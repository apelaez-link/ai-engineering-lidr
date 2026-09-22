"""Endpoint del agente (sesión 12): POST /agent/estimate.

Recibe una transcripción de reunión y devuelve la estimación estructurada del agente
junto con su TRAZA (razonamiento + acción + observación por paso) y el COSTE en tokens.

Monta las dependencias de las tools (sesión de BBDD + embedder) y delega el bucle en
`run_agent`. La sesión de BBDD la inyecta FastAPI (una por request); el embedder y el
cliente de OpenAI se construyen desde el .env.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.logging_config import get_logger

from .loop import run_agent
from .schemas import AgentRun
from .tools import ToolContext

logger = get_logger(component="agent_router")

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentEstimateRequest(BaseModel):
    """Petición al agente: la transcripción y overrides opcionales para experimentar."""

    transcript: str = Field(description="Transcripción de la reunión a estimar.")
    model: str | None = Field(
        default=None,
        description="Modelo a usar (p.ej. 'gpt-5', 'gpt-5-mini', 'gpt-4o'). Si se omite, "
        "usa AGENT_MODEL del .env.",
    )
    max_steps: int | None = Field(
        default=None, description="Tope de vueltas del bucle (si se omite, AGENT_MAX_STEPS)."
    )
    k: int | None = Field(
        default=None, description="Referencias que devuelve cada search_budgets (si se omite, AGENT_SEARCH_K)."
    )


@router.post("/estimate", response_model=AgentRun)
async def agent_estimate(
    request: AgentEstimateRequest,
    session: AsyncSession = Depends(get_session),
) -> AgentRun:
    """Ejecuta el agente sobre la transcripción y devuelve estimación + traza + coste."""
    settings = get_settings()
    try:
        embedder = OpenAIEmbedder()  # valida OPENAI_API_KEY con mensaje claro
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    ctx = ToolContext(
        session=session,
        embedder=embedder,
        k=request.k or settings.agent_search_k,
        candidate_pool=settings.retrieval_candidate_pool,
        rrf_k=settings.rrf_k,
        fulltext_config=settings.fulltext_language,
    )

    try:
        result = await run_agent(
            request.transcript,
            ctx,
            model=request.model,
            max_steps=request.max_steps,
        )
    except ValueError as exc:  # p.ej. falta OPENAI_API_KEY al construir el cliente
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info(
        "agent_estimate_completed",
        stopped_reason=result.stopped_reason,
        steps=result.cost.steps,
        total_tokens=result.cost.total_tokens,
        has_estimate=result.estimate is not None,
    )
    return result
