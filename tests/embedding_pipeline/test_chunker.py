"""Tests del chunker estructural JSON (sesión 07).

El chunker es DETERMINISTA y no toca la red: se testea directamente sobre objetos
Budget, sin mocks. Cubrimos las tres decisiones de la lección: granularidad
(1 componente = 1 chunk), contenido (header contextual + campos), metadata filtrable,
formato del chunk_id y conteo de tokens.
"""

from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.schemas import Budget

_BUDGET = Budget(
    budget_id="BUD-2024-014",
    client_metadata={"name": "FintechCorp", "sector": "finance", "country": "ES"},
    project_summary="Mobile banking API with OAuth 2.0 authentication",
    main_technology="ruby_on_rails",
    year=2024,
    total_estimated_hours=280,
    components=[
        {
            "component_id": "AUTH-001",
            "name": "OAuth 2.0 authentication backend",
            "description": "OAuth 2.0 flows with JWT session management.",
            "tech_stack": ["ruby_on_rails", "postgresql", "redis"],
            "estimated_hours": 120,
            "complexity": "high",
            "dependencies": [],
        },
        {
            "component_id": "LEDGER-002",
            "name": "Double-entry ledger",
            "description": "Immutable ledger with daily reconciliation.",
            "tech_stack": ["ruby_on_rails", "postgresql"],
            "estimated_hours": 160,
            "complexity": "medium",
            "dependencies": ["AUTH-001"],
        },
    ],
)


def test_one_component_one_chunk() -> None:
    """Granularidad: un componente produce exactamente un chunk."""
    chunks = JSONStructuralChunker().chunk([_BUDGET])
    assert len(chunks) == 2


def test_chunk_id_is_traceable() -> None:
    """chunk_id sigue el formato {budget_id}::{component_id}."""
    chunks = JSONStructuralChunker().chunk([_BUDGET])
    assert chunks[0].chunk_id == "BUD-2024-014::AUTH-001"
    assert chunks[1].chunk_id == "BUD-2024-014::LEDGER-002"


def test_text_has_contextual_header_and_component_fields() -> None:
    """El texto embebido combina header del padre + detalles del componente."""
    chunk = JSONStructuralChunker().chunk([_BUDGET])[0]
    # Header contextual del presupuesto padre.
    assert "[Project: Mobile banking API with OAuth 2.0 authentication]" in chunk.text
    assert "Client sector: finance" in chunk.text
    assert "Year: 2024" in chunk.text
    assert "Main tech: ruby_on_rails" in chunk.text
    # Detalles del componente.
    assert "Component: OAuth 2.0 authentication backend" in chunk.text
    assert "Tech stack: ruby_on_rails, postgresql, redis" in chunk.text
    assert "Complexity: high" in chunk.text


def test_metadata_has_filterable_fields() -> None:
    """La metadata lleva los campos filtrables (no embebidos) esperados."""
    chunk = JSONStructuralChunker().chunk([_BUDGET])[0]
    assert chunk.metadata == {
        "budget_id": "BUD-2024-014",
        "component_id": "AUTH-001",
        "client_sector": "finance",
        "main_technology": "ruby_on_rails",
        "year": 2024,
        "complexity": "high",
        "estimated_hours": 120,
    }


def test_token_count_is_positive_and_counted_with_tiktoken() -> None:
    """token_count es > 0 y coherente (el texto no está vacío)."""
    chunk = JSONStructuralChunker().chunk([_BUDGET])[0]
    assert chunk.token_count > 0
    # Un header + descripción corta ronda las decenas de tokens, no miles.
    assert chunk.token_count < 500


def test_multiple_budgets_flatten_to_single_list() -> None:
    """Varios presupuestos producen una lista plana de chunks (2 + 2 = 4)."""
    chunks = JSONStructuralChunker().chunk([_BUDGET, _BUDGET])
    assert len(chunks) == 4
