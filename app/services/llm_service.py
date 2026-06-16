"""Capa de orquestación del estimador (sesión 04: formulario tipado + prompts Jinja2).

Esta capa conecta los schemas Pydantic con el loader de prompts y el wrapper
de proveedores. Reemplaza el flujo anterior basado en transcripción / historial /
CAG por un flujo más limpio:

    EstimationRequest
        -> render_estimation_prompt (Jinja2)    <- template versionado
        -> wrapper.complete / wrapper.stream    <- abstracción LLM
        -> dict / Iterator[str]

Los cambios respecto a la sesión 03:
  - Se elimina la lógica de historial multi-turn (_build_conversation,
    _apply_sliding_window) porque el nuevo modelo de producto es de una sola
    petición: el formulario tipado es el contexto.
  - Se elimina _build_system_prompt: los prompts viven en templates Jinja2
    versionados, no inlineados en código Python.
  - Se añade el parámetro `version` en ambas funciones para el bonus de
    selección de versión de prompt.

Compatibilidad: generate_estimation acepta tanto un EstimationRequest como una
cadena de texto (transcripción libre). Esto mantiene el contrato que usa
test_wrapper.py (que no podemos modificar) y permite la migración gradual.
"""

from collections.abc import Iterator

from app.prompts.loader import render_estimation_prompt
from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType
from app.services.llm_wrapper import wrapper


def _coerce_to_request(request_or_str: "EstimationRequest | str") -> EstimationRequest:
    """Convierte una cadena libre en un EstimationRequest con valores por defecto.

    Esto permite mantener la compatibilidad con código que todavía llama a
    generate_estimation con una transcripción de texto plano (como test_wrapper.py).
    El texto libre se trata como descripción con los parámetros más habituales.
    """
    if isinstance(request_or_str, str):
        return EstimationRequest(
            description=request_or_str if len(request_or_str) >= 20 else request_or_str + " (descripción de proyecto)",
            project_type=ProjectType.WEB_SAAS,
            detail_level=DetailLevel.MEDIUM,
            output_format=OutputFormat.NARRATIVE,
        )
    return request_or_str


def generate_estimation(request: "EstimationRequest | str", version: str = "v1") -> dict:
    """Genera la estimación de forma síncrona (no streaming).

    Renderiza el par (system, user) con Jinja2 y delega en el wrapper, que
    gestiona abstracción de proveedores, fallback, caché y observabilidad.

    Args:
        request: Schema validado con todos los parámetros del formulario, o una
                 cadena de texto libre (compatibilidad con test_wrapper.py).
        version: Versión del template de prompt (default "v1").

    Returns:
        Diccionario con los campos de EstimationResponse (texto + metadatos).
        Incluye finish_reason para mantener compatibilidad con tests heredados.
    """
    req = _coerce_to_request(request)
    system, user = render_estimation_prompt(req, version=version)
    result = wrapper.complete(system, [{"role": "user", "content": user}])

    return {
        "text": result.content,
        "prompt_version": version,
        "model": result.model,
        "cache_hit": result.cache_hit,
        "fallback_used": result.fallback_used,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "cost_usd": result.cost_usd,
        "latency_ms": result.latency_ms,
        # finish_reason se mantiene en el dict del servicio para compatibilidad
        # con test_wrapper.py y para que el endpoint de streaming pueda usarlo.
        "finish_reason": result.finish_reason,
    }


def stream_estimation(
    request: EstimationRequest,
    version: str = "v1",
    *,
    meta: dict | None = None,
) -> Iterator[str]:
    """Versión en streaming: produce la estimación token a token.

    Los metadatos de la llamada (modelo, tokens, coste, latencia, cache_hit...)
    se vuelcan en el dict `meta` al terminar la generación, para que el router
    SSE los emita en el evento `done`.

    Args:
        request: Schema validado con todos los parámetros del formulario.
        version: Versión del template de prompt (default "v1").
        meta:    Dict mutable donde el wrapper deposita los metadatos al finalizar.
    """
    system, user = render_estimation_prompt(request, version=version)
    yield from wrapper.stream(system, [{"role": "user", "content": user}], meta=meta)
