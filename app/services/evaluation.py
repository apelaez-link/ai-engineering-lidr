"""Evaluación estructural de una estimación (reto inspirado en el repo del profesor).

NO llama al LLM: son comprobaciones por regex sobre el texto generado. Da una señal
rápida y automatizable de si el modelo produjo algo "bien formado" según el formato
que pedimos en el system prompt (CAG):

  - Título en H2 (## ...)
  - Desglose de tareas con horas
  - Total de horas declarado
  - Equipo recomendado
  - Duración estimada (en semanas)
  - Supuestos
  - Coherencia aritmética: la suma de horas de las tareas ≈ el total declarado
  - finish_reason válido (no truncado) -> reutiliza el campo que añadimos en el mini-reto

Es la semilla de un "guardrail" de outputs (tema de la sesión 4). Lo diseñamos para
NUESTRO formato en español, no copiamos el del profesor: misma idea, criterios propios.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

# finish_reason que consideramos "terminó bien" (OpenAI usa "stop"; Anthropic "end_turn").
_OK_FINISH_REASONS = {"stop", "end_turn"}

# Una fila de tarea del desglose: "1. Diseño UI/UX: 40 horas"
_TASK_ROW_RE = re.compile(
    r"^\s*\d+\.\s+(?P<task>.+?):\s*(?P<hours>\d+)\s*horas?", re.MULTILINE | re.IGNORECASE
)
# "Total estimado: 200 horas" (admite negritas y variantes).
_TOTAL_HOURS_RE = re.compile(r"Total\s+estimado[:\*\s]*([\d.]+)\s*horas?", re.IGNORECASE)


class EstimationEvaluation(BaseModel):
    """Resultado de la evaluación estructural. score ∈ [0, 1]."""

    has_title: bool
    has_breakdown: bool
    has_total: bool
    has_team: bool
    has_duration: bool
    has_assumptions: bool
    declared_total_hours: int | None = None
    sum_task_hours: int | None = None
    hours_match: bool | None = Field(
        default=None,
        description="¿La suma de horas de las tareas cuadra con el total declarado? "
        "None si no hay datos suficientes para comprobarlo.",
    )
    finish_reason_ok: bool = True
    score: float = 0.0
    issues: list[str] = Field(default_factory=list)


def evaluate_estimation(text: str, finish_reason: str | None = "stop") -> EstimationEvaluation:
    """Evalúa la estructura de una estimación generada. Pura: sin LLM, sin red."""
    has_title = bool(re.search(r"^##\s+\S", text, re.MULTILINE))
    has_breakdown = bool(re.search(r"desglose", text, re.IGNORECASE)) or bool(
        _TASK_ROW_RE.search(text)
    )
    has_total = bool(_TOTAL_HOURS_RE.search(text))
    has_team = bool(re.search(r"equipo\s+recomendado", text, re.IGNORECASE))
    has_duration = bool(
        re.search(r"(duraci[oó]n\s+estimada|semanas?)", text, re.IGNORECASE)
    )
    has_assumptions = bool(re.search(r"supuestos?", text, re.IGNORECASE))

    # Coherencia aritmética: sumamos las horas de cada tarea y la comparamos con el total.
    task_hours = [int(m.group("hours")) for m in _TASK_ROW_RE.finditer(text)]
    sum_task_hours = sum(task_hours) if task_hours else None

    m_total = _TOTAL_HOURS_RE.search(text)
    declared_total_hours = int(float(m_total.group(1))) if m_total else None

    if sum_task_hours is not None and declared_total_hours is not None:
        # Tolerancia de ±1 hora por redondeos.
        hours_match: bool | None = abs(sum_task_hours - declared_total_hours) <= 1
    else:
        hours_match = None

    finish_reason_ok = (finish_reason or "stop") in _OK_FINISH_REASONS

    # El score es la fracción de comprobaciones superadas.
    checks = [
        has_title,
        has_breakdown,
        has_total,
        has_team,
        has_duration,
        has_assumptions,
        bool(hours_match),
        finish_reason_ok,
    ]
    score = round(sum(checks) / len(checks), 3)

    issues: list[str] = []
    if not has_title:
        issues.append("Falta el título en H2 (## ...).")
    if not has_breakdown:
        issues.append("Falta el desglose de tareas con horas.")
    if not has_total:
        issues.append("Falta el total de horas estimado.")
    if not has_team:
        issues.append("Falta el equipo recomendado.")
    if not has_duration:
        issues.append("Falta la duración estimada (en semanas).")
    if not has_assumptions:
        issues.append("Faltan los supuestos.")
    if hours_match is False:
        issues.append(
            f"Incoherencia aritmética: la suma de tareas ({sum_task_hours} h) "
            f"no cuadra con el total declarado ({declared_total_hours} h)."
        )
    if not finish_reason_ok:
        issues.append(f"Respuesta truncada o finish_reason inesperado: '{finish_reason}'.")

    return EstimationEvaluation(
        has_title=has_title,
        has_breakdown=has_breakdown,
        has_total=has_total,
        has_team=has_team,
        has_duration=has_duration,
        has_assumptions=has_assumptions,
        declared_total_hours=declared_total_hours,
        sum_task_hours=sum_task_hours,
        hours_match=hours_match,
        finish_reason_ok=finish_reason_ok,
        score=score,
        issues=issues,
    )
