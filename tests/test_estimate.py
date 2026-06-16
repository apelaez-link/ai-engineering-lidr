"""Tests del endpoint POST /api/v1/estimate (sesión 04).

El contrato del endpoint cambió: ya no acepta 'transcription' + 'history', sino
un formulario tipado (description, project_type, detail_level, output_format).

Seguimos sin llamar a ningún LLM real: mockeamos litellm.completion a través del
wrapper para que los tests sean rápidos, deterministas y funcionen en CI sin API key.

Estrategia de mock: parcheamos 'app.services.llm_wrapper.litellm.completion'
(donde LiteLLM se llama realmente) en lugar de parcheamos el servicio de alto nivel,
de forma que también se ejercita la lógica del wrapper (caché, construcción de
mensajes, etc.) sin hacer llamadas de red.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

# Payload mínimo válido para todos los tests que necesiten una petición correcta.
VALID_PAYLOAD = {
    "description": "A SaaS platform for managing restaurant reservations with online payments.",
    "project_type": "web_saas",
    "detail_level": "medium",
    "output_format": "phases_table",
}


def _fake_completion(*args, **kwargs):
    """Simula una respuesta de litellm.completion con el contenido mínimo esperado."""
    usage = SimpleNamespace(prompt_tokens=50, completion_tokens=80)
    choice = SimpleNamespace(
        message=SimpleNamespace(content="| phase | duration_weeks | cost_eur | confidence_pct |\n|---|---|---|---|\n| Backend | 4 | 25600 | 85 |"),
        finish_reason="stop",
    )
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


@patch("app.services.llm_wrapper.litellm.completion", side_effect=_fake_completion)
def test_estimate_returns_text_and_prompt_version(mock_completion, client: TestClient) -> None:
    """El endpoint debe devolver 'text' y 'prompt_version' con status 200."""
    response = client.post("/api/v1/estimate", json=VALID_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert "text" in data
    assert "prompt_version" in data
    assert data["prompt_version"] == "v1"  # versión por defecto
    assert len(data["text"]) > 0
    mock_completion.assert_called_once()


@patch("app.services.llm_wrapper.litellm.completion", side_effect=_fake_completion)
def test_estimate_custom_prompt_version(mock_completion, client: TestClient) -> None:
    """El query param prompt_version debe pasarse a la respuesta."""
    response = client.post("/api/v1/estimate?prompt_version=v2", json=VALID_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert data["prompt_version"] == "v2"


@patch("app.services.llm_wrapper.litellm.completion", side_effect=_fake_completion)
def test_estimate_returns_observability_metadata(mock_completion, client: TestClient) -> None:
    """La respuesta debe incluir los campos de observabilidad heredados del wrapper."""
    response = client.post("/api/v1/estimate", json=VALID_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    # Campos de observabilidad definidos en EstimationResponse.
    assert "model" in data
    assert "cache_hit" in data
    assert "tokens_in" in data
    assert "tokens_out" in data
    assert "cost_usd" in data
    assert "latency_ms" in data


def test_estimate_rejects_short_description(client: TestClient) -> None:
    """Una description con menos de 20 caracteres debe devolver 422 (validación Pydantic)."""
    payload = {**VALID_PAYLOAD, "description": "too short"}
    response = client.post("/api/v1/estimate", json=payload)
    assert response.status_code == 422


def test_estimate_rejects_missing_project_type(client: TestClient) -> None:
    """Sin project_type el body es inválido -> 422."""
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "project_type"}
    response = client.post("/api/v1/estimate", json=payload)
    assert response.status_code == 422


def test_estimate_rejects_invalid_project_type(client: TestClient) -> None:
    """Un project_type que no existe en el Enum debe devolver 422."""
    payload = {**VALID_PAYLOAD, "project_type": "alien_spaceship"}
    response = client.post("/api/v1/estimate", json=payload)
    assert response.status_code == 422


@patch("app.routers.estimations.generate_estimation")
def test_estimate_config_error_returns_400(mock_generate, client: TestClient) -> None:
    """Si el servicio lanza ValueError (falta API key, etc.) -> 400."""
    mock_generate.side_effect = ValueError("No API key configured")
    response = client.post("/api/v1/estimate", json=VALID_PAYLOAD)
    assert response.status_code == 400


@patch("app.routers.estimations.generate_estimation")
def test_estimate_provider_error_returns_502(mock_generate, client: TestClient) -> None:
    """Si el proveedor falla (red, cuota, etc.) -> 502."""
    mock_generate.side_effect = RuntimeError("Provider unreachable")
    response = client.post("/api/v1/estimate", json=VALID_PAYLOAD)
    assert response.status_code == 502
