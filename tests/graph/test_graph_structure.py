"""Tests de estructura del grafo (sesión 13): nodos, cableado y el reducer del estado."""

from __future__ import annotations

import operator
from types import SimpleNamespace
from typing import Annotated, get_args, get_type_hints

from app.graph.build import build_estimation_graph
from app.graph.deps import GraphDeps
from app.graph.state import EstimationState


def _deps() -> GraphDeps:
    return GraphDeps(session=None, embedder=SimpleNamespace())  # type: ignore[arg-type]


def test_graph_has_the_five_nodes_plus_needs_review():
    builder = build_estimation_graph(_deps())
    expected = {
        "extract_requirements",
        "classify_components",
        "search_budgets",
        "generate_estimate",
        "validate_and_consolidate",
        "needs_review",
    }
    assert expected <= set(builder.nodes)


def test_graph_compiles_without_checkpointer():
    graph = build_estimation_graph(_deps()).compile()
    # El grafo compilado expone su estructura; comprobamos que los nodos están cableados.
    drawn = graph.get_graph()
    node_ids = {n.id for n in drawn.nodes.values()} if hasattr(drawn, "nodes") else set()
    assert "search_budgets" in node_ids


def test_budget_matches_uses_accumulator_reducer():
    """El requisito del enunciado: ≥1 reducer acumulador (operator.add) en el estado."""
    hints = get_type_hints(EstimationState, include_extras=True)
    # budget_matches y errors deben ser Annotated[..., operator.add]
    for field in ("budget_matches", "errors"):
        annotated = hints[field]
        args = get_args(annotated)
        assert operator.add in args, f"{field} debería usar el reducer operator.add"
