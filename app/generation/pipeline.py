"""Pipeline RAG de extremo a extremo (sesión 11): recuperar → generar → verificar.

Une las tres piezas:
  1. Recuperación (sesión 10): embebe la consulta y trae los k chunks de contexto.
  2. Generación (sesión 11): estima con citación por línea sobre ese contexto.
  3. Verificación (sesión 11): comprueba que ninguna cita sea colgante.

Es la etapa que faltaba en nuestro repo (la "sesión 9 en directo"). La retrieval es async
(I/O a Postgres); la generación es síncrona (Instructor/litellm), así que en un endpoint
con concurrencia habría que despacharla a un thread pool. Aquí, para el eval y el demo,
la llamamos directa dentro del contexto async.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.repository import search_chunks

from .generator import generate_estimate, retrieved_chunk_ids
from .schemas import CitationReport, Estimate
from .verify import verify_citations


@dataclass
class RagEstimateResult:
    """Salida completa del pipeline: la estimación, su informe de citación y el contexto."""

    estimate: Estimate
    citation_report: CitationReport
    retrieved: list[dict[str, Any]]


async def estimate_with_citations(
    session: AsyncSession,
    embedder: OpenAIEmbedder,
    query: str,
    k: int = 8,
    request_id: str | None = None,
) -> RagEstimateResult:
    """Ejecuta recuperar → generar → verificar para una consulta.

    Args:
        session: sesión async de BBDD (retrieval).
        embedder: para embeber la consulta con el mismo modelo de la ingesta.
        query: descripción del proyecto a estimar.
        k: nº de chunks de contexto a recuperar (recall para la generación).
        request_id: correlación de logs.
    """
    query_vector = embedder.embed_one(query)
    retrieved = await search_chunks(session, query_vector, k)
    estimate = generate_estimate(query, retrieved)
    report = verify_citations(estimate, retrieved_chunk_ids(retrieved), request_id=request_id)
    return RagEstimateResult(estimate=estimate, citation_report=report, retrieved=retrieved)
