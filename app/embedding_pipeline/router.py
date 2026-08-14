"""Router del pipeline de embeddings (sesión 08): persistencia + búsqueda semántica.

Dos endpoints, ambos async y transaccionales sobre PostgreSQL + pgvector:

  POST /embeddings/ingest  -> trocea un presupuesto, embebe sus chunks y los PERSISTE
                              (document + chunks) en una sola transacción. 409 si el
                              source_path ya existe.
  POST /search             -> embebe la query y devuelve los k chunks más cercanos por
                              distancia coseno.

Cambio respecto a la sesión 07: ingest ya no devuelve los vectores en la respuesta;
los guarda y devuelve identificadores + métricas. La sesión 07 vivía en memoria; ésta
persiste.

El session (AsyncSession) y el embedder se inyectan como dependencias para que los
tests los sustituyan sin tocar la BBDD ni la API real.
"""

from __future__ import annotations

import time
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.logging_config import get_logger

from . import repository
from .chunker import JSONStructuralChunker
from .embedder import EMBEDDING_DIMENSIONS, OpenAIEmbedder
from .hybrid import hybrid_search
from .reranker import CrossEncoderReranker
from .schemas import (
    IngestRequest,
    IngestResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)

logger = get_logger(component="embeddings_router")

router = APIRouter(tags=["embeddings"])

# El chunker no toca la red ni la BBDD: una instancia de módulo basta.
_chunker = JSONStructuralChunker()


def get_embedder() -> OpenAIEmbedder:
    """Dependencia: construye el embedder real (API key del .env). Los tests la
    sobreescriben con app.dependency_overrides[get_embedder]."""
    return OpenAIEmbedder()


@lru_cache
def get_reranker() -> CrossEncoderReranker:
    """Dependencia: cross-encoder cacheado como singleton de proceso (el modelo se
    carga perezosamente en la primera llamada a rerank, no aquí). Solo se instancia si
    alguna petición pide rerank; las peticiones sin rerank no lo tocan."""
    return CrossEncoderReranker(model_name=get_settings().rerank_model)


@router.post("/embeddings/ingest", response_model=IngestResponse)
async def ingest(
    request: IngestRequest,
    session: AsyncSession = Depends(get_session),
    embedder: OpenAIEmbedder = Depends(get_embedder),
):
    """Persiste un presupuesto (document + chunks vectorizados) atómicamente.

    - 200: ingesta correcta (IngestResponse con document_id y métricas).
    - 409: ya existe un documento con ese source_path (detail + document_id).
    - 422: validación Pydantic (lo gestiona FastAPI).
    - 500: error no controlado de la API de embeddings o de la BBDD.
    """
    started = time.perf_counter()

    # 1) Idempotencia: no re-ingestar el mismo fichero dos veces.
    existing_id = await repository.get_document_id_by_source(session, request.source_path)
    if existing_id is not None:
        logger.info(
            "ingest_duplicate", source_path=request.source_path, document_id=existing_id
        )
        return JSONResponse(
            status_code=409,
            content={"detail": "Document already ingested", "document_id": existing_id},
        )

    # 2) Chunk (un presupuesto -> N chunks) y 3) embeber en batch.
    chunks = _chunker.chunk([request.content])
    try:
        embedded = embedder.embed_many(chunks)
    except Exception as exc:  # noqa: BLE001 — fallo de la API de embeddings -> 500
        logger.error("ingest_embedding_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Error generando los embeddings.") from exc

    # 4) Persistir document + chunks en una transacción.
    try:
        document_id = await repository.persist_document(
            session,
            source_path=request.source_path,
            document_type=request.document_type,
            document_metadata={
                "budget_id": request.content.budget_id,
                "client_sector": request.content.client_metadata.sector,
                "main_technology": request.content.main_technology,
                "year": request.content.year,
            },
            embedded_chunks=embedded,
        )
    except Exception as exc:  # noqa: BLE001 — fallo de BBDD -> 500 (transacción revertida)
        await session.rollback()
        logger.error("ingest_persist_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Error persistiendo el documento.") from exc

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "ingest_completed",
        document_id=document_id,
        chunks_created=len(embedded),
        ingestion_time_ms=elapsed_ms,
    )
    return IngestResponse(
        document_id=document_id,
        chunks_created=len(embedded),
        embedding_dimension=EMBEDDING_DIMENSIONS,
        ingestion_time_ms=elapsed_ms,
    )


@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    session: AsyncSession = Depends(get_session),
    embedder: OpenAIEmbedder = Depends(get_embedder),
) -> SearchResponse:
    """Búsqueda de chunks con recuperación configurable (sesión 10).

    Cuatro combinaciones, elegibles por petición sin tocar código:
      mode=vector | hybrid    ×    rerank=false | true

    Patrón recall-then-rerank: si rerank está activo, la recuperación trae un pool
    ANCHO de candidatos (retrieval_candidate_pool) y el cross-encoder los reordena al
    top-k; si no, la recuperación devuelve directamente el top-k.

    La query se embebe con el MISMO modelo que la ingesta (text-embedding-3-small),
    condición necesaria para que las distancias sean comparables.
    """
    settings = get_settings()
    do_rerank = settings.rerank_enabled if request.rerank is None else request.rerank
    pool = settings.retrieval_candidate_pool
    # Anchura de recall: si vamos a reordenar, recuperamos `pool`; si no, solo los k.
    recall_k = max(pool, request.k) if do_rerank else request.k

    started = time.perf_counter()

    try:
        query_vector = embedder.embed_one(request.query)
    except Exception as exc:  # noqa: BLE001
        logger.error("search_embedding_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Error embebiendo la consulta.") from exc

    if request.mode == "hybrid":
        rows = await hybrid_search(
            session,
            query_vector,
            request.query,
            k=recall_k,
            candidate_pool=pool,
            rrf_k=settings.rrf_k,
            fulltext_config=settings.fulltext_language,
        )
    else:
        rows = await repository.search_chunks(session, query_vector, recall_k)

    if do_rerank:
        reranker = get_reranker()
        rows = reranker.rerank(request.query, rows, request.k)

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    logger.info(
        "search_completed",
        query_chars=len(request.query),
        k=request.k,
        mode=request.mode,
        reranked=do_rerank,
        results=len(rows),
        search_time_ms=elapsed_ms,
    )
    return SearchResponse(
        query=request.query,
        k=request.k,
        mode=request.mode,
        reranked=do_rerank,
        search_time_ms=elapsed_ms,
        results=[SearchResultItem(**row) for row in rows],
    )
