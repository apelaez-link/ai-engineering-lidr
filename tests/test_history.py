"""Test de la ventana deslizante (gestión del historial multi-turn).

Prueba directamente la función pura _apply_sliding_window, sin tocar el LLM.
Demuestra la estrategia del material 05: conservar solo los últimos N turnos.
"""

from app.services.llm_service import _apply_sliding_window


def _conversation(num_messages: int) -> list[dict]:
    """Genera una conversación alternando user/assistant."""
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
        for i in range(num_messages)
    ]


def test_window_keeps_all_when_under_limit() -> None:
    convo = _conversation(4)  # 2 turnos
    result = _apply_sliding_window(convo, max_turns=10)
    assert result == convo  # no se descarta nada


def test_window_trims_oldest_when_over_limit() -> None:
    convo = _conversation(30)  # 15 turnos
    result = _apply_sliding_window(convo, max_turns=5)
    # max_turns=5 -> 10 mensajes; conserva los 10 últimos.
    assert len(result) == 10
    assert result[0]["content"] == "msg 20"
    assert result[-1]["content"] == "msg 29"
