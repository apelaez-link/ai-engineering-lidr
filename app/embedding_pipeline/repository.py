"""Operaciones de persistencia y búsqueda sobre documents/chunks (sesión 08).

Aísla el SQL/ORM async del router. El router orquesta (HTTP, códigos de estado,
llamadas al chunker/embedder) y delega aquí el acceso a datos. Esta separación hace
el router testeable sin BBDD (los tests parchean estas funciones) y estas funciones
testeables contra un Postgres real (tests marcados skipif sin BBDD).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Text, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models_db import FULLTEXT_CONFIG, Chunk, Document
from .schemas import EmbeddedChunk


def _or_tsquery(config: str, query_text: str):
    """Construye una tsquery OR a partir de una consulta en lenguaje natural.

    plainto_tsquery une los términos con AND ('mobile & banking & oauth'), así que una
    frase larga solo casa con un chunk que contenga TODAS las palabras — en la práctica,
    ninguno, y la búsqueda léxica devuelve vacío. Para recuperación por palabras clave
    queremos lo contrario: que casen los chunks con CUALQUIER término. Convertimos la
    salida de plainto (ya normalizada: stemming + stop-words) cambiando ' & ' por ' | '.
    Así reutilizamos el análisis léxico correcto de Postgres y obtenemos matching OR,
    que sigue aprovechando el índice GIN vía el operador @@.
    """
    plain_text = cast(func.plainto_tsquery(config, query_text), Text)
    or_text = func.replace(plain_text, " & ", " | ")
    return func.to_tsquery(config, or_text)


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


async def lexical_search_chunks(
    session: AsyncSession, query_text: str, k: int, config: str = FULLTEXT_CONFIG
) -> list[dict[str, Any]]:
    """Mitad LÉXICA de la búsqueda híbrida (sesión 10): full-text search de Postgres.

    Complementa a search_chunks (semántica). Donde el vector captura significado
    ("banca móvil" ~ "mobile banking"), el full-text captura coincidencia EXACTA de
    términos (nombres propios, siglas, IDs, tecnologías) que el embedding a veces diluye.

    - _or_tsquery(config, q): normaliza la consulta con el análisis léxico de Postgres
      (mismo stemming/stop-words que la columna generada) pero uniendo los términos con
      OR, para que casen los chunks con CUALQUIER término (ver la función para el porqué).
    - `content_tsv @@ tsquery`: filtro de match (usa el índice GIN de la migración 0002).
    - ts_rank_cd: ranking por densidad de cobertura (cuántos términos casan y lo juntos
      que aparecen). Ordenamos DESC y devolvemos el `rank` como score léxico.

    Devuelve la MISMA forma de dict que search_chunks (con `rank` en vez de `distance`)
    para que la fusión RRF trate ambas listas de forma homogénea.
    """
    tsquery = _or_tsquery(config, query_text)
    rank = func.ts_rank_cd(Chunk.content_tsv, tsquery).label("rank")
    stmt = (
        select(
            Chunk.id,
            Chunk.document_id,
            Chunk.chunk_type,
            Chunk.content,
            Chunk.meta_,
            rank,
        )
        .where(Chunk.content_tsv.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(k)
    )
    result = await session.execute(stmt)
    return [
        {
            "chunk_id": row.id,
            "document_id": row.document_id,
            "chunk_type": row.chunk_type,
            "content": row.content,
            "rank": float(row.rank),
            "metadata": row.meta_,
        }
        for row in result
    ]
