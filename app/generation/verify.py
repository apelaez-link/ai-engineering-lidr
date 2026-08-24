"""Verificación de citaciones tras la generación (sesión 11).

Recorre todas las líneas de la estimación y comprueba que cada chunk_id citado EXISTE
en el conjunto de chunks que de verdad se le entregó al LLM. Una cita a un id que no
estaba en el contexto es una "citación colgante": el modelo se inventó la procedencia.
Es un fallo de calidad, no un detalle cosmético, así que lo dejamos VISIBLE (informe +
log correlacionado por request_id).

La función es pura y testeable (no toca red ni BBDD): recibe la estimación y el conjunto
de ids recuperados, y devuelve un CitationReport. El logging es un efecto lateral opcional
que no altera el valor devuelto.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.logging_config import get_logger

from .schemas import (
    CitationReport,
    CitationStatus,
    Estimate,
    LineCitationResult,
)

logger = get_logger(component="citation_verifier")


def verify_citations(
    estimate: Estimate,
    retrieved_chunk_ids: Iterable[str],
    request_id: str | None = None,
) -> CitationReport:
    """Verifica que las citas de cada línea apunten a chunks realmente recuperados.

    Args:
        estimate: la estimación generada, con sus líneas y fuentes.
        retrieved_chunk_ids: ids de los chunks que se pasaron al generador (verdad).
        request_id: para correlacionar el log (observabilidad).

    Returns:
        CitationReport con el desglose grounded / dangling / insufficient por línea.
    """
    available = set(retrieved_chunk_ids)
    results: list[LineCitationResult] = []
    grounded = dangling = insufficient = 0

    for line in estimate.line_items:
        if not line.grounded:
            insufficient += 1
            results.append(
                LineCitationResult(
                    component=line.component, status=CitationStatus.INSUFFICIENT
                )
            )
            continue

        cited = [s.chunk_id for s in line.sources]
        missing = [cid for cid in cited if cid not in available]
        if missing:
            dangling += 1
            status = CitationStatus.DANGLING
        else:
            grounded += 1
            status = CitationStatus.GROUNDED
        results.append(
            LineCitationResult(
                component=line.component,
                status=status,
                cited_chunk_ids=cited,
                dangling_chunk_ids=missing,
            )
        )

    report = CitationReport(
        total_lines=len(estimate.line_items),
        grounded=grounded,
        dangling=dangling,
        insufficient=insufficient,
        results=results,
    )

    # Log correlacionado. Las citaciones colgantes se registran como WARNING, con el
    # componente y los ids inventados, para que salten en la observabilidad.
    logger.info(
        "citations_verified",
        request_id=request_id,
        total_lines=report.total_lines,
        grounded=report.grounded,
        dangling=report.dangling,
        insufficient=report.insufficient,
    )
    if report.has_dangling:
        for r in report.results:
            if r.status is CitationStatus.DANGLING:
                logger.warning(
                    "dangling_citation",
                    request_id=request_id,
                    component=r.component,
                    dangling_chunk_ids=r.dangling_chunk_ids,
                )
    return report
