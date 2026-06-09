#!/usr/bin/env python3
"""Valida que exista la estructura de carpetas y archivos esperada del proyecto.

Pensado para ejecutarse en local o en el pipeline de CI ANTES de los tests:
si falta alguna pieza del scaffold, falla con código de salida 1 y lista qué falta.

Uso:
    uv run python scripts/check_structure.py
"""

from pathlib import Path

# La raíz del proyecto es la carpeta padre de scripts/
ROOT = Path(__file__).resolve().parent.parent

REQUIRED_PATHS = [
    "app/__init__.py",
    "app/main.py",
    "app/config.py",
    "app/logging_config.py",
    "app/routers/__init__.py",
    "app/routers/estimations.py",
    "app/services/__init__.py",
    "app/services/llm_service.py",
    "app/services/llm_wrapper.py",
    "app/services/evaluation.py",
    "app/cache/__init__.py",
    "app/cache/llm_cache.py",
    "app/context/__init__.py",
    "app/context/examples.py",
    "app/static/sse_demo.html",
    "streamlit_app.py",
    "docker-compose.yml",
    "fixtures/sample_transcription.txt",
    "tests/test_structure.py",
    "tests/test_health.py",
    "tests/test_estimate.py",
    "tests/test_wrapper.py",
    "tests/test_cache.py",
    "tests/test_evaluation.py",
    "tests/test_estimate_stream.py",
    ".env.example",
    ".gitignore",
    "pyproject.toml",
    "README.md",
]


def main() -> int:
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    if missing:
        print("❌ Faltan rutas obligatorias:")
        for path in missing:
            print(f"   - {path}")
        return 1
    print(f"✅ Estructura OK ({len(REQUIRED_PATHS)} rutas verificadas).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
