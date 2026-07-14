"""Tests del endpoint POST /embeddings/ingest refactorizado a persistencia (sesión 08).

El endpoint ahora persiste en BBDD, así que parcheamos la capa `repository` (AsyncMock)
y sobreescribimos las dependencias de sesión y embedder. Así NO se necesita Postgres ni
la API real: probamos la ORQUESTACIÓN del router (200 con métricas, 409 duplicado, 500).
La lógica real contra la BBDD se prueba en test_repository.py (skipif sin BBDD).
"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.db import get_session
from app.embedding_pipeline.router import get_embedder
from app.embedding_pipeline.schemas import Chunk, EmbeddedChunk
from app.main import app

_ONE_BUDGET = {
    "source_path": "data/budgets/BUD-2024-014.json",
    "document_type": "historical_budget",
    "content": {
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
    },
}


class _FakeEmbedder:
    """Adjunta un vector fijo a cada chunk, sin tocar la red."""

    def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        return [EmbeddedChunk(**c.model_dump(), embedding=[0.1, 0.2, 0.3]) for c in chunks]

    def embed_one(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class _DummySession:
    """Sesión de mentira: la repository está parcheada, así que no se usa de verdad.
    Solo necesita un rollback async por si el camino de error lo invoca."""

    async def rollback(self) -> None:
        return None


def _override_deps(embedder=None):
    app.dependency_overrides[get_session] = lambda: _DummySession()
    app.dependency_overrides[get_embedder] = lambda: embedder or _FakeEmbedder()


def test_ingest_persists_and_returns_metrics() -> None:
    _override_deps()
    try:
        with patch(
            "app.embedding_pipeline.repository.get_document_id_by_source",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.embedding_pipeline.repository.persist_document",
            new=AsyncMock(return_value=7),
        ):
            client = TestClient(app)
            resp = client.post("/embeddings/ingest", json=_ONE_BUDGET)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == 7
    assert body["chunks_created"] == 2  # dos componentes
    assert body["embedding_dimension"] == 1536
    assert "ingestion_time_ms" in body


def test_ingest_duplicate_returns_409_with_existing_id() -> None:
    _override_deps()
    try:
        with patch(
            "app.embedding_pipeline.repository.get_document_id_by_source",
            new=AsyncMock(return_value=42),
        ):
            client = TestClient(app)
            resp = client.post("/embeddings/ingest", json=_ONE_BUDGET)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"] == "Document already ingested"
    assert body["document_id"] == 42


def test_ingest_persist_failure_returns_500() -> None:
    _override_deps()
    try:
        with patch(
            "app.embedding_pipeline.repository.get_document_id_by_source",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.embedding_pipeline.repository.persist_document",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            client = TestClient(app)
            resp = client.post("/embeddings/ingest", json=_ONE_BUDGET)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 500


def test_ingest_invalid_content_returns_422() -> None:
    _override_deps()
    try:
        bad = {
            "source_path": "x.json",
            "document_type": "historical_budget",
            "content": {  # falta project_summary, year, etc.
                "budget_id": "B",
                "client_metadata": {"name": "X", "sector": "finance", "country": "ES"},
                "components": [],
            },
        }
        client = TestClient(app)
        resp = client.post("/embeddings/ingest", json=bad)
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 422
