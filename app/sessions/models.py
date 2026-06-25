"""Estructuras de datos de la memoria conversacional (sesión 05).

Tres modelos que, juntos, dan "memoria" al estimador:

  1. ProjectMetadata — los HECHOS conocidos del proyecto (contexto enriquecido).
     Se acumulan turno a turno SIN perder lo aprendido antes (método merge).

  2. ConversationHistory — el historial de turnos user/assistant con una VENTANA
     DESLIZANTE: cuando supera MAX_TURNS pares, descarta los más antiguos para que
     el contexto que mandamos al LLM no crezca sin control (ni el coste con él).

  3. Session — agrupa un session_id con su historial y sus metadatos.

Nota de diseño: el system prompt NO se guarda en el historial. Se regenera en cada
llamada a partir del project_metadata actual (los hechos pueden haber cambiado), y
se antepone a los turnos recientes en to_messages_list().
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

# Nº de turnos (pares user+assistant) que conserva el historial por defecto.
# Configurable por sesión y desde app/config.py (max_history_turns).
DEFAULT_MAX_TURNS = 6


class ProjectMetadata(BaseModel):
    """Hechos conocidos del proyecto que se van acumulando en la conversación.

    Es el "contexto enriquecido" que inyectamos en cada nuevo prompt para que el
    LLM no parta de cero: si en el turno 1 el cliente dijo que el equipo es de 4
    personas, en el turno 5 seguimos sabiéndolo aunque no lo repita.

    Todos los campos son OPCIONALES / vacíos por defecto: una sesión recién creada
    no sabe nada todavía. El extractor LLM (metadata_extractor.py) los rellena.
    """

    project_name: str | None = Field(
        default=None, description="Project name if mentioned by the client."
    )
    assumed_team_size: int | None = Field(
        default=None, description="Assumed team size agreed/mentioned in the conversation."
    )
    mentioned_technologies: list[str] = Field(
        default_factory=list,
        description="Technologies, frameworks or platforms mentioned so far.",
    )
    agreed_scope: str = Field(
        default="", description="Free-text description of the scope agreed so far."
    )

    def merge(self, other: "ProjectMetadata") -> "ProjectMetadata":
        """Combina ESTE metadata con otro SIN perder hechos previos.

        Regla didáctica: la memoria solo CRECE, nunca olvida un hecho conocido.
          - Escalares (project_name, assumed_team_size): si `other` aporta un valor
            nuevo (no None), gana el nuevo; si no, conservamos el que ya teníamos.
          - mentioned_technologies: UNIÓN de ambas listas, sin duplicados y
            preservando el orden de aparición.
          - agreed_scope: si `other` trae un texto no vacío, lo tomamos como el
            alcance más reciente; si viene vacío, conservamos el anterior.

        Devuelve un NUEVO ProjectMetadata (no muta ninguno de los dos), lo que hace
        el merge fácil de razonar y de testear.
        """
        # Escalares: el valor nuevo sustituye al viejo solo si aporta información.
        project_name = other.project_name if other.project_name is not None else self.project_name
        assumed_team_size = (
            other.assumed_team_size
            if other.assumed_team_size is not None
            else self.assumed_team_size
        )

        # Tecnologías: unión preservando orden (las previas primero, luego las nuevas
        # que no estuvieran ya). Comparamos en minúsculas para no duplicar por mayúsculas.
        merged_techs: list[str] = list(self.mentioned_technologies)
        seen = {t.lower() for t in merged_techs}
        for tech in other.mentioned_technologies:
            if tech.lower() not in seen:
                merged_techs.append(tech)
                seen.add(tech.lower())

        # Alcance: el texto más reciente gana, pero solo si no viene vacío.
        agreed_scope = other.agreed_scope.strip() or self.agreed_scope

        return ProjectMetadata(
            project_name=project_name,
            assumed_team_size=assumed_team_size,
            mentioned_technologies=merged_techs,
            agreed_scope=agreed_scope,
        )

    def is_empty(self) -> bool:
        """True si no se conoce ningún hecho todavía (útil para renderizar el prompt)."""
        return (
            self.project_name is None
            and self.assumed_team_size is None
            and not self.mentioned_technologies
            and not self.agreed_scope.strip()
        )


class Turn(BaseModel):
    """Un turno individual de la conversación (un solo mensaje).

    El `role` es siempre "user" o "assistant": el system prompt NO se guarda aquí,
    porque se regenera dinámicamente a partir del project_metadata en cada llamada.
    """

    role: str = Field(description="Either 'user' or 'assistant' (never 'system').")
    content: str = Field(description="Raw text content of this turn.")


class ConversationHistory(BaseModel):
    """Historial de turnos con VENTANA DESLIZANTE.

    Concepto clave de la lección de memoria conversacional: un LLM no recuerda nada
    entre llamadas, así que SOMOS NOSOTROS quienes reenviamos el historial en cada
    petición. Pero el contexto cuesta tokens (y dinero) y tiene un límite, así que no
    podemos reenviar la conversación entera indefinidamente. La ventana deslizante
    conserva solo los últimos MAX_TURNS pares user+assistant y descarta los antiguos.

    Un "turno" en el sentido de la ventana = un PAR user+assistant. Por eso el límite
    efectivo de mensajes es MAX_TURNS * 2 (más el system, que se añade aparte).
    """

    turns: list[Turn] = Field(default_factory=list)
    max_turns: int = Field(default=DEFAULT_MAX_TURNS, ge=1)

    def add(self, role: str, content: str) -> None:
        """Añade un mensaje al historial y aplica la ventana deslizante.

        Args:
            role: "user" o "assistant" (rechazamos "system": no va en el historial).
            content: el texto del mensaje.

        Raises:
            ValueError: si el role no es user/assistant.
        """
        if role not in ("user", "assistant"):
            raise ValueError(
                f"Invalid role '{role}'. Conversation history only stores "
                f"'user' and 'assistant' turns (system is regenerated each call)."
            )
        self.turns.append(Turn(role=role, content=content))
        self._apply_sliding_window()

    def _apply_sliding_window(self) -> None:
        """Descarta los PARES más antiguos cuando se supera max_turns.

        Trabajamos en unidades de mensajes: max_turns pares = max_turns * 2 mensajes.
        Si nos pasamos, recortamos por el principio (los más antiguos) hasta volver
        al límite. Cortamos en número PAR de mensajes para no dejar un user huérfano
        sin su assistant (mantener pares íntegros ayuda a que el LLM lea coherente).
        """
        max_messages = self.max_turns * 2
        if len(self.turns) <= max_messages:
            return
        # Nº de mensajes a descartar, redondeado a par para no romper la alternancia.
        overflow = len(self.turns) - max_messages
        if overflow % 2 == 1:
            overflow += 1
        self.turns = self.turns[overflow:]

    def to_messages_list(self, system_prompt: str) -> list[dict[str, str]]:
        """Construye la lista de mensajes [system, *turnos recientes] para el LLM.

        El system prompt se PASA aquí (no se guarda en el historial) porque se
        regenera en cada llamada a partir del project_metadata vigente: si los
        hechos del proyecto cambiaron, el system debe reflejarlos.

        Returns:
            Lista de dicts {"role": ..., "content": ...} lista para litellm/Instructor.
        """
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages.extend({"role": t.role, "content": t.content} for t in self.turns)
        return messages


class Session(BaseModel):
    """Una sesión conversacional: historial + metadatos acumulados + identidad.

    Es la unidad que vive en el store. Cada cliente que abre el estimador obtiene
    una Session con un session_id único; a partir de ahí, todos sus turnos y los
    hechos que va dando se acumulan aquí.
    """

    session_id: str = Field(description="Unique session identifier (uuid4).")
    history: ConversationHistory = Field(default_factory=ConversationHistory)
    project_metadata: ProjectMetadata = Field(default_factory=ProjectMetadata)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
