"""Tests del middleware de token de servicio (sesión 15).

Probamos las 3 reglas: /health exento, protegido sin token -> 401, protegido con token
válido -> pasa el middleware (llega al routing). Usamos una ruta inexistente como "sonda"
protegida: así comprobamos el middleware sin ejecutar un endpoint real (que llamaría al LLM).
El middleware corre ANTES del routing, así que sin token devuelve 401 y con token devuelve
404 (pasó el middleware, no existe la ruta).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

PROBE = "/__protected_probe__"


def test_health_is_exempt_even_with_token(monkeypatch):
    monkeypatch.setenv("AI_SERVICE_TOKEN", "secret123")
    get_settings.cache_clear()
    client = TestClient(app)
    assert client.get("/health").status_code == 200  # liveness siempre accesible
    get_settings.cache_clear()


def test_protected_route_requires_token(monkeypatch):
    monkeypatch.setenv("AI_SERVICE_TOKEN", "secret123")
    get_settings.cache_clear()
    client = TestClient(app)

    # Sin cabecera -> 401 (bloqueado por el middleware, antes del routing).
    assert client.get(PROBE).status_code == 401
    # Cabecera incorrecta -> 401.
    assert client.get(PROBE, headers={"X-Service-Token": "wrong"}).status_code == 401
    # Cabecera correcta -> pasa el middleware; la ruta no existe -> 404 (no 401).
    ok = client.get(PROBE, headers={"X-Service-Token": "secret123"})
    assert ok.status_code == 404
    get_settings.cache_clear()


def test_auth_disabled_when_token_empty(monkeypatch):
    monkeypatch.setenv("AI_SERVICE_TOKEN", "")
    get_settings.cache_clear()
    client = TestClient(app)
    # Sin token configurado -> auth desactivada: la sonda va directa al routing (404).
    assert client.get(PROBE).status_code == 404
    get_settings.cache_clear()
