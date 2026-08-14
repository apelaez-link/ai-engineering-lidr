"""Entorno de migraciones Alembic (sesión 08), configurado para async + pgvector.

Diferencias respecto a la plantilla por defecto de Alembic:
  - La URL de conexión se toma de la variable de entorno DATABASE_URL (o, en su
    defecto, de app.config), no de alembic.ini. Así no versionamos credenciales.
  - Se ejecuta con un motor ASYNC (asyncpg), igual que la app.
  - Se registra el tipo `vector` de pgvector en el dialecto, para que la
    autogeneración de migraciones (alembic revision --autogenerate / alembic check)
    reconozca las columnas Vector y no produzca migraciones inconsistentes.
"""

from __future__ import annotations

import asyncio
import os

import pgvector.sqlalchemy
from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool

# Importa la Base y los modelos para que Base.metadata conozca las tablas.
from app.config import get_settings
from app.db import Base
from app.embedding_pipeline import models_db  # noqa: F401 — registra Document/Chunk

config = context.config

# URL de conexión: DATABASE_URL del entorno tiene prioridad; si no, la de settings.
_database_url = os.getenv("DATABASE_URL") or get_settings().database_url
config.set_main_option("sqlalchemy.url", _database_url)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    # Registra el tipo vector para que la reflexión/autogeneración lo reconozca.
    connection.dialect.ischema_names["vector"] = pgvector.sqlalchemy.Vector
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    """Modo offline: emite SQL sin conectar (genera scripts)."""
    context.configure(
        url=_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
