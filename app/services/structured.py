"""Generación de estimaciones con SALIDA JSON ESTRUCTURADA (sesión 04).

Lección "Extracción de datos estructurados". Hasta ahora el LLM devolvía texto
libre (Markdown) que el cliente tenía que parsear a mano. Aquí damos el salto a
un contrato de datos TIPADO: le pedimos al modelo que rellene un objeto Pydantic
(EstimationResult) y dejamos que Instructor garantice que la salida valida.

¿Por qué Instructor y no `response_format={"type": "json_object"}` a pelo?
  - Instructor inyecta el JSON Schema del modelo Pydantic en la llamada.
  - Parsea la respuesta y la valida contra el schema (incluido nuestro
    @model_validator de coherencia de totales).
  - Si la validación falla, REINTENTA automáticamente devolviéndole al LLM el
    error de validación, hasta `max_retries`. Esto es el patrón "fix/retry" que
    también usaremos en los guardrails de salida.

Funcionamos sobre litellm (no sobre el SDK de OpenAI directamente) para mantener
la abstracción de proveedores del wrapper: `instructor.from_litellm(...)`.
"""

from __future__ import annotations

import instructor
import litellm

from app.config import get_settings
from app.logging_config import get_logger
from app.prompts.loader import render_estimation_prompt
from app.schemas import EstimationRequest, EstimationResult

logger = get_logger(component="structured")

# LiteLLM por defecto manda telemetría y puede fallar ante params no soportados.
# Replicamos la misma configuración defensiva que el wrapper.
litellm.telemetry = False
litellm.drop_params = True


def _resolve_primary_model() -> tuple[str, str]:
    """Resuelve (model_id, api_key) del proveedor preferido para Instructor.

    Reutilizamos la lógica del wrapper: tomamos el primer proveedor del orden de
    fallback que tenga API key configurada. Instructor no hace fallback entre
    proveedores (eso vive en el wrapper de texto libre), así que aquí basta el
    preferido. Si no hay ninguno con key, lanzamos ValueError claro.
    """
    from app.services.llm_wrapper import _available_providers, _resolve_model

    providers = _available_providers()
    if not providers:
        raise ValueError(
            "No hay ningún proveedor con API key configurada. "
            "Rellena OPENAI_API_KEY o ANTHROPIC_API_KEY en el .env."
        )
    return _resolve_model(providers[0])


def generate_structured_estimation(
    request: EstimationRequest, version: str = "v1"
) -> EstimationResult:
    """Genera la estimación como objeto Pydantic tipado y validado.

    Flujo:
      1. Renderiza el par (system, user) con el mismo loader Jinja2 que el endpoint
         de texto libre (reutilizamos prompts versionados).
      2. Crea un cliente Instructor sobre litellm.completion.
      3. Llama con response_model=EstimationResult: Instructor fuerza el JSON,
         lo valida y reintenta si falla.

    Args:
        request: Formulario tipado con los parámetros de la estimación.
        version: Versión del template de prompt ("v1", "v2"...).

    Returns:
        EstimationResult validado (campos + coherencia de totales).

    Raises:
        ValueError: si no hay API key configurada (error de configuración claro).
    """
    settings = get_settings()
    model, api_key = _resolve_primary_model()

    system, user = render_estimation_prompt(request, version=version)

    # Instructor envuelve litellm.completion. Mensajes system/user separados, igual
    # que en el wrapper de texto libre, para no romper la semántica de los prompts.
    client = instructor.from_litellm(litellm.completion)

    logger.info("structured_call_started", model=model, prompt_version=version)
    result: EstimationResult = client.chat.completions.create(
        model=model,
        api_key=api_key,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        response_model=EstimationResult,
        # max_retries explícito (es también el default de Instructor): si la salida
        # no valida contra EstimationResult (totales incoherentes, o confianza baja sin
        # "Out of scope"...), Instructor le muestra el error al LLM y reintenta. Es la
        # política FIX/RETRY, y vive en los @model_validator del schema EstimationResult.
        max_retries=3,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    logger.info(
        "structured_call_completed",
        model=model,
        prompt_version=version,
        phases=len(result.phases),
        confidence_pct=result.confidence_pct,
    )
    return result
