"""Capa de acceso a la base de datos (sesión 08): SQLAlchemy 2.0 async + asyncpg.

Expone tres cosas:
  - Base: la clase declarativa de la que heredan los modelos ORM (Document, Chunk).
  - engine / async_session_maker: el motor async y la fábrica de sesiones.
  - get_session: dependencia de FastAPI que abre una sesión async por request y la
    cierra al terminar (patrón "una sesión por request").

El motor se crea de forma PEREZOSA (create_async_engine no conecta hasta la primera
query), así que importar este módulo NO requiere que Postgres esté levantado — es lo
que permite que la app y los tests (que sustituyen get_session) importen sin BBDD.

No creamos las tablas aquí: el esquema lo gestiona Alembic (migraciones). La app
asume una BBDD ya migrada.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Base declarativa común a todos los modelos ORM del proyecto."""


@lru_cache
def get_engine() -> AsyncEngine:
    """Motor async (cacheado como singleton de proceso).

    pool_pre_ping evita servir conexiones muertas tras un reinicio de Postgres.
    """
    settings = get_settings()
    return create_async_engine(settings.database_url, pool_pre_ping=True)


@lru_cache
def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Fábrica de sesiones async (cacheada). expire_on_commit=False para poder leer
    los objetos después del commit sin disparar un refresh (que requeriría I/O)."""
    return async_sessionmaker(
        bind=get_engine(), expire_on_commit=False, class_=AsyncSession
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependencia FastAPI: una sesión async por request, cerrada al terminar.

    Los tests la sobreescriben (app.dependency_overrides[get_session]) para no tocar
    una BBDD real.
    """
    async with get_session_maker()() as session:
        yield session
