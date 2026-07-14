"""Tests de integración del endpoint POST /embeddings/ingest (sesión 07).

Sobrescribimos la dependencia get_embedder con un embedder FALSO (sin red) via
app.dependency_overrides. Cubrimos: 200 + stats correctas, 422 por payload inválido,
y 500 cuando el embedder revienta.
"""

from fastapi.testclient import TestClient

from app.embedding_pipeline.embedder import estimate_cost_usd
from app.embedding_pipeline.router import get_embedder
from app.embedding_pipeline.schemas import Chunk, EmbeddedChunk
from app.main import app

_ONE_BUDGET = {
    "budgets": [
        {
            "budget_id": "BUD-2024-014",
            "client_metadata": {"name": "FintechCorp", "sector": "finance", "country": "ES"},
            "project_summary": "Mobile banking API",
            "main_technology": "ruby_on_rails",
            "year": 2024,
            "total_estimated_hours": 280,
            "components": [
                {
                    "component_id": "AUTH-001",
                    "name": "OAuth backend",
                    "description": "OAuth 2.0 flows.",
                    "tech_stack": ["ruby_on_rails"],
                    "estimated_hours": 120,
                    "complexity": "high",
                    "dependencies": [],
                },
                {
                    "component_id": "LEDGER-002",
                    "name": "Ledger",
                    "description": "Double-entry ledger.",
                    "tech_stack": ["ruby_on_rails"],
                    "estimated_hours": 160,
                    "complexity": "medium",
                    "dependencies": [],
                },
            ],
        }
    ]
}


class _FakeEmbedder:
    """Embedder falso: adjunta un vector fijo a cada chunk, sin tocar la red."""

    def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        return [EmbeddedChunk(**c.model_dump(), embedding=[0.1, 0.2, 0.3]) for c in chunks]


class _BrokenEmbedder:
    def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        raise RuntimeError("OpenAI down")


def test_ingest_returns_embedded_chunks_and_stats() -> None:
    app.dependency_overrides[get_embedder] = lambda: _FakeEmbedder()
    try:
        client = TestClient(app)
        response = client.post("/embeddings/ingest", json=_ONE_BUDGET)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    # Dos componentes -> dos chunks vectorizados.
    assert len(body["chunks"]) == 2
    assert body["chunks"][0]["chunk_id"] == "BUD-2024-014::AUTH-001"
    assert body["chunks"][0]["embedding"] == [0.1, 0.2, 0.3]
    # Stats agregadas.
    stats = body["stats"]
    assert stats["total_budgets"] == 1
    assert stats["total_chunks"] == 2
    assert stats["total_tokens"] > 0
    # El coste declarado coincide con la fórmula sobre los tokens contados.
    assert stats["estimated_cost_usd"] == round(estimate_cost_usd(stats["total_tokens"]), 6)


def test_ingest_invalid_payload_returns_422() -> None:
    """Falta un campo requerido (complexity) -> validación Pydantic -> 422."""
    bad = {
        "budgets": [
            {
                "budget_id": "BUD-1",
                "client_metadata": {"name": "X", "sector": "finance", "country": "ES"},
                "project_summary": "x",
                "main_technology": "go",
                "year": 2024,
                "total_estimated_hours": 10,
                "components": [
                    {
                        "component_id": "C1",
                        "name": "c",
                        "description": "d",
                        "tech_stack": ["go"],
                        "estimated_hours": 10,
                        # falta complexity (requerido)
                        "dependencies": [],
                    }
                ],
            }
        ]
    }
    client = TestClient(app)
    response = client.post("/embeddings/ingest", json=bad)
    assert response.status_code == 422


def test_ingest_embedder_failure_returns_500() -> None:
    app.dependency_overrides[get_embedder] = lambda: _BrokenEmbedder()
    try:
        client = TestClient(app)
        response = client.post("/embeddings/ingest", json=_ONE_BUDGET)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 500
