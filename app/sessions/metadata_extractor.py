"""Extractor LLM de metadatos del proyecto (sesión 05).

Segundo uso de Instructor en el sistema (el primero genera la estimación): aquí un
LLM lee el turno actual (mensaje del cliente + respuesta del asistente) y DESTILA
los hechos del proyecto a un ProjectMetadata tipado. Luego MERGEAMOS ese resultado
con la memoria que ya teníamos, de modo que la conversación va acumulando contexto
sin perder lo aprendido antes.

¿Por qué un LLM y no una expresión regular? Porque los hechos llegan en lenguaje
natural y de formas muy variadas ("somos cuatro", "un equipo de 4", "team of four").
Un extractor LLM con salida estructurada lo normaliza a campos tipados de forma
robusta. Es el patrón CAMINO B / EXTRACTOR LLM acordado para esta fase.

DEFENSIVO: la extracción de metadatos es un EXTRA, no el camino crítico. Si falla
(sin API key, error de red, validación...), NO debe tumbar la petición: devolvemos
el `current` sin cambios. La estimación ya se generó y se devolvió igualmente.
"""

from __future__ import annotations

import instructor
import litellm

from app.config import get_settings
from app.logging_config import get_logger
from app.prompts.loader import render_metadata_extraction_prompt
from app.sessions.models import ProjectMetadata

logger = get_logger(component="metadata_extractor")

# Misma configuración defensiva de litellm que en structured.py.
litellm.telemetry = False
litellm.drop_params = True


def _resolve_extractor_model() -> tuple[str, str]:
    """Resuelve (model_id, api_key) para el extractor de metadatos.

    Reutilizamos los helpers del wrapper para tomar el primer proveedor con API key,
    pero forzamos el MODELO configurado para el extractor (metadata_extractor_model)
    cuando el proveedor primario es OpenAI. Si no hay ningún proveedor con key,
    lanzamos ValueError (lo captura el caller defensivo de extract_metadata).
    """
    from app.services.llm_wrapper import _available_providers, _resolve_model

    providers = _available_providers()
    if not providers:
        raise ValueError("No provider with API key configured for metadata extraction.")

    provider = providers[0]
    model, api_key = _resolve_model(provider)
    # Para OpenAI usamos el modelo del extractor (puede diferir del de estimación).
    if provider == "openai":
        model = get_settings().metadata_extractor_model
    return model, api_key


def extract_metadata(
    transcript: str,
    assistant_text: str,
    current: ProjectMetadata,
    version: str = "v1",
) -> ProjectMetadata:
    """Extrae los hechos del turno actual y los MERGEA con la memoria previa.

    Flujo:
      1. Renderiza el prompt del extractor con (transcript, assistant_text).
      2. Llama a Instructor (sobre litellm) con response_model=ProjectMetadata: el LLM
         devuelve SOLO los hechos nuevos de este turno (tipados y validados).
      3. Mergea esos hechos nuevos con `current` (la memoria acumulada) usando
         ProjectMetadata.merge, que no pierde nada de lo que ya sabíamos.

    Args:
        transcript:     Mensaje del cliente en el turno actual.
        assistant_text: Respuesta del asistente (p. ej. el summary de la estimación).
        current:        La memoria de la sesión ANTES de este turno.
        version:        Versión del template del extractor.

    Returns:
        El ProjectMetadata MERGEADO. Si la extracción falla por cualquier motivo,
        devuelve `current` intacto (defensivo: nunca rompe la petición).
    """
    try:
        settings = get_settings()
        model, api_key = _resolve_extractor_model()
        system, user = render_metadata_extraction_prompt(
            transcript, assistant_text, version=version
        )

        client = instructor.from_litellm(litellm.completion)
        extracted: ProjectMetadata = client.chat.completions.create(
            model=model,
            api_key=api_key,
            temperature=0,  # extracción determinista: queremos hechos, no creatividad
            max_tokens=settings.llm_max_tokens,
            response_model=ProjectMetadata,
            max_retries=2,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        merged = current.merge(extracted)
        logger.info(
            "metadata_extracted",
            model=model,
            technologies=len(merged.mentioned_technologies),
            has_team_size=merged.assumed_team_size is not None,
        )
        return merged
    except Exception as exc:  # noqa: BLE001 — la extracción es un extra, no el camino crítico
        # No abortamos la petición por un fallo en la extracción: la estimación ya
        # está hecha. Conservamos la memoria previa intacta y seguimos.
        logger.warning("metadata_extraction_failed", reason=type(exc).__name__)
        return current
