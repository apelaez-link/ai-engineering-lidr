"""Router CONVERSACIONAL del estimador (sesión 05).

Convierte el estimador de transaccional a conversacional. Dos endpoints:

  POST /sessions
      Abre una conversación nueva y devuelve su session_id (uuid4). A partir de ahí
      todas las estimaciones de esa conversación comparten memoria.

  POST /sessions/{session_id}/estimate   (multipart/form-data)
      Un turno de la conversación: el cliente manda un `transcript` (texto libre) y,
      opcionalmente, `attachments` (PDF/Word/txt). El endpoint:
        1. Valida la entrada (guardrail) -> 400 si no pasa.
        2. Extrae el texto de los adjuntos y lo concatena al transcript.
        3. Renderiza el prompt con el project_metadata acumulado + el historial.
        4. Genera la estimación estructurada (Instructor) con esos mensajes.
        5. Valida la salida (guardrail).
        6. Actualiza el historial (turno user + turno assistant), respetando la
           ventana deslizante.
        7. Extrae y mergea los metadatos del proyecto (extractor LLM).
        8. Devuelve EstimationResponseStructured.

El prefijo /api/v1 lo añade main.py al incluir este router (igual que el de estimaciones).
"""

from __future__ import annotations

import time

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.config import get_settings
from app.guardrails import InputModerationError, validate_input, validate_output
from app.attachments import extract_attachments
from app.prompts.loader import render_estimation_prompt
from app.schemas import (
    DetailLevel,
    EstimationRequest,
    EstimationResponseStructured,
    OutputFormat,
    ProjectType,
)
from app.services.observation import (
    TurnObservation,
    count_tokens_and_cost,
    emit_turn_observed,
)
from app.services.structured import generate_structured_from_messages
from app.sessions.metadata_extractor import extract_metadata
from app.sessions.store import get_store

router = APIRouter(tags=["sessions"])


@router.post("/sessions")
def create_session() -> dict[str, str]:
    """Abre una conversación nueva y devuelve su identificador.

    Returns:
        {"session_id": "<uuid4>"} — el cliente debe guardarlo y enviarlo en cada
        turno siguiente (POST /sessions/{session_id}/estimate).
    """
    session = get_store().create_session()
    return {"session_id": session.session_id}


@router.get("/sessions/{session_id}")
def get_session_state(session_id: str) -> dict:
    """Devuelve el estado de la sesión: su project_metadata y nº de turnos.

    Lo usa la UI conversacional para pintar el panel lateral con la "memoria viva"
    del proyecto (los hechos acumulados). 404 si la sesión no existe.
    """
    session = get_store().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return {
        "session_id": session.session_id,
        "project_metadata": session.project_metadata.model_dump(),
        "turns": len(session.history.turns),
    }


@router.post("/sessions/{session_id}/estimate", response_model=EstimationResponseStructured)
async def estimate_in_session(
    session_id: str,
    transcript: str = Form(...),
    attachments: list[UploadFile] = File(default=[]),
    prompt_version: str = Query(default="v1", description="Versión del template de prompt (v1, v2...)."),
    project_type: ProjectType = Form(default=ProjectType.WEB_SAAS),
    detail_level: DetailLevel = Form(default=DetailLevel.MEDIUM),
    output_format: OutputFormat = Form(default=OutputFormat.PHASES_TABLE),
) -> EstimationResponseStructured:
    """Procesa UN turno de la conversación con memoria + adjuntos.

    Recibe el cuerpo como multipart/form-data (porque puede llevar ficheros). El
    `transcript` es el mensaje del cliente; `attachments` son documentos opcionales
    cuyo texto se inyecta como contexto enriquecido. Los parámetros de estimación
    (tipo, detalle, formato) van también como campos de formulario con valores por
    defecto razonables, para que el cliente no esté obligado a repetirlos cada turno.
    """
    settings = get_settings()

    # 0) Recuperar la sesión. Si no existe -> 404 (no podemos tener memoria sin sesión).
    session = get_store().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    # 1) GUARDRAIL DE ENTRADA — antes de tocar nada (política EXCEPTION -> 400).
    try:
        validate_input(transcript)
    except InputModerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 2) ADJUNTOS — extracción local (CAMINO B) y concatenación al transcript.
    files: list[tuple[str, bytes]] = []
    for upload in attachments:
        data = await upload.read()
        files.append((upload.filename or "attachment", data))
    attachments_text = extract_attachments(files)

    user_content = transcript
    if attachments_text:
        user_content = f"{transcript}\n\n{attachments_text}"

    # 3) RENDER del prompt con el project_metadata acumulado + historial de la sesión.
    #    Construimos un EstimationRequest con el contenido del turno (transcript +
    #    adjuntos) para reutilizar el mismo loader Jinja2 de la sesión 04. La
    #    descripción debe cumplir el mínimo de 20 caracteres del schema; si el turno
    #    es muy corto, lo rellenamos de forma defensiva sin alterar el sentido.
    description = user_content if len(user_content.strip()) >= 20 else (
        f"{user_content}\n\n(Conversational turn — see conversation history for context.)"
    )
    # EstimationRequest.description tiene un máximo de 2000 caracteres. Con adjuntos
    # grandes (el caso que estresa el stress test de la sesión 06), el contenido
    # enriquecido lo supera y el turno reventaría con un 400. Lo TRUNCAMOS de forma
    # defensiva al límite del schema, dejando una marca explícita. Es justamente uno de
    # los puntos donde "el CAG empieza a romperse": a partir de cierto tamaño de
    # contexto ya no cabe entero en el prompt y hay que recortar (o, en el futuro,
    # resumir/anclar). Medimos el tamaño REAL en enriched_transcript_chars (sin truncar),
    # de modo que el harness vea el tamaño que de verdad entró por la puerta.
    _max_len = 2000  # debe coincidir con EstimationRequest.description (max_length=2000)
    if len(description) > _max_len:
        marker = "\n\n[...attachment truncated to fit prompt window...]"
        description = description[: _max_len - len(marker)] + marker
    request = EstimationRequest(
        description=description,
        project_type=project_type,
        detail_level=detail_level,
        output_format=output_format,
    )
    system, current_user = render_estimation_prompt(
        request, version=prompt_version, project_metadata=session.project_metadata
    )

    # El system se regenera SIEMPRE a partir del metadata actual (los hechos pueden
    # haber cambiado). to_messages_list lo antepone a los turnos recientes; añadimos
    # al final el mensaje de usuario de ESTE turno (aún no está en el historial).
    messages = session.history.to_messages_list(system)
    messages.append({"role": "user", "content": current_user})

    # 4) GENERACIÓN estructurada (Instructor) con la conversación completa.
    #    Medimos la LATENCIA con time.perf_counter SOLO alrededor de la generación
    #    (la parte cara), no del parseo de adjuntos ni de los guardrails. perf_counter
    #    es un reloj monótono de alta resolución: el indicado para medir duraciones.
    gen_start = time.perf_counter()
    try:
        result = generate_structured_from_messages(messages, version=prompt_version)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Error al llamar al LLM: {exc}") from exc
    latency_ms = round((time.perf_counter() - gen_start) * 1000, 1)

    # 5) GUARDRAIL DE SALIDA (red de seguridad para la regla de baja confianza).
    result = validate_output(result)

    # 6) ACTUALIZAR HISTORIAL — par user+assistant. La ventana deslizante (max_turns)
    #    descarta automáticamente los pares más antiguos si nos pasamos del límite.
    session.history.max_turns = settings.max_history_turns
    session.history.add("user", current_user)
    session.history.add("assistant", result.summary)

    # 7) EXTRAER Y MERGEAR METADATOS del proyecto (extractor LLM, defensivo).
    session.project_metadata = extract_metadata(
        transcript=user_content,
        assistant_text=result.summary,
        current=session.project_metadata,
    )

    # 8) OBSERVABILIDAD POR TURNO (sesión 06) — construir y emitir `turn_observed`.
    #    turn_index es 1-based y MONÓTONO dentro de la sesión. No lo derivamos de
    #    len(history.turns) porque la ventana deslizante descarta pares antiguos (ese
    #    len se satura); usamos el contador propio de la sesión.
    session.turn_count += 1
    turn_index = session.turn_count

    # Modelo efectivo para contar tokens/coste. Lo resolvemos igual que structured.py
    # (el proveedor preferido con API key). DEFENSIVO: en tests/mock puede no haberlo,
    # en cuyo caso contamos con un nombre genérico y count_tokens_and_cost devuelve 0.
    try:
        from app.services.structured import _resolve_primary_model

        model_id, _api_key = _resolve_primary_model()
    except Exception:  # noqa: BLE001 — sin proveedor configurado (tests, mock)
        model_id = settings.openai_model

    tokens_in, tokens_out, cost_usd = count_tokens_and_cost(
        model=model_id, messages=messages, output_text=result.summary
    )

    observation = TurnObservation(
        turn_index=turn_index,
        session_id=session.session_id,
        # Contexto enriquecido del turno = transcript + adjuntos (lo que de verdad
        # mandamos como contenido del usuario). attachments_total_chars es el subconjunto.
        enriched_transcript_chars=len(user_content),
        attachments_total_chars=len(attachments_text),
        # Mensajes del historial que sobreviven a la ventana deslizante (sin el system).
        messages_in_window=len(session.history.turns),
        # GAP (no implementado en nuestra base): anclas y summarizer acumulativo.
        anchors_count=0,
        summary_chars=0,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        # El flujo conversacional usa Instructor directamente (no integra los cachés
        # exact/semantic), así que aquí no hay hit de caché: "none". El campo se
        # mantiene en el contrato para cuando se cablee el cacheo a este endpoint.
        cache_hit_kind="none",
        # GAP: no hay tier dinámico (Actor-Critic-Boss); lo dejamos None.
        last_resolved_tier=None,
    )
    observation_dict = emit_turn_observed(observation)

    # 9) Devolver la estimación estructurada del turno + su observación (sesión 06).
    return EstimationResponseStructured(
        result=result,
        prompt_version=prompt_version,
        cached=False,
        observation=observation_dict,
    )
