"""Test end-to-end del grafo (sesión 13) SIN red ni BBDD.

Parcheamos los pasos LLM (extract/classify/generate) y la búsqueda híbrida con dobles, y
compilamos SIN checkpointer. Así verificamos el cableado completo: el estado recorre los
5 nodos, el reducer ACUMULA los matches, y la arista CONDICIONAL enruta a validated o a
needs_review según la verificación de citaciones (que sí es real y determinista).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import app.graph.build as build_mod
from app.generation.schemas import (
    EstimateLineItem,
    Estimate,
    SourceReference,
)
from app.graph.build import _ComponentSpec, build_estimation_graph
from app.graph.deps import GraphDeps


def _deps() -> GraphDeps:
    return GraphDeps(
        session=None,  # type: ignore[arg-type]
        embedder=SimpleNamespace(embed_one=lambda q: [0.0] * 1536),  # type: ignore[arg-type]
    )


def _patch_common(monkeypatch):
    """Extract/classify/search deterministas (2 componentes, 1 match cada uno)."""
    monkeypatch.setattr(
        build_mod, "_extract_requirements_llm", lambda transcript: ["need auth", "need payments"]
    )
    monkeypatch.setattr(
        build_mod,
        "_classify_components_llm",
        lambda requirements: [
            _ComponentSpec(name="auth", search_query="oauth authentication"),
            _ComponentSpec(name="payments", search_query="payments integration"),
        ],
    )

    async def fake_hybrid_search(session, *, query_text, **kwargs):
        # Un match por componente, con chunk_id trazable según la query.
        cid = "BUD-1::AUTH" if "oauth" in query_text else "BUD-2::PAY"
        return [
            {
                "chunk_id": 1,
                "document_id": 1,
                "content": f"Component for '{query_text}'. Estimated hours: 40.",
                "rrf_score": 0.03,
                "metadata": {"chunk_id": cid, "budget_id": cid.split("::")[0]},
            }
        ]

    monkeypatch.setattr(build_mod, "hybrid_search", fake_hybrid_search)


def test_graph_run_validated_path(monkeypatch):
    _patch_common(monkeypatch)

    # Estimate GROUNDED citando un chunk_id que SÍ está en los matches -> sin colgantes.
    grounded = Estimate(
        line_items=[
            EstimateLineItem(
                component="auth",
                hours=40,
                rationale="from evidence",
                grounded=True,
                sources=[SourceReference(chunk_id="BUD-1::AUTH", document_id="BUD-1", evidence="40")],
            )
        ],
        total_hours=40,
        summary="ok",
    )
    monkeypatch.setattr(build_mod, "rag_generate_estimate", lambda transcript, rows: grounded)

    graph = build_estimation_graph(_deps()).compile()
    final = asyncio.run(
        graph.ainvoke(
            {"transcript": "meeting"}, config={"configurable": {"thread_id": "t1"}}
        )
    )

    # El reducer acumuló un match por cada uno de los 2 componentes.
    assert len(final["budget_matches"]) == 2
    assert {m["component"] for m in final["budget_matches"]} == {"auth", "payments"}
    # La verificación real no encontró colgantes -> validated.
    assert final["status"] == "validated"
    assert final["estimate"]["total_hours"] == 40
    assert final.get("errors", []) == []


def test_graph_run_needs_review_on_dangling_citation(monkeypatch):
    _patch_common(monkeypatch)

    # Estimate que cita un chunk_id que NO está en los matches -> cita COLGANTE.
    dangling = Estimate(
        line_items=[
            EstimateLineItem(
                component="auth",
                hours=40,
                rationale="hallucinated",
                grounded=True,
                sources=[SourceReference(chunk_id="BUD-9::GHOST", document_id="BUD-9", evidence="x")],
            )
        ],
        total_hours=40,
        summary="ko",
    )
    monkeypatch.setattr(build_mod, "rag_generate_estimate", lambda transcript, rows: dangling)

    graph = build_estimation_graph(_deps()).compile()
    final = asyncio.run(
        graph.ainvoke(
            {"transcript": "meeting"}, config={"configurable": {"thread_id": "t2"}}
        )
    )

    # La arista condicional enrutó a needs_review y el nodo dejó una incidencia.
    assert final["status"] == "needs_review"
    assert any("human review" in e for e in final["errors"])
