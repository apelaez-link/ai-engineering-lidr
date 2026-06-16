"""Cargador y renderizador de templates Jinja2 para los prompts del estimador.

Centraliza dos responsabilidades:
  1. Cargar los templates desde disco (usando FileSystemLoader de Jinja2).
  2. Renderizarlos con el contexto de cada petición y devolver el par (system, user).

El versionado es explícito: la carpeta `estimation/v1/` contiene los templates de
la versión 1; `estimation/v2/` la variación deliberada. La versión activa se pasa
como parámetro en cada llamada. Esto permite experimentar y comparar versiones
sin modificar código (solo configuración o query param).

El hash del system prompt renderizado se registra con structlog para facilitar
la depuración en producción: si el comportamiento cambia, podemos saber exactamente
qué template se usó en cada llamada comparando los hashes.
"""

import hashlib
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.schemas import EstimationRequest

# Raíz del paquete de prompts: la carpeta donde vive este loader.py
PROMPTS_DIR = Path(__file__).parent

log = structlog.get_logger()

# Entorno Jinja2 reutilizable (se crea una sola vez al importar el módulo).
# - trim_blocks/lstrip_blocks: elimina los saltos de línea extra que genera la
#   lógica de control ({% if %}, {% for %}) para que el prompt quede limpio.
# - StrictUndefined: si una variable del contexto no existe, Jinja2 lanza error
#   en lugar de sustituir por cadena vacía (facilita detectar errores de typo).
_env = Environment(
    loader=FileSystemLoader(PROMPTS_DIR),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=False,
    undefined=StrictUndefined,
)


def render_estimation_prompt(
    request: EstimationRequest, version: str = "v1"
) -> tuple[str, str]:
    """Renderiza el par (system_prompt, user_prompt) para la petición dada.

    Args:
        request:  Schema Pydantic con todos los parámetros de la estimación.
        version:  Versión del template a usar ("v1", "v2", ...).

    Returns:
        Tupla (system, user) con los prompts ya renderizados listos para el LLM.

    Raises:
        jinja2.TemplateNotFound: si la versión solicitada no existe en disco.
        jinja2.UndefinedError:   si el template referencia una variable no proporcionada.
    """
    system_tpl = _env.get_template(f"estimation/{version}/system.j2")
    user_tpl = _env.get_template(f"estimation/{version}/user.j2")

    # Contexto que se pasa a los templates. Usamos .value en los enums para que
    # Jinja2 reciba cadenas simples (p. ej. "phases_table"), no objetos Enum.
    context = {
        "project_type": request.project_type.value,
        "detail_level": request.detail_level.value,
        "output_format": request.output_format.value,
        "description": request.description,
        "reference_projects": request.reference_projects,  # None si no se proporcionaron
    }

    system = system_tpl.render(**context)
    user = user_tpl.render(**context)

    # Registramos versión + hash (12 chars del SHA-256) para trazabilidad en producción.
    # Así podemos correlacionar comportamientos del LLM con versiones concretas del prompt.
    log.info(
        "prompt_rendered",
        version=version,
        system_hash=hashlib.sha256(system.encode()).hexdigest()[:12],
    )

    return system, user
