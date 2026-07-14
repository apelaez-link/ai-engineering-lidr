"""Operaciones de persistencia y búsqueda sobre documents/chunks (sesión 08).

Aísla el SQL/ORM async del router. El router orquesta (HTTP, códigos de estado,
llamadas al chunker/embedder) y delega aquí el acceso a datos. Esta separación hace
el router testeable sin BBDD (los tests parchean estas funciones) y estas funciones
testeables contra un Postgres real (tests marcados skipif sin BBDD).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models_db import Chunk, Document
from .schemas import EmbeddedChunk


async def get_document_id_by_source(
    session: AsyncSession, source_path: str
) -> int | None:
    """Devuelve el id del documento con ese source_path, o None si no existe.

    Sostiene la regla de idempotencia del endpoint: no re-ingestar dos veces el mismo
    fichero (responde 409 con el id existente).
    """
    result = await session.execute(
        select(Document.id).where(Document.source_path == source_path)
    )
    return result.scalar_one_or_none()


async def persist_document(
    session: AsyncSession,
    source_path: str,
    document_type: str,
    document_metadata: dict[str, Any],
    embedded_chunks: list[EmbeddedChunk],
    chunk_type: str = "budget_component",
) -> int:
    """Persiste un documento y sus chunks (con embeddings) en UNA transacción.

    Atomicidad: si algo falla, no queda un `document` huérfano sin chunks. El id del
    document se genera en el flush; las filas de chunks lo referencian por FK.

    En el `metadata` de cada chunk guardamos, además de la metadata filtrable del
    chunker, el `chunk_id` trazable ({budget_id}::{component_id}) y el token_count.
    """
    document = Document(
        source_path=source_path,
        document_type=document_type,
        meta_=document_metadata,
    )
    session.add(document)
    await session.flush()  # asigna document.id sin cerrar la transacción

    for ec in embedded_chunks:
        session.add(
            Chunk(
                document_id=document.id,
                chunk_type=chunk_type,
                content=ec.text,
                embedding=ec.embedding,
                meta_={
                    **ec.metadata,
                    "chunk_id": ec.chunk_id,
                    "token_count": ec.token_count,
                },
            )
        )

    await session.commit()
    return document.id


async def search_chunks(
    session: AsyncSession, query_vector: list[float], k: int
) -> list[dict[str, Any]]:
    """Devuelve los k chunks más cercanos por DISTANCIA COSENO (operador <=>).

    Usamos cosine_distance (que se traduce a <=>) para alinear con la operator class
    que tendrá el índice HNSW del directo (vector_cosine_ops). Sin índice todavía,
    Postgres hace sequential scan: correcto y suficiente para el volumen del corpus.
    """
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
    stmt = (
        select(
            Chunk.id,
            Chunk.document_id,
            Chunk.chunk_type,
            Chunk.content,
            Chunk.meta_,
            distance,
        )
        # La columna embedding es NULLABLE (permite ingesta async futura). Un chunk sin
        # embedding daría distancia NULL: lo excluimos para no devolver "no-resultados"
        # ni romper el float() de la distancia si entrara en el top-k.
        .where(Chunk.embedding.is_not(None))
        .order_by(distance)
        .limit(k)
    )
    result = await session.execute(stmt)
    return [
        {
            "chunk_id": row.id,
            "document_id": row.document_id,
            "chunk_type": row.chunk_type,
            "content": row.content,
            "distance": float(row.distance),
            "metadata": row.meta_,
        }
        for row in result
    ]
