"""Guardrails de SALIDA: validación semántica del resultado del LLM.

Lección "Guardrails y validación de outputs". Una vez el LLM ha respondido (ya
con la salida estructurada y validada por Pydantic), aplicamos una regla de
NEGOCIO que el tipado por sí solo no captura.

Regla implementada (misma que el model_validator de EstimationResult):
  Si el modelo declara confianza muy baja (confidence_pct < 30), la estimación no
  es fiable. Solo la aceptamos si está honestamente marcada como fuera de alcance
  (`summary` empieza por "Out of scope"). Si no, la rechazamos con ValueError.

Dónde ocurre el FIX/RETRY de verdad: esta regla vive PRIMARIAMENTE como
`@model_validator` en EstimationResult (app/schemas.py). Al ser parte del
`response_model` de Instructor, su ValueError dispara el REINTENTO del LLM
(política FIX / RETRY). Por eso, un resultado generado vía Instructor ya viene
correcto y esta función es esencialmente un passthrough.

Qué hace entonces validate_output: es una RED DE SEGURIDAD a posteriori
(política EXCEPTION) para resultados que NO se construyeron vía Instructor
(p. ej. servidos desde caché, importados, o de tests). Si uno de esos resultados
incumpliera la regla, aquí se rechaza (el router lo traduce a error HTTP), en vez
de reintentar. Defensa en profundidad: misma regla, dos barreras.

(Las otras dos políticas, ver guardrails/__init__.py:
  - EXCEPTION: bloquear sin reintentar (entrada + esta red de salida).
  - FILTER: sanear/transformar la salida (lo modelamos en el prompt con <scope>).)
"""

from __future__ import annotations

from app.logging_config import get_logger
from app.schemas import EstimationResult

logger = get_logger(component="guardrails_output")

# Umbral por debajo del cual exigimos que la estimación esté marcada como
# fuera de alcance. Por debajo de esto, una estimación "normal" no es de fiar.
_LOW_CONFIDENCE_THRESHOLD = 30
_OUT_OF_SCOPE_PREFIX = "out of scope"


def validate_output(result: EstimationResult) -> EstimationResult:
    """Valida semánticamente el resultado estructurado del LLM (política FIX/RETRY).

    Args:
        result: La estimación estructurada ya validada por Pydantic.

    Returns:
        El mismo `result` si pasa la validación semántica (passthrough).

    Raises:
        ValueError: si confidence_pct < 30 y el summary NO empieza por "Out of
            scope". Instructor usa este error para reintentar la generación.
    """
    if result.confidence_pct < _LOW_CONFIDENCE_THRESHOLD:
        summary_start = result.summary.strip().lower()
        if not summary_start.startswith(_OUT_OF_SCOPE_PREFIX):
            logger.warning(
                "output_low_confidence_rejected",
                confidence_pct=result.confidence_pct,
            )
            raise ValueError(
                f"Confidence is very low ({result.confidence_pct}%) but the summary is not "
                f"marked as out of scope. If the project cannot be reliably estimated, the "
                f"summary must start with 'Out of scope:' and confidence_pct must be 0."
            )
    return result
