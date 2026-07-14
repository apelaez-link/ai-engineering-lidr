"""Router del pipeline de embeddings (sesión 07): POST /embeddings/ingest.

Orquesta la secuencia mínima: chunker.chunk(budgets) -> embedder.embed_many(chunks)
-> ensamblar IngestResponse con las estadísticas agregadas.

Se registra en main.py bajo el prefijo /embeddings, así que la ruta completa queda
POST /embeddings/ingest y aparece en /docs (Swagger).

El embedder se inyecta como dependencia de FastAPI (get_embedder) para que los tests
puedan sustituirlo por un doble sin tocar la red (app.dependency_overrides).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.logging_config import get_logger

from .chunker import JSONStructuralChunker
from .embedder import OpenAIEmbedder, estimate_cost_usd
from .schemas import IngestRequest, IngestResponse, IngestStats

logger = get_logger(component="embeddings_router")

router = APIRouter(tags=["embeddings"])

# El chunker no toca la red ni necesita API key: una instancia de módulo basta.
_chunker = JSONStructuralChunker()


def get_embedder() -> OpenAIEmbedder:
    """Dependencia: construye el embedder real (con la API key del .env).

    Los tests la sobrescriben con app.dependency_overrides[get_embedder] para inyectar
    un embedder falso y evitar llamadas reales a la API.
    """
    return OpenAIEmbedder()


@router.post("/ingest", response_model=IngestResponse)
def ingest(
    request: IngestRequest,
    embedder: OpenAIEmbedder = Depends(get_embedder),
) -> IngestResponse:
    """Trocea los presupuestos, vectoriza los chunks y devuelve vectores + estadísticas.

    - 200: éxito.
    - 422: validación Pydantic fallida (lo gestiona FastAPI automáticamente).
    - 500: error no controlado de la API de embeddings (mensaje genérico al cliente,
      detalle en los logs).
    """
    chunks = _chunker.chunk(request.budgets)

    try:
        embedded = embedder.embed_many(chunks)
    except Exception as exc:  # noqa: BLE001 — traducimos cualquier fallo de la API a 500
        logger.error("embeddings_ingest_failed", error=str(exc))
        raise HTTPException(
            status_code=500, detail="Error generando los embeddings."
        ) from exc

    total_tokens = sum(chunk.token_count for chunk in chunks)
    stats = IngestStats(
        total_budgets=len(request.budgets),
        total_chunks=len(embedded),
        total_tokens=total_tokens,
        estimated_cost_usd=round(estimate_cost_usd(total_tokens), 6),
    )
    logger.info(
        "embeddings_ingest_completed",
        total_budgets=stats.total_budgets,
        total_chunks=stats.total_chunks,
        total_tokens=stats.total_tokens,
        estimated_cost_usd=stats.estimated_cost_usd,
    )
    return IngestResponse(chunks=embedded, stats=stats)
