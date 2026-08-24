"""Tests de los schemas de generación (sesión 11): la regla de integridad grounded/sources.

Matemática pura de validación (sin red): comprobamos que Pydantic rechaza las
combinaciones prohibidas — que son las que Instructor forzaría a corregir al LLM.
"""

import pytest
from pydantic import ValidationError

from app.generation.schemas import (
    Estimate,
    EstimateLineItem,
    SourceReference,
)


def _src(chunk_id="BUD-2024-014::AUTH-001"):
    return SourceReference(chunk_id=chunk_id, document_id="BUD-2024-014", evidence="120h")


def test_grounded_line_requires_a_source() -> None:
    with pytest.raises(ValidationError):
        EstimateLineItem(component="auth", hours=120, rationale="r", grounded=True, sources=[])


def test_grounded_line_with_source_is_valid() -> None:
    li = EstimateLineItem(
        component="auth", hours=120, rationale="r", grounded=True, sources=[_src()]
    )
    assert li.grounded and li.sources[0].evidence == "120h"


def test_ungrounded_line_cannot_invent_hours() -> None:
    with pytest.raises(ValidationError):
        EstimateLineItem(component="ml", hours=40, rationale="guess", grounded=False)


def test_ungrounded_line_cannot_carry_sources() -> None:
    with pytest.raises(ValidationError):
        EstimateLineItem(
            component="ml", hours=0, rationale="x", grounded=False, sources=[_src()]
        )


def test_ungrounded_line_zero_hours_is_valid() -> None:
    li = EstimateLineItem(
        component="ml", hours=0, rationale="insufficient historical data", grounded=False
    )
    assert not li.grounded and li.hours == 0 and li.sources == []


def test_estimate_total_must_match_line_sum() -> None:
    good = EstimateLineItem(
        component="auth", hours=120, rationale="r", grounded=True, sources=[_src()]
    )
    with pytest.raises(ValidationError):
        Estimate(line_items=[good], total_hours=200, summary="s")


def test_estimate_total_matches_and_as_text() -> None:
    grounded = EstimateLineItem(
        component="auth", hours=120, rationale="oauth backend", grounded=True, sources=[_src()]
    )
    insufficient = EstimateLineItem(
        component="ml recommender", hours=0, rationale="insufficient historical data",
        grounded=False,
    )
    est = Estimate(line_items=[grounded, insufficient], total_hours=120, summary="summary")
    text = est.as_text()
    assert "auth: 120h" in text
    assert "ml recommender: insufficient data" in text
    assert "Total: 120h" in text
