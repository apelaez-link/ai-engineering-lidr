"""Test del corazón CAG: comprobar que los ejemplos se inyectan en el prompt.

No llama al LLM; solo verifica que _build_system_prompt() incluye el contenido
de los ejemplos estáticos. Si alguien borra la inyección de contexto por error,
este test lo detecta.
"""

from app.context.examples import ESTIMATION_EXAMPLES
from app.services.llm_service import _build_system_prompt


def test_system_prompt_injects_examples() -> None:
    prompt = _build_system_prompt()

    # El rol del modelo debe estar definido.
    assert "estimador" in prompt.lower()

    # El resumen de cada ejemplo debe aparecer literalmente dentro del prompt.
    for ejemplo in ESTIMATION_EXAMPLES:
        assert ejemplo["meeting_summary"] in prompt
