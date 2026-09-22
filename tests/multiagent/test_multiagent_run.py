"""Test end-to-end del equipo multi-agente (sesión 14) SIN red ni Postgres.

Parcheamos LLM + búsqueda + generación, y compilamos con MemorySaver (el checkpointer en
memoria basta para que interrupt()/resume funcionen en el test). Verificamos:
  - el supervisor recorre a los workers en orden y acumula la auditoría;
  - una estimación por encima del umbral PARA en revisión humana (interrupt);
  - al reanudar con 'approve', el grafo termina con status 'approved'.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

import app.multiagent.build as mab
from app.generation.schemas import Estimate, EstimateLineItem, SourceReference
from app.graph.build import _ComponentSpec
from app.graph.deps import GraphDeps
from app.multiagent.build import build_multiagent_graph


def _deps() -> GraphDeps:
    return GraphDeps(
        session=None,  # type: ignore[arg-type]
        embedder=SimpleNamespace(embed_one=lambda q: [0.0] * 1536),  # type: ignore[arg-type]
    )


def _patch(monkeypatch, total_hours: float):
    monkeypatch.setattr(mab, "_extract_requirements_llm", lambda t: ["need auth"])
    monkeypatch.setattr(
        mab,
        "_classify_components_llm",
        lambda reqs: [_ComponentSpec(name="auth", search_query="oauth authentication")],
    )

    async def fake_hybrid_search(session, *, query_text, **kwargs):
        return [
            {
                "chunk_id": 1,
                "document_id": 1,
                "content": "OAuth module. Estimated hours: 480.",
                "rrf_score": 0.03,
                "metadata": {"chunk_id": "BUD-1::AUTH", "budget_id": "BUD-1"},
            }
        ]

    monkeypatch.setattr(mab, "hybrid_search", fake_hybrid_search)

    estimate = Estimate(
        line_items=[
            EstimateLineItem(
                component="auth",
                hours=total_hours,
                rationale="from evidence",
                grounded=True,
                sources=[SourceReference(chunk_id="BUD-1::AUTH", document_id="BUD-1", evidence="480")],
            )
        ],
        total_hours=total_hours,
        summary="ok",
    )
    monkeypatch.setattr(mab, "rag_generate_estimate", lambda transcript, rows: estimate)


def test_team_pauses_for_human_review_then_resumes_approved(monkeypatch):
    _patch(monkeypatch, total_hours=480)  # > umbral 300 -> revisión humana
    graph = build_multiagent_graph(_deps(), review_threshold_hours=300).compile(
        checkpointer=MemorySaver()
    )
    config = {"configurable": {"thread_id": "team-test"}}

    async def run():
        first = await graph.ainvoke({"transcript": "meeting"}, config=config)
        second = await graph.ainvoke(Command(resume={"decision": "approve"}), config=config)
        return first, second

    first, second = asyncio.run(run())

    # 1) Paró en revisión humana con el payload de la pausa.
    assert "__interrupt__" in first
    payload = first["__interrupt__"][0].value
    assert "threshold" in payload["reason"]
    assert payload["total_hours"] == 480
    # El equipo ya había recorrido los 4 workers antes de la pausa (auditoría acumulada).
    agents_seen = {a.get("agent") for a in first.get("audit", [])}
    assert {"requirements_extractor", "budget_searcher", "estimate_generator", "coherence_validator"} <= agents_seen

    # 2) Al reanudar con approve, termina aprobado.
    assert second["status"] == "approved"
    assert second["human_decision"] == "approve"
    assert second["estimate"]["total_hours"] == 480


def test_team_auto_approves_below_threshold(monkeypatch):
    _patch(monkeypatch, total_hours=40)  # < umbral -> sin revisión humana
    graph = build_multiagent_graph(_deps(), review_threshold_hours=300).compile(
        checkpointer=MemorySaver()
    )
    config = {"configurable": {"thread_id": "team-low"}}
    final = asyncio.run(graph.ainvoke({"transcript": "meeting"}, config=config))

    # No hubo pausa: la estimación pequeña y validada se cierra sola.
    assert "__interrupt__" not in final
    assert final["status"] == "validated"
    assert final["estimate"]["total_hours"] == 40
