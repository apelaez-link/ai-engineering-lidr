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

from app.schemas import EstimationRequest, EstimationResponse
from app.services.llm_service import generate_estimation, stream_estimation

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
