"""Endpoints del sistema multi-agente (sesión 14).

  POST /multiagent/estimate            → arranca el equipo sobre una transcripción.
  POST /multiagent/resume/{thread_id}  → reanuda un grafo pausado en revisión humana.

El HITL necesita persistencia, así que ambos compilan el grafo con el checkpointer
AsyncPostgresSaver (Nivel 2). Cuando el grafo se PARA en `human_review` (interrupt), el
arranque devuelve `awaiting_human_review=True` con el payload de la pausa y el `thread_id`;
el cliente decide y llama a /resume con ese thread_id para continuar donde se quedó.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.graph.deps import GraphDeps
from app.graph.observability import configure_logfire
from app.logging_config import get_logger

from .build import build_multiagent_graph

logger = get_logger(component="multiagent_router")

router = APIRouter(prefix="/multiagent", tags=["multiagent"])

_setup_done = False


class MultiAgentRequest(BaseModel):
    transcript: str = Field(description="Transcripción de la reunión a estimar.")
    thread_id: str | None = None


class ResumeRequest(BaseModel):
    decision: str = Field(description='Decisión humana: "approve" o "reject".')


class MultiAgentResponse(BaseModel):
    thread_id: str
    awaiting_human_review: bool = False
    interrupt: dict | None = Field(
        default=None, description="Payload de la pausa humana (si awaiting_human_review)."
    )
    status: str | None = None
    estimate: dict | None = None
    citation_report: dict | None = None
    components: list[dict] | None = None
    n_budget_matches: int = 0
    audit: list[dict] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


async def _ensure_setup(checkpointer: AsyncPostgresSaver) -> None:
    global _setup_done
    if not _setup_done:
        await checkpointer.setup()
        _setup_done = True


def _build_deps(session: AsyncSession) -> GraphDeps:
    settings = get_settings()
    return GraphDeps(
        session=session,
        embedder=OpenAIEmbedder(),
        k=settings.agent_search_k,
        candidate_pool=settings.retrieval_candidate_pool,
        rrf_k=settings.rrf_k,
        fulltext_config=settings.fulltext_language,
    )


def _to_response(thread_id: str, final: dict[str, Any]) -> MultiAgentResponse:
    """Traduce el estado final del grafo a la respuesta, detectando la pausa humana."""
    interrupts = final.get("__interrupt__")
    if interrupts:
        payload = interrupts[0].value if hasattr(interrupts[0], "value") else dict(interrupts[0])
        return MultiAgentResponse(
            thread_id=thread_id,
            awaiting_human_review=True,
            interrupt=payload,
            status=final.get("status"),
            estimate=final.get("estimate"),
            citation_report=final.get("citation_report"),
            components=final.get("components"),
            n_budget_matches=len(final.get("budget_matches", [])),
            audit=final.get("audit", []) or [],
            errors=final.get("errors", []) or [],
        )
    return MultiAgentResponse(
        thread_id=thread_id,
        awaiting_human_review=False,
        status=final.get("status"),
        estimate=final.get("estimate"),
        citation_report=final.get("citation_report"),
        components=final.get("components"),
        n_budget_matches=len(final.get("budget_matches", [])),
        audit=final.get("audit", []) or [],
        errors=final.get("errors", []) or [],
    )


@router.post("/estimate", response_model=MultiAgentResponse)
async def multiagent_estimate(
    request: MultiAgentRequest,
    session: AsyncSession = Depends(get_session),
) -> MultiAgentResponse:
    """Arranca el equipo multi-agente. Puede terminar o PARAR en revisión humana."""
    settings = get_settings()
    configure_logfire(settings.logfire_enabled)
    try:
        deps = _build_deps(session)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    builder = build_multiagent_graph(deps, settings.multiagent_review_threshold_hours)
    thread_id = request.thread_id or f"team-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    async with AsyncPostgresSaver.from_conn_string(settings.graph_checkpointer_url) as cp:
        await _ensure_setup(cp)
        graph = builder.compile(checkpointer=cp)
        final = await graph.ainvoke({"transcript": request.transcript}, config=config)

    response = _to_response(thread_id, final)
    logger.info(
        "multiagent_estimate_completed",
        thread_id=thread_id,
        awaiting_human_review=response.awaiting_human_review,
        status=response.status,
    )
    return response


@router.post("/resume/{thread_id}", response_model=MultiAgentResponse)
async def multiagent_resume(
    thread_id: str,
    request: ResumeRequest,
    session: AsyncSession = Depends(get_session),
) -> MultiAgentResponse:
    """Reanuda un grafo pausado en revisión humana, aplicando la decisión."""
    settings = get_settings()
    configure_logfire(settings.logfire_enabled)
    try:
        deps = _build_deps(session)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    builder = build_multiagent_graph(deps, settings.multiagent_review_threshold_hours)
    config = {"configurable": {"thread_id": thread_id}}

    async with AsyncPostgresSaver.from_conn_string(settings.graph_checkpointer_url) as cp:
        await _ensure_setup(cp)
        graph = builder.compile(checkpointer=cp)
        # Reanuda: interrupt() en human_review devolverá esta decisión.
        final = await graph.ainvoke(
            Command(resume={"decision": request.decision}), config=config
        )

    response = _to_response(thread_id, final)
    logger.info(
        "multiagent_resume_completed", thread_id=thread_id, status=response.status
    )
    return response
