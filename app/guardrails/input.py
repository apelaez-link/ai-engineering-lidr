"""Guardrails de ENTRADA: moderación y anti prompt-injection.

Lección "Guardrails y validación de outputs". Antes de gastar un token llamando
al LLM, validamos lo que el usuario nos manda. Política aplicada aquí: EXCEPTION
(si la entrada es inaceptable, abortamos con InputModerationError; el router la
traduce a HTTP 400).

Dos comprobaciones:

  1. MODERACIÓN: usamos `litellm.moderation` para detectar contenido marcado
     (odio, violencia, etc.). Va envuelta en try/except: si el proveedor o la
     versión instalada no soporta moderación, lo OMITIMOS con un log en vez de
     romper. Filosofía del repo: "corre sin infra por defecto".

  2. PROMPT INJECTION: heurística de patrones conocidos ("ignore previous",
     "you are now", etc.). No es infalible, pero corta los intentos más obvios de
     secuestrar el system prompt. En producción se combinaría con un clasificador.
"""

from __future__ import annotations

from app.logging_config import get_logger

logger = get_logger(component="guardrails_input")


class InputModerationError(ValueError):
    """La entrada del usuario no pasó los guardrails de entrada (política EXCEPTION).

    Hereda de ValueError para que el router la pueda traducir a HTTP 400 con la
    misma rama que el resto de errores de validación de entrada.
    """


# Patrones de prompt-injection más habituales. Comparación en minúsculas.
# No pretende ser exhaustivo: corta los intentos evidentes de override del system.
_INJECTION_PATTERNS: tuple[str, ...] = (
    "ignore previous",
    "ignore all instructions",
    "you are now",
    "system prompt",
    "</project_description>",
)


def validate_input(description: str) -> None:
    """Valida la descripción del usuario antes de componer el prompt.

    Política: EXCEPTION. Si algo no pasa, lanza InputModerationError y NO se llama
    al LLM. Si todo pasa, retorna None silenciosamente.

    Args:
        description: Texto libre que el usuario envía como descripción del proyecto.

    Raises:
        InputModerationError: si la moderación marca el contenido o si se detecta
            un patrón de prompt-injection.
    """
    # 1) MODERACIÓN — defensiva: si no está soportada, se omite con un log.
    try:
        import litellm

        moderation = litellm.moderation(input=description)
        flagged = _is_flagged(moderation)
        if flagged:
            logger.warning("input_moderation_flagged")
            raise InputModerationError(
                "The input was flagged by the moderation guardrail and cannot be processed."
            )
    except InputModerationError:
        raise
    except Exception as exc:  # noqa: BLE001 — moderación no soportada / sin red
        # No abortamos por un fallo de infraestructura de moderación: lo registramos
        # y seguimos con el resto de comprobaciones (corre sin infra por defecto).
        logger.info("input_moderation_skipped", reason=type(exc).__name__)

    # 2) PROMPT INJECTION — heurística de patrones conocidos.
    lowered = description.lower()
    for pattern in _INJECTION_PATTERNS:
        if pattern in lowered:
            logger.warning("input_injection_detected", pattern=pattern)
            raise InputModerationError(
                f"The input contains a disallowed prompt-injection pattern: '{pattern}'."
            )


def _is_flagged(moderation_response: object) -> bool:
    """Extrae el flag de la respuesta de moderación de forma defensiva.

    La respuesta de litellm.moderation imita la de OpenAI: tiene `results`, una
    lista de objetos con atributo `flagged`. Soportamos también dicts por si el
    mock de los tests devuelve un dict.
    """
    results = None
    if isinstance(moderation_response, dict):
        results = moderation_response.get("results")
    else:
        results = getattr(moderation_response, "results", None)

    if not results:
        return False

    first = results[0]
    if isinstance(first, dict):
        return bool(first.get("flagged", False))
    return bool(getattr(first, "flagged", False))
