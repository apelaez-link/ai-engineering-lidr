"""Tests puros del generador (sesión 11): formateo de contexto e ids recuperados.

No llaman al LLM (eso se prueba a mano / en el eval). Fijan que el contexto que ve el
modelo lleva los ids trazables y que retrieved_chunk_ids coincide con lo que verify usa.
"""

from app.generation.generator import _format_context, retrieved_chunk_ids
from evals.generation.golden_set import GENERATION_GOLDEN_SET


def _row(cid, budget, content):
    return {
        "chunk_id": 1,
        "document_id": 5,
        "content": content,
        "metadata": {"chunk_id": cid, "budget_id": budget},
    }


def test_format_context_includes_traceable_ids() -> None:
    rows = [_row("BUD-1::A", "BUD-1", "Cart and checkout. Estimated hours: 160")]
    ctx = _format_context(rows)
    assert "chunk_id=BUD-1::A" in ctx
    assert "document_id=BUD-1" in ctx
    assert "Estimated hours: 160" in ctx


def test_retrieved_chunk_ids_matches_metadata() -> None:
    rows = [_row("BUD-1::A", "BUD-1", "x"), _row("BUD-2::B", "BUD-2", "y")]
    assert retrieved_chunk_ids(rows) == {"BUD-1::A", "BUD-2::B"}


def test_generation_golden_set_is_well_formed() -> None:
    assert len(GENERATION_GOLDEN_SET) == 5
    for gq in GENERATION_GOLDEN_SET:
        assert gq.query.strip()
        assert gq.ground_truth.strip(), f"{gq.id} sin ground_truth"
        assert gq.relevant_budget_ids
