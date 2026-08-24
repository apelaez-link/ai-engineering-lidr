"""Tests de verify_citations (sesión 11): detección de citaciones colgantes. Puro, sin red."""

from app.generation.schemas import Estimate, EstimateLineItem, SourceReference
from app.generation.verify import verify_citations


def _line(component, chunk_id=None, hours=10.0):
    if chunk_id is None:
        return EstimateLineItem(
            component=component, hours=0, rationale="insufficient historical data",
            grounded=False,
        )
    return EstimateLineItem(
        component=component, hours=hours, rationale="r", grounded=True,
        sources=[SourceReference(chunk_id=chunk_id, document_id="BUD-1", evidence="x")],
    )


def test_all_grounded_no_dangling() -> None:
    est = Estimate(
        line_items=[_line("auth", "c1", 120), _line("api", "c2", 80)],
        total_hours=200, summary="s",
    )
    report = verify_citations(est, {"c1", "c2", "c3"})
    assert report.grounded == 2
    assert report.dangling == 0
    assert report.insufficient == 0
    assert report.has_dangling is False


def test_detects_dangling_citation() -> None:
    # 'c9' NO está en el contexto recuperado -> citación colgante (alucinación).
    est = Estimate(line_items=[_line("auth", "c9", 120)], total_hours=120, summary="s")
    report = verify_citations(est, {"c1", "c2"})
    assert report.dangling == 1
    assert report.has_dangling is True
    assert report.results[0].dangling_chunk_ids == ["c9"]
    assert report.results[0].status.value == "dangling"


def test_insufficient_line_classified() -> None:
    est = Estimate(
        line_items=[_line("auth", "c1", 120), _line("ml", None)],
        total_hours=120, summary="s",
    )
    report = verify_citations(est, {"c1"})
    assert report.grounded == 1
    assert report.insufficient == 1
    assert report.dangling == 0
    statuses = {r.component: r.status.value for r in report.results}
    assert statuses == {"auth": "grounded", "ml": "insufficient"}
