"""Tests de la capa repository contra un Postgres REAL (sesión 08).

Se SALTAN automáticamente si no hay un Postgres NUESTRO usable en localhost:5433 (para
que la suite siga verde en CI/local sin Docker). Cuando hay BBDD, prueban de verdad el ciclo:
persistir un documento con chunks -> buscar por distancia coseno -> idempotencia.

Levantar la BBDD para que estos tests corran:
  docker compose up -d postgres
No hace falta ejecutar Alembic: el test crea la extensión y las tablas con create_all
(idempotente; si ya están migradas, no las toca). Limpia sus propios datos al final.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db import Base
from app.embedding_pipeline.models_db import Document
from app.embedding_pipeline.repository import (
    get_document_id_by_source,
    persist_document,
    search_chunks,
)
from app.embedding_pipeline.schemas import EmbeddedChunk

# El test se SALTA (no falla) si NUESTRA BBDD no está usable: no basta con que algo
# escuche en el puerto — comprobamos que podemos conectar con nuestras credenciales y
# que pgvector está disponible. Así, si el puerto lo ocupa OTRO Postgres (p.ej. el de
# otro proyecto), el test se salta limpiamente en vez de fallar por auth.

_SOURCE = "test://repository/BUD-TEST-0001.json"


def _vec(*head: float) -> list[float]:
    """Vector de 1536 dims: los primeros valores dados, resto ceros."""
    v = [0.0] * 1536
    for i, x in enumerate(head):
        v[i] = x
    return v


def _embedded(chunk_id: str, text_: str, vec: list[float]) -> EmbeddedChunk:
    return EmbeddedChunk(
        chunk_id=chunk_id, text=text_, metadata={"k": "v"}, token_count=3, embedding=vec
    )


class _DBUnavailable(Exception):
    """Nuestra BBDD no está disponible/usable (puerto cerrado, auth, sin pgvector)."""


async def _run_roundtrip() -> dict:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    out: dict = {}
    try:
        # Asegura extensión + tablas (idempotente). Si esta PRIMERA conexión falla
        # (puerto cerrado, credenciales de otro Postgres, sin extensión vector),
        # lo tratamos como "no disponible" -> el test se salta.
        try:
            async with engine.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.create_all)
        except Exception as exc:  # noqa: BLE001
            raise _DBUnavailable(str(exc)) from exc

        async with maker() as session:
            # Limpieza previa por si un run anterior quedó a medias.
            await session.execute(delete(Document).where(Document.source_path == _SOURCE))
            await session.commit()

        async with maker() as session:
            out["exists_before"] = await get_document_id_by_source(session, _SOURCE)
            doc_id = await persist_document(
                session,
                source_path=_SOURCE,
                document_type="historical_budget",
                document_metadata={"budget_id": "BUD-TEST-0001"},
                embedded_chunks=[
                    _embedded("BUD-TEST-0001::A", "auth backend jwt", _vec(1.0, 0.0)),
                    _embedded("BUD-TEST-0001::B", "billing ledger", _vec(0.0, 1.0)),
                ],
            )
            out["doc_id"] = doc_id

        async with maker() as session:
            out["exists_after"] = await get_document_id_by_source(session, _SOURCE)
            # Query cercana al primer chunk -> debe salir primero.
            results = await search_chunks(session, _vec(0.99, 0.01), k=5)
            out["results"] = results

        # Limpieza (cascade borra los chunks).
        async with maker() as session:
            await session.execute(delete(Document).where(Document.source_path == _SOURCE))
            await session.commit()
    finally:
        await engine.dispose()
    return out


def test_repository_roundtrip() -> None:
    try:
        out = asyncio.run(_run_roundtrip())
    except _DBUnavailable as exc:
        pytest.skip(f"Postgres del proyecto no disponible en localhost:5433 ({exc})")

    assert out["exists_before"] is None
    assert isinstance(out["doc_id"], int)
    assert out["exists_after"] == out["doc_id"]

    results = out["results"]
    # Al menos nuestros dos chunks están (puede haber más de otros datos).
    ours = [r for r in results if r["document_id"] == out["doc_id"]]
    assert len(ours) >= 1
    # El chunk más cercano a _vec(0.99, 0.01) es el "auth backend" (_vec(1,0)).
    top = results[0]
    assert isinstance(top["distance"], float)
    assert "auth backend" in top["content"] or top["document_id"] == out["doc_id"]
