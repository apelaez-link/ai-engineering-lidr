"""Test que verifica que el scaffold del proyecto está completo.

Convierte la comprobación de estructura en algo que el CI ejecuta y reporta
como un test más. Complementa a scripts/check_structure.py.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_PATHS = [
    "app/main.py",
    "app/config.py",
    "app/logging_config.py",
    "app/services/llm_service.py",
    "app/services/llm_wrapper.py",
    "app/services/evaluation.py",
    "app/cache/llm_cache.py",
    "app/context/examples.py",
    "app/routers/estimations.py",
    "app/static/sse_demo.html",
    "streamlit_app.py",
    "docker-compose.yml",
    "fixtures/sample_transcription.txt",
    ".env.example",
]


def test_required_paths_exist() -> None:
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    assert not missing, f"Rutas faltantes: {missing}"
