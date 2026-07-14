"""Tests del OpenAIEmbedder (sesión 07).

Inyectamos un cliente FALSO (no toca la red) para comprobar el batching, el mapeo
de vectores a EmbeddedChunk, el reintento ante RateLimitError y el cálculo de coste.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import RateLimitError

from app.embedding_pipeline.embedder import (
    COST_PER_1M_INPUT_TOKENS_USD,
    OpenAIEmbedder,
    estimate_cost_usd,
)
from app.embedding_pipeline.schemas import Chunk


def _fake_response(texts: list[str]):
    """Respuesta falsa de embeddings.create: un vector [len, i] por texto, en orden."""
    data = [SimpleNamespace(embedding=[float(len(t)), float(i)]) for i, t in enumerate(texts)]
    return SimpleNamespace(data=data, usage=SimpleNamespace(total_tokens=len(texts) * 3))


def _fake_client() -> MagicMock:
    client = MagicMock()
    client.embeddings.create.side_effect = lambda model, input: _fake_response(input)
    return client


def _chunk(i: int) -> Chunk:
    return Chunk(chunk_id=f"B::C{i}", text=f"text {i}", metadata={}, token_count=3)


def test_embed_one_returns_vector() -> None:
    embedder = OpenAIEmbedder(client=_fake_client())
    vec = embedder.embed_one("hello")
    assert vec == [5.0, 0.0]  # len("hello")=5, index 0


def test_embed_many_preserves_order_and_attaches_embedding() -> None:
    embedder = OpenAIEmbedder(client=_fake_client())
    chunks = [_chunk(0), _chunk(1), _chunk(2)]
    embedded = embedder.embed_many(chunks)
    assert len(embedded) == 3
    # El chunk original se conserva y se le añade el embedding.
    assert embedded[0].chunk_id == "B::C0"
    assert embedded[1].embedding == [6.0, 1.0]  # len("text 1")=6, index 1 dentro del batch


def test_embed_many_batches_by_batch_size() -> None:
    """250 chunks con batch_size=100 -> 3 llamadas a la API (100+100+50)."""
    client = _fake_client()
    embedder = OpenAIEmbedder(client=client, batch_size=100)
    chunks = [_chunk(i) for i in range(250)]
    embedded = embedder.embed_many(chunks)
    assert len(embedded) == 250
    assert client.embeddings.create.call_count == 3


def test_retry_on_rate_limit_then_succeeds() -> None:
    """Ante un RateLimitError transitorio, reintenta y acaba devolviendo el vector."""
    req = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    resp = httpx.Response(429, request=req)
    rate_limited = RateLimitError("rate limited", response=resp, body=None)

    client = MagicMock()
    client.embeddings.create.side_effect = [
        rate_limited,  # primer intento: falla
        _fake_response(["hello"]),  # reintento: éxito
    ]
    embedder = OpenAIEmbedder(client=client)

    with patch("app.embedding_pipeline.embedder.time.sleep") as mock_sleep:
        vec = embedder.embed_one("hello")

    assert vec == [5.0, 0.0]
    assert client.embeddings.create.call_count == 2
    mock_sleep.assert_called_once()  # esperó una vez (backoff)


def test_estimate_cost_usd() -> None:
    """1M tokens cuesta exactamente el precio por millón; escala lineal."""
    assert estimate_cost_usd(1_000_000) == pytest.approx(COST_PER_1M_INPUT_TOKENS_USD)
    assert estimate_cost_usd(500_000) == pytest.approx(COST_PER_1M_INPUT_TOKENS_USD / 2)
    assert estimate_cost_usd(0) == 0.0
