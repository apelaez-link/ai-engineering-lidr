"""Tests de la evaluación estructural (reto sesión 3). Pura: sin LLM, sin red."""

from app.services.evaluation import evaluate_estimation

ESTIMACION_OK = """## Estimación: Plataforma de prueba

### Desglose de tareas:
1. Diseño UI/UX: 40 horas
2. Backend API: 60 horas

**Total estimado: 100 horas**
**Equipo recomendado: 2 desarrolladores full-stack**
**Duración estimada: 5 semanas**
**Supuestos: integración con un único sistema externo.**
"""


def test_estimacion_bien_formada_puntua_alto() -> None:
    ev = evaluate_estimation(ESTIMACION_OK, finish_reason="stop")
    assert ev.has_title and ev.has_breakdown and ev.has_total
    assert ev.has_team and ev.has_duration and ev.has_assumptions
    assert ev.sum_task_hours == 100
    assert ev.declared_total_hours == 100
    assert ev.hours_match is True
    assert ev.finish_reason_ok is True
    assert ev.score == 1.0
    assert ev.issues == []


def test_detecta_incoherencia_aritmetica() -> None:
    # Suma de tareas = 100, pero el total declarado dice 250 -> mismatch.
    texto = ESTIMACION_OK.replace("Total estimado: 100 horas", "Total estimado: 250 horas")
    ev = evaluate_estimation(texto, finish_reason="stop")
    assert ev.hours_match is False
    assert any("aritm" in i.lower() for i in ev.issues)
    assert ev.score < 1.0


def test_detecta_truncamiento() -> None:
    ev = evaluate_estimation(ESTIMACION_OK, finish_reason="length")
    assert ev.finish_reason_ok is False
    assert any("trunc" in i.lower() for i in ev.issues)


def test_texto_pobre_puntua_bajo() -> None:
    ev = evaluate_estimation("Esto no es una estimación con formato.", finish_reason="stop")
    assert ev.score < 0.5
    assert len(ev.issues) >= 4
