"""Router de estimaciones: capa HTTP.

Define los endpoints y los schemas (contratos) Pydantic. El router NO contiene
lógica de negocio: valida la petición, delega en el servicio y devuelve la respuesta.

En la sesión 03 añadimos:
  - metadatos de trazabilidad en la respuesta de /estimate (modelo, tokens, coste,
    latencia, cache_hit, fallback_used),
  - un endpoint /estimate/stream que devuelve la estimación en STREAMING vía SSE
    (Server-Sent Events), para clientes que no sean Streamlit.
"""

import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.llm_service import generate_estimation, stream_estimation

# El prefijo /api/v1 se lo pone main.py al incluir este router.
router = APIRouter(tags=["estimations"])


class Message(BaseModel):
    """Un turno de la conversación. 'role' solo puede ser user o assistant.

    El system prompt NO viaja aquí: lo construye el servicio en cada llamada con el
    contexto CAG. Aquí solo van los turnos visibles de la conversación.
    """

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)


class EstimationRequest(BaseModel):
    """Cuerpo de la petición. Pydantic valida que 'transcription' venga y no esté vacío."""

    transcription: str = Field(
        ...,
        min_length=1,
        description="Texto de la transcripción de la reunión, o el siguiente mensaje del usuario.",
        examples=[
            "En la reunión con el equipo de marketing, el cliente explicó que "
            "necesita una landing page con formulario de contacto e integración con HubSpot."
        ],
    )
    history: list[Message] | None = Field(
        default=None,
        description=(
            "Turnos previos (user/assistant) para continuar una conversación. "
            "Omítelo en la primera llamada; en las siguientes, reenvía el 'history' "
            "que devolvió la respuesta anterior."
        ),
    )


class EstimationResponse(BaseModel):
    """Forma de la respuesta. Documenta el contrato de salida en Swagger."""

    estimation: str = Field(..., description="Estimación generada por el LLM (Markdown).")
    model: str = Field(..., description="Modelo concreto usado, p. ej. gpt-4o-mini.")
    provider: str = Field(..., description="Proveedor que respondió: openai o anthropic.")
    history: list[Message] = Field(
        ...,
        description="Historial actualizado (incluye este turno). Reenvíalo en la siguiente petición.",
    )
    # ── Metadatos de trazabilidad (sesión 03) ──────────────────────────────
    cache_hit: bool = Field(default=False, description="True si la respuesta vino de caché.")
    fallback_used: bool = Field(
        default=False, description="True si respondió un proveedor de fallback, no el primario."
    )
    tokens_in: int = Field(default=0, description="Tokens de entrada (prompt).")
    tokens_out: int = Field(default=0, description="Tokens de salida (respuesta).")
    cost_usd: float = Field(default=0.0, description="Coste estimado de la llamada en USD.")
    latency_ms: float = Field(default=0.0, description="Latencia de la llamada en milisegundos.")


@router.post("/estimate", response_model=EstimationResponse)
def estimate(request: EstimationRequest) -> EstimationResponse:
    """Recibe una transcripción (y, opcionalmente, el historial) y devuelve la estimación."""
    history = [m.model_dump() for m in request.history] if request.history else None
    try:
        result = generate_estimation(request.transcription, history=history)
    except ValueError as exc:
        # Errores de configuración (p. ej. falta la API key) -> 400.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # Cualquier otro fallo (red, todos los proveedores caídos, etc.) -> 502.
        raise HTTPException(status_code=502, detail=f"Error al llamar al LLM: {exc}") from exc

    return EstimationResponse(**result)


@router.post("/estimate/stream")
def estimate_stream(request: EstimationRequest) -> StreamingResponse:
    """Igual que /estimate, pero devuelve la estimación en STREAMING vía SSE.

    Protocolo (Server-Sent Events, media_type text/event-stream):
      - Por cada fragmento:  event: token   data: {"text": "..."}
      - Al terminar:         event: done    data: {<metadatos: modelo, tokens, coste...>}
      - Si hay error:        event: error   data: {"detail": "..."}

    Codificamos el texto como JSON en el campo `data` para que los saltos de línea
    del Markdown no rompan el framing de SSE (cada evento SSE termina en línea en blanco).
    El cliente debe hacer JSON.parse de event.data.
    """
    history = [m.model_dump() for m in request.history] if request.history else None

    def event_source():
        meta: dict = {}
        try:
            for chunk in stream_estimation(request.transcription, history=history, meta=meta):
                yield f"event: token\ndata: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
        except ValueError as exc:
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
            return
        except Exception as exc:  # noqa: BLE001
            yield f"event: error\ndata: {json.dumps({'detail': f'Error al llamar al LLM: {exc}'})}\n\n"
            return
        # Evento final con los metadatos de trazabilidad (sin el contenido completo,
        # que ya se envió token a token).
        meta.pop("content", None)
        meta.pop("providers_tried", None)
        yield f"event: done\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
