"""Router de estimaciones: capa HTTP (sesión 04).

Recibe peticiones tipadas (EstimationRequest), delega en el servicio de
orquestación y devuelve EstimationResponse con los metadatos de observabilidad.

Cambios respecto a la sesión 03:
  - Los schemas se importan desde app.schemas (ya no se definen inline).
  - El endpoint /estimate acepta el nuevo schema con project_type, detail_level
    y output_format en lugar de transcripción + historial.
  - Se añade el query param opcional `prompt_version` (bonus) para seleccionar
    la versión del template Jinja2 en tiempo de petición.
  - /estimate/stream se adapta al nuevo schema de request.
"""

import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.cache.semantic import get_semantic_cache, make_bucket
from app.config import get_settings
from app.guardrails import InputModerationError, validate_input, validate_output
from app.schemas import (
    EstimationRequest,
    EstimationResponse,
    EstimationResponseStructured,
    EstimationResult,
)
from app.services.llm_service import generate_estimation, stream_estimation
from app.services.structured import generate_structured_estimation

# El prefijo /api/v1 lo añade main.py al incluir este router.
router = APIRouter(tags=["estimations"])


@router.post("/estimate", response_model=EstimationResponse)
def estimate(
    request: EstimationRequest,
    prompt_version: str = Query(default="v1", description="Versión del template de prompt (v1, v2...)."),
) -> EstimationResponse:
    """Recibe un formulario tipado y devuelve la estimación generada por el LLM.

    El campo `prompt_version` permite seleccionar la versión del template Jinja2
    sin modificar código (útil para A/B testing o comparación de variantes).
    """
    try:
        result = generate_estimation(request, version=prompt_version)
    except ValueError as exc:
        # Errores de configuración (p. ej. falta la API key) -> 400.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # Cualquier otro fallo (red, todos los proveedores caídos, etc.) -> 502.
        raise HTTPException(status_code=502, detail=f"Error al llamar al LLM: {exc}") from exc

    return EstimationResponse(**result)


@router.post("/estimate/stream")
def estimate_stream(
    request: EstimationRequest,
    prompt_version: str = Query(default="v1", description="Versión del template de prompt."),
) -> StreamingResponse:
    """Igual que /estimate, pero devuelve la estimación en STREAMING vía SSE.

    Protocolo (Server-Sent Events, media_type text/event-stream):
      - Por cada fragmento:  event: token   data: {"text": "..."}
      - Al terminar:         event: done    data: {<metadatos: modelo, tokens, coste...>}
      - Si hay error:        event: error   data: {"detail": "..."}

    Codificamos el texto como JSON en el campo `data` para que los saltos de línea
    del Markdown no rompan el framing de SSE (cada evento SSE termina en línea en blanco).
    El cliente debe hacer JSON.parse de event.data.
    """
    def event_source():
        meta: dict = {}
        try:
            for chunk in stream_estimation(request, version=prompt_version, meta=meta):
                yield f"event: token\ndata: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
        except ValueError as exc:
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
            return
        except Exception as exc:  # noqa: BLE001
            yield f"event: error\ndata: {json.dumps({'detail': f'Error al llamar al LLM: {exc}'})}\n\n"
            return
        # Evento final con los metadatos de trazabilidad (sin el contenido completo,
        # que ya se envió token a token). Añadimos la versión del prompt.
        meta.pop("content", None)
        meta.pop("providers_tried", None)
        meta["prompt_version"] = prompt_version
        yield f"event: done\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.post("/estimate/structured", response_model=EstimationResponseStructured)
def estimate_structured(
    request: EstimationRequest,
    prompt_version: str = Query(default="v1", description="Versión del template de prompt (v1, v2...)."),
) -> EstimationResponseStructured:
    """Devuelve la estimación como JSON ESTRUCTURADO y validado (sesión 04).

    Integra los tres temas del directo con el ORDEN del pipeline que enseña la
    lección de cacheo semántico:

      1. GUARDRAILS DE ENTRADA (validate_input) — PRIMERO de todo. Moderación +
         anti prompt-injection. Si no pasa, ni siquiera consultamos la caché ni
         llamamos al LLM (política EXCEPTION -> HTTP 400). Validar antes de cachear
         evita envenenar la caché con entradas maliciosas.

      2. CACHE LOOKUP (semántico) — buscamos una respuesta equivalente ya generada
         en el mismo bucket. Si HIT, devolvemos con cached=True sin tocar el LLM.

      3. GENERACIÓN + GUARDRAILS DE SALIDA — solo si MISS. Instructor genera el
         EstimationResult tipado; validate_output aplica la regla semántica de
         baja confianza (política FIX/RETRY).

      4. CACHE WRITE — SOLO tras validar la salida. Nunca cacheamos algo que no
         haya pasado los guardrails.
    """
    settings = get_settings()

    # 1) GUARDRAILS DE ENTRADA (antes de componer el prompt o tocar la caché).
    try:
        validate_input(request.description)
    except InputModerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Bucket determinista para el cacheo semántico (parte "exacta" de la clave).
    bucket = make_bucket(
        project_type=request.project_type.value,
        detail_level=request.detail_level.value,
        output_format=request.output_format.value,
        prompt_version=prompt_version,
    )
    cache = get_semantic_cache()

    # 2) CACHE LOOKUP semántico.
    if settings.semantic_cache_enabled:
        try:
            hit = cache.lookup(request.description, bucket)
        except Exception:  # noqa: BLE001 — fallo de embeddings no debe tumbar la petición
            hit = None
        if hit is not None:
            result = EstimationResult.model_validate_json(hit)
            return EstimationResponseStructured(
                result=result, prompt_version=prompt_version, cached=True
            )

    # 3) MISS -> generación estructurada + guardrail de salida.
    try:
        result = generate_structured_estimation(request, version=prompt_version)
    except ValueError as exc:
        # Error de configuración (falta API key, etc.) -> 400.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Error al llamar al LLM: {exc}") from exc

    # Guardrail de salida (regla semántica de baja confianza).
    result = validate_output(result)

    # 4) CACHE WRITE — solo después de validar la salida.
    if settings.semantic_cache_enabled:
        try:
            cache.write(request.description, bucket, result.model_dump_json())
        except Exception:  # noqa: BLE001 — un fallo al cachear no debe romper la respuesta
            pass

    return EstimationResponseStructured(
        result=result, prompt_version=prompt_version, cached=False
    )
