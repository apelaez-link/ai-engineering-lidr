"""Chunker estructural para presupuestos JSON (sesión 07).

Estrategia de la lección "Chunking del proyecto": la unidad lógica de un presupuesto
es el COMPONENTE, así que **un componente = un chunk**. No partimos el presupuesto
entero (perderíamos especificidad) ni cada campo por separado (perderíamos coherencia).

Tres decisiones explícitas (de la lección):
  1. Granularidad: un componente = un chunk.
  2. Contenido (text): representación legible con un HEADER CONTEXTUAL del presupuesto
     padre prepended (proyecto, sector, año, tecnología principal). Es la versión
     estática y barata de "contextual chunk headers" / Contextual Retrieval: usamos el
     contexto del padre que YA tenemos en el JSON, sin llamar a un LLM. Microsoft Azure
     documentó +15–25 puntos de accuracy de QA solo con esto.
  3. Metadata: campos filtrables que NO se embeben pero viajan con el chunk.

Un umbral de aviso (WARN) detecta descripciones anormalmente largas: la lección pide
NO trocearlas (confiamos en la estructura del JSON), pero sí dejar constancia — es
material de discusión para el directo.
"""

from __future__ import annotations

import tiktoken

from app.logging_config import get_logger

from .schemas import Budget, BudgetComponent, Chunk

logger = get_logger(component="json_chunker")

# Modelo cuyo tokenizador usamos para contar tokens del texto del chunk. Debe coincidir
# con el modelo de embeddings (así el token_count es el que la API va a facturar).
DEFAULT_TOKEN_MODEL = "text-embedding-3-small"

# Por encima de estos tokens, un chunk es "anormalmente grande". No lo troceamos (lo
# dice el enunciado): solo avisamos. text-embedding-3-small admite hasta 8191 tokens,
# así que esto es una alerta de higiene, muy por debajo del límite duro de la API.
LARGE_CHUNK_WARN_TOKENS = 1000


class JSONStructuralChunker:
    """Parte presupuestos en chunks a nivel de componente.

    Cada BudgetComponent se convierte en un Chunk cuyo texto combina los campos del
    componente con un header contextual del presupuesto padre.
    """

    def __init__(self, model_for_token_count: str = DEFAULT_TOKEN_MODEL) -> None:
        # encoding_for_model conoce el tokenizador exacto del modelo; si el nombre no
        # estuviera en la tabla de tiktoken, caemos a cl100k_base (el de la familia 3).
        try:
            self._tokenizer = tiktoken.encoding_for_model(model_for_token_count)
        except KeyError:
            self._tokenizer = tiktoken.get_encoding("cl100k_base")

    def chunk(self, budgets: list[Budget]) -> list[Chunk]:
        """Convierte una lista de presupuestos en una lista plana de chunks."""
        chunks: list[Chunk] = []
        for budget in budgets:
            budget_chunks = self._chunk_one_budget(budget)
            chunks.extend(budget_chunks)
            logger.info(
                "budget_chunked",
                budget_id=budget.budget_id,
                components=len(budget.components),
                chunks=len(budget_chunks),
            )
        logger.info("chunking_completed", budgets=len(budgets), chunks=len(chunks))
        return chunks

    def _chunk_one_budget(self, budget: Budget) -> list[Chunk]:
        parent_context = self._build_parent_context(budget)
        return [
            self._build_chunk(component, budget, parent_context)
            for component in budget.components
        ]

    def _build_parent_context(self, budget: Budget) -> str:
        """Header contextual: las dos líneas entre corchetes que sitúan el componente."""
        client = budget.client_metadata
        return (
            f"[Project: {budget.project_summary}]\n"
            f"[Client sector: {client.sector} | "
            f"Year: {budget.year} | "
            f"Main tech: {budget.main_technology}]"
        )

    def _build_chunk(
        self, component: BudgetComponent, budget: Budget, parent_context: str
    ) -> Chunk:
        text = self._render_component_text(component, parent_context)
        token_count = len(self._tokenizer.encode(text))

        if token_count > LARGE_CHUNK_WARN_TOKENS:
            # No troceamos (lo dice el enunciado): confiamos en la estructura del JSON.
            # Solo dejamos constancia para discutirlo en el directo.
            logger.warning(
                "large_chunk_detected",
                chunk_id=f"{budget.budget_id}::{component.component_id}",
                token_count=token_count,
                threshold=LARGE_CHUNK_WARN_TOKENS,
            )

        return Chunk(
            chunk_id=f"{budget.budget_id}::{component.component_id}",
            text=text,
            metadata=self._build_metadata(component, budget),
            token_count=token_count,
        )

    def _render_component_text(
        self, component: BudgetComponent, parent_context: str
    ) -> str:
        return (
            f"{parent_context}\n\n"
            f"Component: {component.name}\n"
            f"Description: {component.description}\n"
            f"Tech stack: {', '.join(component.tech_stack)}\n"
            f"Complexity: {component.complexity}\n"
            f"Estimated hours: {component.estimated_hours}"
        )

    def _build_metadata(
        self, component: BudgetComponent, budget: Budget
    ) -> dict:
        """Campos filtrables (no se embeben). En la sesión 08 alimentan los filtros SQL."""
        return {
            "budget_id": budget.budget_id,
            "component_id": component.component_id,
            "client_sector": budget.client_metadata.sector,
            "main_technology": budget.main_technology,
            "year": budget.year,
            "complexity": component.complexity,
            "estimated_hours": component.estimated_hours,
        }
