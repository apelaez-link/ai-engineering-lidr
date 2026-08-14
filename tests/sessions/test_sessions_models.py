"""Tests de los modelos de memoria conversacional (sesión 05).

Cubren las dos piezas de lógica no triviales:
  (a) ConversationHistory: la VENTANA DESLIZANTE conserva el system y, como mucho,
      los últimos MAX_TURNS pares user+assistant.
  (b) ProjectMetadata.merge: combina hechos SIN perder los previos.

No hay APIs reales: los modelos son Pydantic puro.
"""

from app.sessions.models import ConversationHistory, ProjectMetadata


# ── (a) Ventana deslizante ────────────────────────────────────────────────────

def test_sliding_window_keeps_system_and_last_max_turns() -> None:
    """Con MAX_TURNS=3 y 8 turnos completos, solo sobreviven los 3 pares más recientes.

    Comprobamos además que to_messages_list antepone SIEMPRE el system prompt y que
    los mensajes conservados son efectivamente los últimos (el más antiguo cae).
    """
    history = ConversationHistory(max_turns=3)
    for i in range(8):  # 8 pares user+assistant = 16 mensajes
        history.add("user", f"user message {i}")
        history.add("assistant", f"assistant message {i}")

    # Como mucho MAX_TURNS * 2 mensajes en el historial.
    assert len(history.turns) <= 3 * 2

    messages = history.to_messages_list("SYSTEM PROMPT")
    # El primero es siempre el system regenerado.
    assert messages[0] == {"role": "system", "content": "SYSTEM PROMPT"}
    # El nº total de mensajes no supera MAX_TURNS*2 + 1 (el system).
    assert len(messages) <= 3 * 2 + 1
    # El último par debe ser el más reciente (índice 7); el más antiguo (0) ya no está.
    contents = [m["content"] for m in messages]
    assert "assistant message 7" in contents
    assert "user message 0" not in contents


def test_sliding_window_8_turns_does_not_exceed_limit() -> None:
    """8 turnos con MAX_TURNS por defecto (6): nº de mensajes efectivos <= MAX_TURNS*2+1."""
    history = ConversationHistory()  # max_turns por defecto = 6
    for i in range(8):
        history.add("user", f"u{i}")
        history.add("assistant", f"a{i}")

    messages = history.to_messages_list("S")
    assert len(messages) <= history.max_turns * 2 + 1


def test_sliding_window_keeps_pairs_intact() -> None:
    """La ventana descarta en bloques PARES: nunca deja un 'user' huérfano al inicio."""
    history = ConversationHistory(max_turns=2)
    for i in range(5):
        history.add("user", f"u{i}")
        history.add("assistant", f"a{i}")
    # Tras la ventana, el primer turno conservado debe ser un 'user' (par íntegro).
    assert history.turns[0].role == "user"
    assert len(history.turns) % 2 == 0


def test_history_rejects_system_role() -> None:
    """El historial solo almacena user/assistant; un role inválido lanza ValueError."""
    history = ConversationHistory()
    try:
        history.add("system", "should not be stored")
        raised = False
    except ValueError:
        raised = True
    assert raised


# ── (b) Merge de ProjectMetadata ──────────────────────────────────────────────

def test_merge_does_not_lose_previous_facts() -> None:
    """El merge conserva los hechos previos y añade los nuevos (la memoria solo crece)."""
    previous = ProjectMetadata(
        project_name="FleetX",
        assumed_team_size=4,
        mentioned_technologies=["React", "PostgreSQL"],
        agreed_scope="MVP with driver tracking",
    )
    # El turno nuevo solo aporta una tecnología extra; el resto viene vacío/None.
    incoming = ProjectMetadata(
        project_name=None,
        assumed_team_size=None,
        mentioned_technologies=["AWS", "react"],  # 'react' duplicado (case-insensitive)
        agreed_scope="",
    )

    merged = previous.merge(incoming)

    # Hechos previos intactos.
    assert merged.project_name == "FleetX"
    assert merged.assumed_team_size == 4
    assert merged.agreed_scope == "MVP with driver tracking"
    # Tecnologías: unión sin duplicar 'React'/'react', con la nueva 'AWS'.
    assert merged.mentioned_technologies == ["React", "PostgreSQL", "AWS"]


def test_merge_new_values_override_when_present() -> None:
    """Un valor nuevo no nulo sustituye al previo; un alcance nuevo es el más reciente."""
    previous = ProjectMetadata(assumed_team_size=4, agreed_scope="MVP")
    incoming = ProjectMetadata(assumed_team_size=6, agreed_scope="MVP + reporting module")

    merged = previous.merge(incoming)

    assert merged.assumed_team_size == 6
    assert merged.agreed_scope == "MVP + reporting module"


def test_is_empty_detects_no_facts() -> None:
    """is_empty distingue una memoria sin hechos de una con al menos uno."""
    assert ProjectMetadata().is_empty() is True
    assert ProjectMetadata(project_name="X").is_empty() is False
