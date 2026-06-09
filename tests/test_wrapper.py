"""Tests del wrapper de abstracción + fallback + caché.

Clave: NO llamamos a ningún LLM real. Mockeamos `litellm.completion` (donde se
usa, dentro del wrapper) para controlar qué devuelve o qué error lanza.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.config import get_settings
from app.services.llm_wrapper import LLMWrapper


def fake_response(content="## Estimación\n\n**Total: 40 horas**", model="gpt-4o-mini",
                  tokens_in=12, tokens_out=34):
    """Imita la forma de la respuesta de litellm.completion (compatible con OpenAI)."""
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=content),
            finish_reason="stop",
        )],
        usage=SimpleNamespace(prompt_tokens=tokens_in, completion_tokens=tokens_out),
        model=model,
    )


@patch("app.services.llm_wrapper.litellm.completion_cost", return_value=0.0)
@patch("app.services.llm_wrapper.litellm.completion")
def test_complete_normalizes_response(mock_completion, _mock_cost) -> None:
    mock_completion.return_value = fake_response()

    result = LLMWrapper().complete("Eres un estimador.", [{"role": "user", "content": "hola"}])

    assert result.content.startswith("## Estimación")
    assert result.provider == "openai"
    assert result.model == "gpt-4o-mini"
    assert result.tokens_in == 12
    assert result.tokens_out == 34
    assert result.cache_hit is False
    assert result.fallback_used is False
    mock_completion.assert_called_once()


@patch("app.services.llm_wrapper.litellm.completion_cost", return_value=0.0)
@patch("app.services.llm_wrapper.litellm.completion")
def test_second_identical_call_hits_cache(mock_completion, _mock_cost) -> None:
    mock_completion.return_value = fake_response()
    wrapper = LLMWrapper()
    messages = [{"role": "user", "content": "misma transcripción"}]

    first = wrapper.complete("system", messages)
    second = wrapper.complete("system", messages)

    assert first.cache_hit is False
    assert second.cache_hit is True
    # La segunda vez NO se llama al LLM: la respuesta sale de caché.
    mock_completion.assert_called_once()


@patch("app.services.llm_wrapper.litellm.completion_cost", return_value=0.0)
@patch("app.services.llm_wrapper.litellm.completion")
def test_fallback_rotates_to_next_provider(mock_completion, _mock_cost, monkeypatch) -> None:
    # Dos proveedores disponibles, en orden openai -> anthropic.
    monkeypatch.setenv("OPENAI_API_KEY", "key-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-anthropic")
    monkeypatch.setenv("PROVIDER_FALLBACK_ORDER", "openai,anthropic")
    get_settings.cache_clear()

    # El primero falla; el segundo responde.
    mock_completion.side_effect = [
        RuntimeError("openai temporalmente caído"),
        fake_response(model="anthropic/claude-haiku-4-5"),
    ]

    result = LLMWrapper().complete("system", [{"role": "user", "content": "hola"}])

    assert result.fallback_used is True
    assert result.provider == "anthropic"
    assert mock_completion.call_count == 2


def test_complete_without_providers_raises(monkeypatch) -> None:
    # Sin ninguna API key, el wrapper no puede llamar a nadie -> ValueError (config).
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()

    with pytest.raises(ValueError):
        LLMWrapper().complete("system", [{"role": "user", "content": "x"}])


def _stream_chunk(content, finish_reason=None):
    """Imita un chunk de litellm.completion(stream=True)."""
    return SimpleNamespace(
        choices=[SimpleNamespace(
            delta=SimpleNamespace(content=content),
            finish_reason=finish_reason,
        )]
    )


@patch("app.services.llm_wrapper._stream_usage", return_value=(20, 5, 0.0))
@patch("app.services.llm_wrapper.litellm.completion")
def test_stream_captures_finish_reason_length(mock_completion, _usage) -> None:
    # El último chunk marca finish_reason="length" (truncado). El wrapper debe
    # capturarlo y volcarlo en meta, en vez de asumir siempre "stop".
    def fake_stream(*args, **kwargs):
        yield _stream_chunk("## Esti")
        yield _stream_chunk("mación")
        yield _stream_chunk(None, finish_reason="length")  # cierre: truncado
    mock_completion.side_effect = fake_stream

    meta: dict = {}
    text = "".join(LLMWrapper().stream("system", [{"role": "user", "content": "x"}], meta=meta))

    assert text == "## Estimación"
    assert meta["finish_reason"] == "length"


@patch("app.services.llm_wrapper.litellm.completion_cost", return_value=0.0)
@patch("app.services.llm_wrapper.litellm.completion")
def test_generate_estimation_surfaces_finish_reason(mock_completion, _cost) -> None:
    # La capa de negocio debe propagar finish_reason hasta el dict de respuesta,
    # para que la API y la UI puedan avisar de truncamiento.
    from app.services.llm_service import generate_estimation

    mock_completion.return_value = fake_response()  # finish_reason="stop"
    result = generate_estimation("Una transcripción cualquiera.")

    assert result["finish_reason"] == "stop"
