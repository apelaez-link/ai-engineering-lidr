"""Endpoint del grafo (sesión 13): POST /graph/estimate.

Recibe una transcripción y ejecuta el grafo de LangGraph, devolviendo la estimación y el
estado final (status, citaciones, componentes, nº de matches, incidencias). Mantiene el
mismo CONTRATO externo que el pipeline/agente: transcripción → estimación + estado.

Nivel 2: compila el grafo con el checkpointer AsyncPostgresSaver y ejecuta con un
`thread_id` (si el cliente manda uno, reanuda ese hilo; si no, genera uno nuevo). El
checkpointer persiste el estado del grafo en Postgres, lo que permitiría reanudar una
ejecución interrumpida — la base de la pausa/reanudación humana de la S14.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.logging_config import get_logger

from .build import build_estimation_graph
from .deps import GraphDeps
from .observability import configure_logfire

logger = get_logger(component="graph_router")

router = APIRouter(prefix="/graph", tags=["graph"])

# El checkpointer crea sus tablas la primera vez (setup()). Lo hacemos una vez por
# proceso: las tablas persisten en Postgres, así que las siguientes peticiones no repiten.
_setup_done = False


class GraphEstimateRequest(BaseModel):
    transcript: str = Field(description="Transcripción de la reunión a estimar.")
    thread_id: str | None = Field(
        default=None,
        description="Hilo del checkpointer. Si se omite, se genera uno nuevo; si se "
        "reutiliza, el checkpointer reanuda ese estado.",
    )


class GraphEstimateResponse(BaseModel):
    thread_id: str
    status: str | None = None
    estimate: dict | None = None
    citation_report: dict | None = None
    components: list[dict] | None = None
    n_budget_matches: int = 0
    errors: list[str] = Field(default_factory=list)
    checkpointer: str = Field(description="'postgres' o 'none'.")


async def _ensure_setup(checkpointer: AsyncPostgresSaver) -> None:
    global _setup_done
    if not _setup_done:
        await checkpointer.setup()
        _setup_done = True


@router.post("/estimate", response_model=GraphEstimateResponse)
async def graph_estimate(
    request: GraphEstimateRequest,
    session: AsyncSession = Depends(get_session),
) -> GraphEstimateResponse:
    """Ejecuta el grafo de estimación sobre la transcripción."""
    settings = get_settings()
    configure_logfire(settings.logfire_enabled)

    try:
        embedder = OpenAIEmbedder()  # valida OPENAI_API_KEY con mensaje claro
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    deps = GraphDeps(
        session=session,
        embedder=embedder,
        k=settings.agent_search_k,
        candidate_pool=settings.retrieval_candidate_pool,
        rrf_k=settings.rrf_k,
        fulltext_config=settings.fulltext_language,
    )
    builder = build_estimation_graph(deps)
    thread_id = request.thread_id or f"graph-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    if settings.graph_checkpointer_enabled:
        async with AsyncPostgresSaver.from_conn_string(settings.graph_checkpointer_url) as cp:
            await _ensure_setup(cp)
            graph = builder.compile(checkpointer=cp)
            final = await graph.ainvoke({"transcript": request.transcript}, config=config)
        checkpointer = "postgres"
    else:
        graph = builder.compile()
        final = await graph.ainvoke({"transcript": request.transcript}, config=config)
        checkpointer = "none"

    logger.info(
        "graph_estimate_completed",
        thread_id=thread_id,
        status=final.get("status"),
        n_matches=len(final.get("budget_matches", [])),
        checkpointer=checkpointer,
    )
    return GraphEstimateResponse(
        thread_id=thread_id,
        status=final.get("status"),
        estimate=final.get("estimate"),
        citation_report=final.get("citation_report"),
        components=final.get("components"),
        n_budget_matches=len(final.get("budget_matches", [])),
        errors=final.get("errors", []) or [],
        checkpointer=checkpointer,
    )
