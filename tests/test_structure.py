"""Test que verifica que el scaffold del proyecto está completo (sesión 04).

Convierte la comprobación de estructura en algo que el CI ejecuta y reporta
como un test más. Complementa a scripts/check_structure.py.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_PATHS = [
    "app/main.py",
    "app/config.py",
    "app/logging_config.py",
    "app/schemas.py",
    "app/services/llm_service.py",
    "app/services/llm_wrapper.py",
    "app/services/evaluation.py",
    "app/cache/llm_cache.py",
    "app/routers/estimations.py",
    "app/prompts/loader.py",
    "app/prompts/estimation/v1/system.j2",
    "app/prompts/estimation/v1/user.j2",
    "app/prompts/estimation/v1/examples.j2",
    "app/prompts/estimation/v2/system.j2",
    "app/prompts/estimation/v2/user.j2",
    "app/prompts/estimation/v2/examples.j2",
    "app/static/sse_demo.html",
    "streamlit_app.py",
    "docker-compose.yml",
    "fixtures/sample_transcription.txt",
    ".env.example",
    "tests/prompts/test_estimation_v1.py",
]


def test_required_paths_exist() -> None:
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    assert not missing, f"Rutas faltantes: {missing}"
