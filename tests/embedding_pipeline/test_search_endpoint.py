"""Tests del endpoint POST /search (sesión 08).

Parcheamos repository.search_chunks (AsyncMock) y sobreescribimos embedder+sesión: sin
BBDD ni API real. Probamos que la query se embebe, que el resultado se mapea al schema
de salida y que las métricas viajan.
"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.db import get_session
from app.embedding_pipeline.router import get_embedder
from app.main import app


class _FakeEmbedder:
    def embed_one(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class _DummySession:
    async def rollback(self) -> None:
        return None


_FAKE_ROWS = [
    {
        "chunk_id": 156,
        "document_id": 12,
        "chunk_type": "budget_component",
        "content": "Backend service with JWT-based authentication for fintech.",
        "distance": 0.231,
        "metadata": {"client_sector": "finance", "main_technology": "python"},
    },
    {
        "chunk_id": 22,
        "document_id": 3,
        "chunk_type": "budget_component",
        "content": "Authorization module with token isolation.",
        "distance": 0.288,
        "metadata": {"client_sector": "finance"},
    },
]


def test_search_returns_ranked_results() -> None:
    app.dependency_overrides[get_session] = lambda: _DummySession()
    app.dependency_overrides[get_embedder] = lambda: _FakeEmbedder()
    try:
        with patch(
            "app.embedding_pipeline.repository.search_chunks",
            new=AsyncMock(return_value=_FAKE_ROWS),
        ):
            client = TestClient(app)
            resp = client.post("/search", json={"query": "auth for fintech", "k": 2})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "auth for fintech"
    assert body["k"] == 2
    assert "search_time_ms" in body
    assert len(body["results"]) == 2
    first = body["results"][0]
    assert first["chunk_id"] == 156
    assert first["distance"] == 0.231
    assert first["metadata"]["client_sector"] == "finance"


def test_search_default_k_is_5() -> None:
    app.dependency_overrides[get_session] = lambda: _DummySession()
    app.dependency_overrides[get_embedder] = lambda: _FakeEmbedder()
    try:
        with patch(
            "app.embedding_pipeline.repository.search_chunks",
            new=AsyncMock(return_value=[]),
        ) as mock_search:
            client = TestClient(app)
            resp = client.post("/search", json={"query": "anything"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["k"] == 5
    # La k por defecto (5) se pasa a la repository.
    assert mock_search.call_args.args[2] == 5


def test_search_invalid_k_returns_422() -> None:
    """k fuera de rango (>50) falla la validación Pydantic."""
    client = TestClient(app)
    resp = client.post("/search", json={"query": "x", "k": 999})
    assert resp.status_code == 422
