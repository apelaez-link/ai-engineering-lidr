"""Configuración compartida de pytest (fixtures).

Un `conftest.py` es especial: pytest lo descubre solo y sus fixtures quedan
disponibles para todos los tests de la carpeta sin importarlos.

Aquí definimos variables de entorno de prueba ANTES de importar la app, para
que funcione en CI (donde no hay un .env real) sin tocar tus claves reales.
"""

import os

import pytest
from fastapi.testclient import TestClient

# Valores ficticios suficientes para arrancar la app en tests/CI.
# No se hace ninguna llamada real al LLM: en los tests lo mockeamos.
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("OPENAI_API_KEY", "test-key-for-ci")
os.environ.setdefault("OPENAI_MODEL", "gpt-4o-mini")
# Caché en memoria y logging silencioso para los tests.
os.environ.setdefault("CACHE_BACKEND", "memory")
os.environ.setdefault("ENV", "development")
os.environ.setdefault("LOG_LEVEL", "WARNING")

# Se importan DESPUÉS de fijar el entorno (por eso el noqa: E402).
from app.cache import get_cache  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clear_caches():
    """Limpia las cachés de proceso antes y después de cada test.

    get_settings y get_cache están cacheadas con @lru_cache. Si un test cambia la
    config o llena la caché de respuestas, queremos que el siguiente empiece limpio.
    autouse=True la aplica a todos los tests.
    """
    get_settings.cache_clear()
    get_cache.cache_clear()
    yield
    get_settings.cache_clear()
    get_cache.cache_clear()


@pytest.fixture
def client() -> TestClient:
    """Cliente HTTP de prueba que habla con la app en memoria (sin levantar servidor)."""
    return TestClient(app)
