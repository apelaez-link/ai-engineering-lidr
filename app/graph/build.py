"""Los 5 nodos del grafo (funciones puras) + el cableado del StateGraph (sesión 13).

Grafo:
    START → extract_requirements → classify_components → search_budgets
          → generate_estimate → validate_and_consolidate → (needs_review | END)

Cada nodo es una función que recibe el estado y devuelve una ACTUALIZACIÓN PARCIAL
(solo las claves que cambia). Reutilizan la lógica que ya teníamos: `search_budgets`
envuelve la búsqueda híbrida de S10; `generate_estimate` llama al generador citado de
S11; `validate_and_consolidate` usa la verificación de citaciones de S11. Los nodos son
async (hay I/O a BBDD y a la API del LLM); el trabajo síncrono (litellm/Instructor) se
saca del event loop con `asyncio.to_thread`.

`build_estimation_graph(deps)` define los nodos cerrando sobre `deps` (sesión + embedder)
y devuelve el StateGraph SIN compilar. El llamante lo compila con el checkpointer
(Nivel 2). Cada nodo se envuelve en un span de Logfire (Nivel 2).
"""

from __future__ import annotations

import asyncio
from typing import Any

import instructor
import litellm
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.embedding_pipeline.hybrid import hybrid_search
from app.generation.generator import generate_estimate as rag_generate_estimate
from app.generation.schemas import Estimate
from app.generation.verify import verify_citations
from app.logging_config import get_logger
from app.services.structured import _resolve_primary_model

from .deps import GraphDeps
from .observability import span
from .state import EstimationState

logger = get_logger(component="graph")

litellm.telemetry = False
litellm.drop_params = True


# ── Schemas internos de los pasos LLM (Instructor los fuerza) ────────────────────


class _Requirements(BaseModel):
    """Requisitos funcionales extraídos de la transcripción."""

    requirements: list[str] = Field(
        description="Functional requirements mentioned in the meeting, one per item."
    )


class _ComponentSpec(BaseModel):
    """Un componente del proyecto con una consulta de búsqueda precisa."""

    name: str = Field(description="Short component name, e.g. 'authentication'.")
    search_query: str = Field(
        description="Precise natural-language query to find historical budgets for THIS "
        "component only (one component per query)."
    )


class _Components(BaseModel):
    components: list[_ComponentSpec] = Field(
        description="The project's distinct components, one search query each."
    )


# ── Helpers LLM (síncronos; se llaman con asyncio.to_thread desde los nodos) ─────


def _extract_requirements_llm(transcript: str) -> list[str]:
    model, api_key = _resolve_primary_model()
    client = instructor.from_litellm(litellm.completion)
    result: _Requirements = client.chat.completions.create(
        model=model,
        api_key=api_key,
        temperature=0.2,
        response_model=_Requirements,
        max_retries=2,
        messages=[
            {
                "role": "system",
                "content": "You extract the functional requirements from a client meeting "
                "transcript. List concrete requirements, not pleasantries.",
            },
            {"role": "user", "content": transcript},
        ],
    )
    return result.requirements


def _classify_components_llm(requirements: list[str]) -> list[_ComponentSpec]:
    model, api_key = _resolve_primary_model()
    client = instructor.from_litellm(litellm.completion)
    joined = "\n".join(f"- {r}" for r in requirements)
    result: _Components = client.chat.completions.create(
        model=model,
        api_key=api_key,
        temperature=0.2,
        response_model=_Components,
        max_retries=2,
        messages=[
            {
                "role": "system",
                "content": "Group the requirements into the project's distinct software "
                "COMPONENTS. For each component give a short name and a precise search "
                "query to retrieve historical budgets for that component ALONE. Never "
                "merge unrelated components into one query.",
            },
            {"role": "user", "content": f"Requirements:\n{joined}"},
        ],
    )
    return result.components


def _trim(text: str | None, limit: int = 400) -> str:
    normalized = " ".join((text or "").split())
    return normalized if len(normalized) <= limit else normalized[:limit] + "…"


# ── Constructor del grafo ────────────────────────────────────────────────────────


def build_estimation_graph(deps: GraphDeps) -> StateGraph:
    """Define los 5 nodos (cerrando sobre `deps`) y cablea el grafo. Devuelve SIN compilar."""

    async def extract_requirements(state: EstimationState) -> dict[str, Any]:
        with span("node: extract_requirements"):
            requirements = await asyncio.to_thread(
                _extract_requirements_llm, state["transcript"]
            )
        logger.info("graph_extract_requirements", n=len(requirements))
        return {"requirements": requirements}

    async def classify_components(state: EstimationState) -> dict[str, Any]:
        with span("node: classify_components"):
            components = await asyncio.to_thread(
                _classify_components_llm, state.get("requirements", [])
            )
        logger.info("graph_classify_components", n=len(components))
        return {"components": [c.model_dump() for c in components]}

    async def search_budgets(state: EstimationState) -> dict[str, Any]:
        matches: list[dict[str, Any]] = []
        components = state.get("components", [])
        with span("node: search_budgets", n_components=len(components)):
            for comp in components:
                query = comp["search_query"]
                vector = await asyncio.to_thread(deps.embedder.embed_one, query)
                rows = await hybrid_search(
                    deps.session,
                    query_vector=vector,
                    query_text=query,
                    k=deps.k,
                    candidate_pool=deps.candidate_pool,
                    rrf_k=deps.rrf_k,
                    fulltext_config=deps.fulltext_config,
                )
                for row in rows:
                    md = row.get("metadata") or {}
                    matches.append(
                        {
                            "component": comp["name"],
                            "chunk_id": md.get("chunk_id") or str(row.get("chunk_id")),
                            "document_id": md.get("budget_id") or str(row.get("document_id")),
                            "content": _trim(row.get("content")),
                            "score": round(float(row.get("rrf_score", 0.0)), 5),
                        }
                    )
        logger.info("graph_search_budgets", n_matches=len(matches))
        # reducer operator.add: ACUMULA (append), no sobreescribe.
        return {"budget_matches": matches}

    async def generate_estimate(state: EstimationState) -> dict[str, Any]:
        matches = state.get("budget_matches", [])
        # Reconstruimos las filas en la forma que espera el generador de S11 (content +
        # metadata con chunk_id/budget_id para que pueda citar).
        rows = [
            {
                "content": m["content"],
                "metadata": {"chunk_id": m["chunk_id"], "budget_id": m["document_id"]},
            }
            for m in matches
        ]
        with span("node: generate_estimate", n_chunks=len(rows)):
            estimate = await asyncio.to_thread(
                rag_generate_estimate, state["transcript"], rows
            )
        logger.info(
            "graph_generate_estimate",
            line_items=len(estimate.line_items),
            total_hours=estimate.total_hours,
        )
        return {"estimate": estimate.model_dump()}

    async def validate_and_consolidate(state: EstimationState) -> dict[str, Any]:
        with span("node: validate_and_consolidate"):
            est_dict = state.get("estimate")
            if not est_dict:
                return {"status": "needs_review", "errors": ["no estimate produced"]}
            estimate = Estimate(**est_dict)
            retrieved_ids = {m["chunk_id"] for m in state.get("budget_matches", [])}
            report = verify_citations(estimate, retrieved_ids)
            status = (
                "validated"
                if (not report.has_dangling and estimate.total_hours > 0)
                else "needs_review"
            )
        logger.info("graph_validate", status=status, has_dangling=report.has_dangling)
        return {"citation_report": report.model_dump(), "status": status}

    async def needs_review(state: EstimationState) -> dict[str, Any]:
        with span("node: needs_review"):
            reasons: list[str] = []
            cr = state.get("citation_report") or {}
            if cr.get("dangling", 0):
                reasons.append(f"{cr['dangling']} dangling citation(s)")
            est = state.get("estimate") or {}
            if not est or est.get("total_hours", 0) <= 0:
                reasons.append("no grounded hours")
        detail = ", ".join(reasons) or "validation failed"
        return {"errors": [f"flagged for human review: {detail}"]}

    def route_after_validation(state: EstimationState) -> str:
        """Arista CONDICIONAL (Nivel 3): decide el destino según el status de validación."""
        return "needs_review" if state.get("status") == "needs_review" else "validated"

    builder = StateGraph(EstimationState)
    builder.add_node("extract_requirements", extract_requirements)
    builder.add_node("classify_components", classify_components)
    builder.add_node("search_budgets", search_budgets)
    builder.add_node("generate_estimate", generate_estimate)
    builder.add_node("validate_and_consolidate", validate_and_consolidate)
    builder.add_node("needs_review", needs_review)

    builder.add_edge(START, "extract_requirements")
    builder.add_edge("extract_requirements", "classify_components")
    builder.add_edge("classify_components", "search_budgets")
    builder.add_edge("search_budgets", "generate_estimate")
    builder.add_edge("generate_estimate", "validate_and_consolidate")
    # Nivel 3: en vez de una arista fija a END, decidimos en tiempo de ejecución.
    builder.add_conditional_edges(
        "validate_and_consolidate",
        route_after_validation,
        {"needs_review": "needs_review", "validated": END},
    )
    builder.add_edge("needs_review", END)

    return builder
