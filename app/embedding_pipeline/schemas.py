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


# ── Contrato HTTP del endpoint POST /embeddings/ingest ───────────────────────────


class IngestRequest(BaseModel):
    """Payload de entrada: una lista de presupuestos a vectorizar."""

    budgets: list[Budget]


class IngestStats(BaseModel):
    """Estadísticas agregadas de una ingesta (útiles para el cliente y para logs)."""

    total_budgets: int
    total_chunks: int
    total_tokens: int
    estimated_cost_usd: float


class IngestResponse(BaseModel):
    """Payload de salida: los chunks vectorizados + las estadísticas de la ingesta."""

    chunks: list[EmbeddedChunk]
    stats: IngestStats
