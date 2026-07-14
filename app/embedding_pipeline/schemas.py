"""Modelos Pydantic v2 del pipeline de embeddings (sesión 07).

Contrato de datos del pipeline, de entrada a salida:

    IngestRequest(budgets)  --chunker-->  list[Chunk]  --embedder-->  list[EmbeddedChunk]
                                                                          |
                                                                    IngestResponse(chunks, stats)

Seguimos la convención del proyecto: Pydantic v2, nombres en inglés, validadores
explícitos donde aportan (complexity como Literal cerrado; sector lo dejamos abierto
porque el universo de sectores crece con cada cliente nuevo).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# Niveles de complejidad de un componente. SÍ es un universo cerrado y conocido, así
# que lo fijamos como Literal: un JSON con complexity="huge" falla la validación (422)
# en lugar de colarse como dato sucio hasta el embedding.
Complexity = Literal["low", "medium", "high"]


# ── Entrada: el presupuesto tal como lo dejó la sesión 06 ────────────────────────


class ClientMetadata(BaseModel):
    """Metadatos del cliente dueño del presupuesto."""

    name: str
    # sector NO es Literal a propósito: es abierto (finance, ecommerce, healthcare,
    # industrial, y los que vengan). Va como filtro en el metadata del chunk.
    sector: str
    country: str


class BudgetComponent(BaseModel):
    """Un componente (unidad lógica de negocio) dentro de un presupuesto.

    Es la granularidad del chunking: un componente = un chunk.
    """

    component_id: str
    name: str
    description: str
    tech_stack: list[str] = Field(default_factory=list)
    estimated_hours: int = Field(ge=0)
    complexity: Complexity
    # Dependencias hacia otros component_id del mismo presupuesto. No se embeben; las
    # conservamos por fidelidad al dato de la sesión 06 (podrían usarse en retrieval).
    dependencies: list[str] = Field(default_factory=list)


class Budget(BaseModel):
    """Un presupuesto histórico completo (el documento padre del chunking)."""

    budget_id: str
    client_metadata: ClientMetadata
    project_summary: str
    main_technology: str
    year: int
    total_estimated_hours: int = Field(ge=0)
    components: list[BudgetComponent]


# ── Piezas del pipeline: chunk sin y con embedding ───────────────────────────────


class Chunk(BaseModel):
    """Un fragmento listo para embeber.

    - text: la representación textual que SÍ se vectoriza (incluye el header
      contextual del presupuesto padre).
    - metadata: campos filtrables que NO se embeben pero viajan con el chunk
      (para filtrar en la BBDD vectorial de la sesión 08 y para devolver al cliente).
    - chunk_id: identificador trazable "{budget_id}::{component_id}".
    - token_count: nº de tokens del text (contados con tiktoken), para detectar
      chunks anormalmente grandes antes de mandarlos a la API.
    """

    chunk_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    token_count: int = Field(ge=0)


class EmbeddedChunk(Chunk):
    """Un Chunk ya vectorizado: extiende Chunk con su vector de embedding."""

    embedding: list[float]


# ── Contrato HTTP de POST /embeddings/ingest (sesión 08: persiste, no devuelve vectores) ──


class IngestRequest(BaseModel):
    """Payload de entrada: UN documento (un presupuesto) a persistir.

    Cambia respecto a la sesión 07 (que recibía una lista y devolvía los vectores):
    ahora un documento = un source_path único = un presupuesto. `content` es el JSON
    completo del presupuesto, que el chunker trocea internamente.
    """

    source_path: str = Field(description="Ruta/identificador único del documento origen.")
    document_type: str = Field(description="Tipo de documento, p.ej. 'historical_budget'.")
    content: Budget = Field(description="El presupuesto completo (JSON) a trocear y vectorizar.")


class IngestResponse(BaseModel):
    """Payload de salida (200): identificadores y métricas de la ingesta persistida."""

    document_id: int
    chunks_created: int
    embedding_dimension: int
    ingestion_time_ms: int


class DuplicateResponse(BaseModel):
    """Payload de salida (409): el documento ya existía; devolvemos su id."""

    detail: str = "Document already ingested"
    document_id: int


# ── Contrato HTTP de POST /search (sesión 08) ────────────────────────────────────


class SearchRequest(BaseModel):
    """Payload de entrada: una consulta en lenguaje natural y cuántos resultados."""

    query: str
    k: int = Field(default=5, ge=1, le=50)


class SearchResultItem(BaseModel):
    """Un chunk recuperado, con su distancia coseno a la consulta."""

    chunk_id: int
    document_id: int
    chunk_type: str
    content: str
    distance: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Payload de salida: la consulta, sus parámetros y los resultados ordenados."""

    query: str
    k: int
    search_time_ms: int
    results: list[SearchResultItem]
