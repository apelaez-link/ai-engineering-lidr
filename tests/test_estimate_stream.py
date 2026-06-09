"""Test del endpoint de streaming SSE POST /api/v1/estimate/stream.

Mockeamos el streaming de litellm (no hay LLM real) y comprobamos que el endpoint
emite eventos SSE bien formados: varios `event: token` y un `event: done`.
"""

from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient


def _chunk(content, finish_reason=None):
    """Imita un chunk de litellm.completion(stream=True)."""
    return SimpleNamespace(
        choices=[SimpleNamespace(
            delta=SimpleNamespace(content=content),
            finish_reason=finish_reason,
        )]
    )


@patch("app.services.llm_wrapper._stream_usage", return_value=(10, 5, 0.0))
@patch("app.services.llm_wrapper.litellm.completion")
def test_estimate_stream_emite_sse(mock_completion, _usage, client: TestClient) -> None:
    def fake_stream(*args, **kwargs):
        yield _chunk("## Esti")
        yield _chunk("mación")
        yield _chunk(None, finish_reason="stop")
    mock_completion.side_effect = fake_stream

    resp = client.post("/api/v1/estimate/stream", json={"transcription": "Una transcripción."})

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "event: token" in body
    assert "event: done" in body
    assert "Esti" in body  # el contenido del stream aparece en los eventos token
