"""Modelos ORM de la persistencia vectorial (sesión 08): documents y chunks.

Diseño de la lección "Diseño del esquema y búsqueda semántica": DOS tablas con una
relación uno-a-muchos (un presupuesto = un document = N chunks), no una sola con la
metadata del documento duplicada en cada chunk.

  documents  1 ──< N  chunks   (ON DELETE CASCADE)

Notas de diseño (justificadas en el README):
  - metadata en JSONB (no columnas): estable en columnas tipadas (document_type,
    chunk_type, fechas); variable/enriquecible en JSONB con índice GIN.
  - embedding vector(1536): dimensión de text-embedding-3-small, hardcodeada
    (cambiarla implica re-embeder todo el corpus). Nullable: permite insertar el
    chunk y rellenar el embedding después (no lo usamos así aquí, pero deja la puerta
    abierta a ingesta asíncrona).
  - Sin índice vectorial (HNSW): deliberado. El directo lo añade y mide su impacto
    contra el sequential scan que hay ahora.

El atributo Python se llama `meta_` (mapeado a la columna SQL `metadata`) porque
`metadata` es un nombre reservado en la clase declarativa de SQLAlchemy.
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

EMBEDDING_DIM = 1536


class Document(Base):
    """Un presupuesto histórico persistido una sola vez, con su metadata."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    meta_: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default="{}", nullable=False
    )

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class Chunk(Base):
    """Un fragmento derivado del chunking de un documento, con su embedding."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )
    meta_: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")
