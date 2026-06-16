"""Test del endpoint de streaming SSE POST /api/v1/estimate/stream (sesión 04).

El schema de request cambió: ya no se envía 'transcription' sino el formulario
tipado (description, project_type, detail_level, output_format).

Mockeamos litellm.completion para no hacer llamadas reales y verificamos que el
endpoint emite eventos SSE bien formados: varios `event: token` y un `event: done`.
"""

from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

# Payload válido con el nuevo schema de sesión 04.
VALID_PAYLOAD = {
    "description": "A mobile app for field technicians to log maintenance tasks offline.",
    "project_type": "mobile_app",
    "detail_level": "summary",
    "output_format": "line_items",
}


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
    """El endpoint debe emitir eventos SSE bien formados con el nuevo schema."""
    def fake_stream(*args, **kwargs):
        yield _chunk("1. UI Design")
        yield _chunk(" — 40 h")
        yield _chunk(None, finish_reason="stop")
    mock_completion.side_effect = fake_stream

    resp = client.post("/api/v1/estimate/stream", json=VALID_PAYLOAD)

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "event: token" in body
    assert "event: done" in body
    # El contenido del stream debe aparecer en los eventos token.
    assert "UI Design" in body


@patch("app.services.llm_wrapper._stream_usage", return_value=(10, 5, 0.0))
@patch("app.services.llm_wrapper.litellm.completion")
def test_estimate_stream_done_event_contains_prompt_version(mock_completion, _usage, client: TestClient) -> None:
    """El evento done debe incluir prompt_version en los metadatos."""
    def fake_stream(*args, **kwargs):
        yield _chunk("Some estimate")
        yield _chunk(None, finish_reason="stop")
    mock_completion.side_effect = fake_stream

    resp = client.post("/api/v1/estimate/stream?prompt_version=v2", json=VALID_PAYLOAD)

    assert resp.status_code == 200
    body = resp.text
    assert "event: done" in body
    assert "prompt_version" in body


def test_estimate_stream_rejects_short_description(client: TestClient) -> None:
    """Una description demasiado corta debe devolver 422 (validación Pydantic)."""
    payload = {**VALID_PAYLOAD, "description": "too short"}
    resp = client.post("/api/v1/estimate/stream", json=payload)
    assert resp.status_code == 422
