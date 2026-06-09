"""Tests del endpoint POST /api/v1/estimate.

Idea clave: NO llamamos al LLM real. Con unittest.mock.patch sustituimos
generate_estimation por una versión falsa que devuelve lo que queramos.
Así los tests son gratis, rápidos, deterministas y funcionan en CI sin API key.

Ojo al objetivo del patch: parcheamos 'app.routers.estimations.generate_estimation'
(donde se USA), no donde se define. El router hizo `from ...llm_service import
generate_estimation`, así que esa es la referencia que debemos reemplazar.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient


@patch("app.routers.estimations.generate_estimation")
def test_estimate_returns_estimation(mock_generate, client: TestClient) -> None:
    # Preparamos la respuesta falsa del servicio (ahora incluye 'history').
    mock_generate.return_value = {
        "estimation": "## Estimación de prueba\n\n**Total: 40 horas**",
        "model": "gpt-4o-mini",
        "provider": "openai",
        "history": [
            {"role": "user", "content": "El cliente quiere una landing."},
            {"role": "assistant", "content": "## Estimación de prueba\n\n**Total: 40 horas**"},
        ],
    }

    response = client.post(
        "/api/v1/estimate",
        json={"transcription": "El cliente quiere una landing con formulario y blog."},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["estimation"].startswith("## Estimación")
    assert data["model"] == "gpt-4o-mini"
    assert data["provider"] == "openai"
    # El response devuelve el historial para continuar la conversación.
    assert len(data["history"]) == 2
    mock_generate.assert_called_once()


@patch("app.routers.estimations.generate_estimation")
def test_estimate_accepts_history(mock_generate, client: TestClient) -> None:
    # Multi-turn: el cliente reenvía el historial previo en la siguiente petición.
    mock_generate.return_value = {
        "estimation": "## Estimación actualizada",
        "model": "gpt-4o-mini",
        "provider": "openai",
        "history": [],
    }

    response = client.post(
        "/api/v1/estimate",
        json={
            "transcription": "Sube las horas de diseño a 60.",
            "history": [
                {"role": "user", "content": "Estima una landing."},
                {"role": "assistant", "content": "## Estimación: 40h de diseño..."},
            ],
        },
    )

    assert response.status_code == 200
    # El router debe pasar el historial al servicio (como argumento 'history').
    _, kwargs = mock_generate.call_args
    assert kwargs["history"] is not None
    assert len(kwargs["history"]) == 2
    assert kwargs["history"][0]["role"] == "user"


def test_estimate_rejects_invalid_role(client: TestClient) -> None:
    # 'role' solo admite user/assistant -> un rol inválido da 422 (validación Pydantic).
    response = client.post(
        "/api/v1/estimate",
        json={
            "transcription": "Continúa.",
            "history": [{"role": "system", "content": "no permitido aquí"}],
        },
    )
    assert response.status_code == 422


def test_estimate_rejects_empty_transcription(client: TestClient) -> None:
    # Sin 'transcription' -> Pydantic devuelve 422 sin tocar el servicio.
    response = client.post("/api/v1/estimate", json={})
    assert response.status_code == 422


@patch("app.routers.estimations.generate_estimation")
def test_estimate_config_error_returns_400(mock_generate, client: TestClient) -> None:
    # Si el servicio lanza ValueError (p. ej. falta API key) -> 400.
    mock_generate.side_effect = ValueError("Falta OPENAI_API_KEY en el .env")

    response = client.post(
        "/api/v1/estimate",
        json={"transcription": "Una transcripción cualquiera."},
    )
    assert response.status_code == 400


@patch("app.routers.estimations.generate_estimation")
def test_estimate_provider_error_returns_502(mock_generate, client: TestClient) -> None:
    # Si el proveedor falla (red, cuota, etc.) -> 502.
    mock_generate.side_effect = RuntimeError("API caída")

    response = client.post(
        "/api/v1/estimate",
        json={"transcription": "Una transcripción cualquiera."},
    )
    assert response.status_code == 502
