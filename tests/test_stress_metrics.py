"""Tests de las métricas deterministas del stress test (sesión 06, BLOQUE 4).

Cubrimos, para cada métrica, los tres casos que pide el ejercicio:
  - una que PASA (score 1.0),
  - una que FALLA (score 0.0),
  - un caso LÍMITE (valor justo en el umbral / hecho parcialmente presente).

Todo es determinista: sin APIs, sin embeddings, sin LLM. Importamos las métricas
directamente del módulo evals.stress.metrics.
"""

from evals.stress.metrics import (
    CostBudgetMetric,
    LatencyBudgetMetric,
    MemoryDriftMetric,
    MetricResult,
)


# ── LatencyBudgetMetric ───────────────────────────────────────────────────────


def test_latency_budget_passes_under_budget() -> None:
    """Latencia por debajo del presupuesto -> score 1.0 y passed True."""
    metric = LatencyBudgetMetric(budget_ms=2000)
    result = metric.evaluate(latency_ms=1500)
    assert isinstance(result, MetricResult)
    assert result.name == "latency_budget"
    assert result.score == 1.0
    assert result.passed is True
    assert result.details["latency_ms"] == 1500


def test_latency_budget_fails_over_budget() -> None:
    """Latencia por encima del presupuesto -> score 0.0 y passed False."""
    metric = LatencyBudgetMetric(budget_ms=2000)
    result = metric.evaluate(latency_ms=3500)
    assert result.score == 0.0
    assert result.passed is False


def test_latency_budget_boundary_equal_passes() -> None:
    """Caso LÍMITE: latencia EXACTAMENTE igual al presupuesto se considera dentro (<=)."""
    metric = LatencyBudgetMetric(budget_ms=2000)
    result = metric.evaluate(latency_ms=2000)
    assert result.score == 1.0
    assert result.passed is True


# ── CostBudgetMetric ──────────────────────────────────────────────────────────


def test_cost_budget_passes_under_budget() -> None:
    """Coste por debajo del presupuesto -> pasa."""
    metric = CostBudgetMetric(budget_usd=0.01)
    result = metric.evaluate(cost_usd=0.004)
    assert result.name == "cost_budget"
    assert result.score == 1.0
    assert result.passed is True


def test_cost_budget_fails_over_budget() -> None:
    """Coste por encima del presupuesto -> falla."""
    metric = CostBudgetMetric(budget_usd=0.01)
    result = metric.evaluate(cost_usd=0.05)
    assert result.score == 0.0
    assert result.passed is False


def test_cost_budget_boundary_equal_passes() -> None:
    """Caso LÍMITE: coste EXACTAMENTE igual al presupuesto se considera dentro (<=)."""
    metric = CostBudgetMetric(budget_usd=0.01)
    result = metric.evaluate(cost_usd=0.01)
    assert result.score == 1.0
    assert result.passed is True


# ── MemoryDriftMetric ─────────────────────────────────────────────────────────


def test_memory_drift_passes_when_fact_present_in_metadata() -> None:
    """El fact aparece en el ProjectMetadata acumulado -> score 1.0 (sin deriva).

    Búsqueda case-insensitive: el fact "Helios" se encuentra aunque el metadata lo
    guarde como "helios" en otro casing.
    """
    snapshot = {
        "project_metadata": {
            "project_name": "helios",
            "mentioned_technologies": ["Django", "React"],
            "agreed_scope": "Solar fleet monitoring SaaS",
        }
    }
    metric = MemoryDriftMetric(fact="Helios")
    result = metric.evaluate(snapshot)
    assert result.name == "memory_drift"
    assert result.score == 1.0
    assert result.passed is True
    assert result.details["found"] is True


def test_memory_drift_fails_when_fact_absent() -> None:
    """El fact NO aparece en ningún campo disponible -> score 0.0 (deriva detectada)."""
    snapshot = {
        "project_metadata": {
            "project_name": "Atlas",
            "mentioned_technologies": ["Go"],
            "agreed_scope": "Data pipeline",
        }
    }
    metric = MemoryDriftMetric(fact="Helios")
    result = metric.evaluate(snapshot)
    assert result.score == 0.0
    assert result.passed is False
    assert result.details["found"] is False


def test_memory_drift_boundary_summary_anchors_empty_history_fallback() -> None:
    """Caso LÍMITE/GAP: summary y anchors vacíos; el fact solo está en el historial.

    Refleja nuestra base real: no hay summarizer (summary) ni anclas (anchors), así
    que esos campos vienen vacíos. El runner añade "history" (texto de los turnos).
    Con el where por defecto (summary, anchors, metadata) el fact "80k" NO se
    encontraría; ampliando where con "history" SÍ. Verifica ambos extremos.
    """
    snapshot = {
        "summary": "",  # GAP: no hay summarizer acumulativo
        "anchors": [],  # GAP: no hay sistema de anclas
        "project_metadata": {"project_name": "Atlas", "agreed_scope": "Data pipeline"},
        "history": "user: budget is now 80k EUR not 30k\nassistant: re-estimated for 80k",
    }

    # Con el where por defecto (sin "history") y el fact solo en el historial -> falla.
    default_metric = MemoryDriftMetric(fact="80k")
    assert default_metric.evaluate(snapshot).score == 0.0

    # Ampliando where con "history" (lo que hace el runner) -> lo encuentra -> pasa.
    history_metric = MemoryDriftMetric(fact="80k", where=["summary", "anchors", "metadata", "history"])
    result = history_metric.evaluate(snapshot)
    assert result.score == 1.0
    assert result.passed is True


def test_memory_drift_empty_fact_is_not_applicable() -> None:
    """Un fact vacío no se rastrea: la métrica lo trata como 'no aplica' y pasa."""
    metric = MemoryDriftMetric(fact="")
    result = metric.evaluate({"project_metadata": {}})
    assert result.score == 1.0
    assert result.passed is True
    assert result.details["reason"] == "no_fact_to_track"
