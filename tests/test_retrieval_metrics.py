"""Tests de la métrica de recuperación precisión@k (sesión 10). Sin BBDD: pura.

También validamos que el golden set es coherente (ids únicos, presupuestos relevantes
no vacíos), porque un golden set mal anotado invalidaría toda la medición.
"""

import pytest

from evals.retrieval.golden_set import GOLDEN_SET
from evals.retrieval.metrics import mean, precision_at_k


def test_precision_all_relevant() -> None:
    assert precision_at_k(["A", "A", "B", "A", "B"], {"A", "B"}, 5) == 1.0


def test_precision_none_relevant() -> None:
    assert precision_at_k(["X", "Y", "Z"], {"A"}, 5) == 0.0


def test_precision_partial_divides_by_k_not_by_returned() -> None:
    """3 relevantes entre los 5 primeros -> 0.6, aunque devuelva menos de 5."""
    assert precision_at_k(["A", "A", "A"], {"A"}, 5) == pytest.approx(0.6)


def test_precision_respects_k_cutoff() -> None:
    """Un relevante en posición 6 NO cuenta para precisión@5."""
    retrieved = ["X", "X", "X", "X", "X", "A"]
    assert precision_at_k(retrieved, {"A"}, 5) == 0.0


def test_precision_k_must_be_positive() -> None:
    with pytest.raises(ValueError):
        precision_at_k(["A"], {"A"}, 0)


def test_mean_empty_is_zero() -> None:
    assert mean([]) == 0.0
    assert mean([0.2, 0.8]) == pytest.approx(0.5)


def test_golden_set_is_well_formed() -> None:
    ids = [gq.id for gq in GOLDEN_SET]
    assert len(ids) == len(set(ids)), "ids de consulta duplicados"
    assert len(GOLDEN_SET) == 5
    for gq in GOLDEN_SET:
        assert gq.query.strip(), f"{gq.id} sin texto de consulta"
        assert gq.relevant_budget_ids, f"{gq.id} sin presupuestos relevantes"
        assert all(b.startswith("BUD-") for b in gq.relevant_budget_ids)
