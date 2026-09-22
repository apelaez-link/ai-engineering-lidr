"""Supervisor + workers + human-in-the-loop, a mano (sesión 14).

Patrón supervisor construido con `StateGraph` + `Command` (NO `create_supervisor`):

    START → supervisor ─┬→ requirements_extractor ─┐
                        ├→ budget_searcher          │
                        ├→ estimate_generator        ├→ (vuelven al supervisor)
                        ├→ coherence_validator      ┘
                        ├→ human_review (interrupt) → supervisor
                        └→ END

- El SUPERVISOR no tiene tools: mira el estado y decide el siguiente agente (o END, o la
  revisión humana). Devuelve `Command(goto=..., update=...)`.
- Cada WORKER usa SOLO su tool (privilegio mínimo, comprobado con enforce_privilege), hace
  su parte y devuelve `Command(goto="supervisor", ...)` para ceder el control.
- `human_review` PARA el grafo con `interrupt()` cuando la estimación es de riesgo; el
  estado queda persistido (checkpointer) y se reanuda con la decisión humana.

Reutiliza las piezas ya construidas: los pasos LLM de la S13, la búsqueda híbrida de S10,
el generador citado de S11 y las tools deterministas de la S12.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agent.tools import calculate_estimate, validate_estimate
from app.embedding_pipeline.hybrid import hybrid_search
from app.generation.generator import generate_estimate as rag_generate_estimate
from app.generation.schemas import Estimate
from app.generation.verify import verify_citations
from app.graph.build import (
    _classify_components_llm,
    _extract_requirements_llm,
    _trim,
)
from app.graph.deps import GraphDeps
from app.graph.observability import span
from app.logging_config import get_logger

from .privileges import audit_entry, enforce_privilege
from .state import MultiAgentState

logger = get_logger(component="multiagent")

# Workers a los que el supervisor puede enrutar (para declarar destinos del nodo).
_WORKERS = (
    "requirements_extractor",
    "budget_searcher",
    "estimate_generator",
    "coherence_validator",
    "human_review",
)


def _needs_human_review(state: MultiAgentState, threshold_hours: float) -> bool:
    """Regla del HITL: revisión humana si la validación falló o la estimación es de riesgo.

    "De riesgo" = supera un umbral de horas (una estimación grande no se cierra sola). En un
    servicio real, aquí entrarían coste, criticidad, cliente, etc.
    """
    if state.get("status") == "needs_review":
        return True
    est = state.get("estimate") or {}
    return float(est.get("total_hours", 0) or 0) > threshold_hours


def build_multiagent_graph(deps: GraphDeps, review_threshold_hours: float = 300.0) -> StateGraph:
    """Construye el grafo supervisor/workers. Devuelve SIN compilar (el llamante añade el checkpointer)."""

    # ── SUPERVISOR: solo enruta (sin tools) ──────────────────────────────────────
    async def supervisor(state: MultiAgentState) -> Command:
        with span("agent: supervisor"):
            if not state.get("components"):
                goto = "requirements_extractor"
            elif not state.get("budget_matches"):
                goto = "budget_searcher"
            elif not state.get("estimate"):
                goto = "estimate_generator"
            elif not state.get("status"):
                goto = "coherence_validator"
            elif state.get("human_decision") is None and _needs_human_review(
                state, review_threshold_hours
            ):
                goto = "human_review"
            else:
                goto = END
        logger.info("supervisor_route", goto=str(goto))
        return Command(
            goto=goto,
            update={"audit": [{"agent": "supervisor", "routed_to": str(goto)}]},
        )

    # ── WORKER 1: extrae requisitos y clasifica componentes (sin tools de negocio) ─
    async def requirements_extractor(state: MultiAgentState) -> Command:
        with span("agent: requirements_extractor"):
            reqs = await asyncio.to_thread(_extract_requirements_llm, state["transcript"])
            comps = await asyncio.to_thread(_classify_components_llm, reqs)
        return Command(
            goto="supervisor",
            update={
                "requirements": reqs,
                "components": [c.model_dump() for c in comps],
                "audit": [audit_entry("requirements_extractor", "(none)")],
            },
        )

    # ── WORKER 2: busca presupuestos (SOLO search_budgets) ───────────────────────
    async def budget_searcher(state: MultiAgentState) -> Command:
        enforce_privilege("budget_searcher", "search_budgets")  # privilegio mínimo
        matches: list[dict[str, Any]] = []
        with span("agent: budget_searcher"):
            for comp in state.get("components", []):
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
        return Command(
            goto="supervisor",
            update={
                "budget_matches": matches,
                "audit": [audit_entry("budget_searcher", "search_budgets", n=len(matches))],
            },
        )

    # ── WORKER 3: genera la estimación (SOLO calculate_estimate) ─────────────────
    async def estimate_generator(state: MultiAgentState) -> Command:
        enforce_privilege("estimate_generator", "calculate_estimate")  # privilegio mínimo
        matches = state.get("budget_matches", [])
        rows = [
            {
                "content": m["content"],
                "metadata": {"chunk_id": m["chunk_id"], "budget_id": m["document_id"]},
            }
            for m in matches
        ]
        with span("agent: estimate_generator"):
            estimate = await asyncio.to_thread(rag_generate_estimate, state["transcript"], rows)
            # Su tool concedida: totaliza de forma determinista (coherencia garantizada).
            calculate_estimate(
                [{"component": li.component, "hours": li.hours} for li in estimate.line_items]
            )
        return Command(
            goto="supervisor",
            update={
                "estimate": estimate.model_dump(),
                "audit": [audit_entry("estimate_generator", "calculate_estimate")],
            },
        )

    # ── WORKER 4: valida coherencia y citaciones (SOLO validate_estimate) ────────
    async def coherence_validator(state: MultiAgentState) -> Command:
        enforce_privilege("coherence_validator", "validate_estimate")  # privilegio mínimo
        with span("agent: coherence_validator"):
            estimate = Estimate(**state["estimate"])
            retrieved_ids = {m["chunk_id"] for m in state.get("budget_matches", [])}
            report = verify_citations(estimate, retrieved_ids)
            check = validate_estimate(
                estimate.total_hours,
                [{"component": li.component, "hours": li.hours} for li in estimate.line_items],
            )
            status = (
                "validated"
                if (not report.has_dangling and estimate.total_hours > 0 and check["ok"])
                else "needs_review"
            )
        return Command(
            goto="supervisor",
            update={
                "citation_report": report.model_dump(),
                "status": status,
                "audit": [audit_entry("coherence_validator", "validate_estimate", status=status)],
            },
        )

    # ── HUMAN-IN-THE-LOOP: pausa con interrupt() y espera decisión ───────────────
    async def human_review(state: MultiAgentState) -> Command:
        est = state.get("estimate") or {}
        # interrupt() PARA el grafo aquí; el estado queda persistido en el checkpointer.
        # Al reanudar con Command(resume=<decisión>), interrupt() devuelve esa decisión.
        decision = interrupt(
            {
                "reason": (
                    "needs_review by validator"
                    if state.get("status") == "needs_review"
                    else "estimate above auto-approval threshold"
                ),
                "status": state.get("status"),
                "total_hours": est.get("total_hours"),
                "summary": est.get("summary"),
                "how_to_resume": (
                    "POST /multiagent/resume/{thread_id} con "
                    '{"decision": "approve"} o {"decision": "reject"}'
                ),
            }
        )
        # A partir de aquí se ejecuta EN LA REANUDACIÓN.
        dec = decision.get("decision") if isinstance(decision, dict) else str(decision)
        status = "approved" if dec == "approve" else "rejected"
        logger.info("human_review_resumed", decision=dec, status=status)
        return Command(
            goto="supervisor",
            update={
                "human_decision": dec,
                "status": status,
                "audit": [{"agent": "human_review", "decision": dec}],
            },
        )

    builder = StateGraph(MultiAgentState)
    builder.add_node("supervisor", supervisor, destinations=(*_WORKERS, END))
    builder.add_node("requirements_extractor", requirements_extractor, destinations=("supervisor",))
    builder.add_node("budget_searcher", budget_searcher, destinations=("supervisor",))
    builder.add_node("estimate_generator", estimate_generator, destinations=("supervisor",))
    builder.add_node("coherence_validator", coherence_validator, destinations=("supervisor",))
    builder.add_node("human_review", human_review, destinations=("supervisor",))
    builder.add_edge(START, "supervisor")
    return builder
