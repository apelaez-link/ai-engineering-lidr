"""Estado del equipo multi-agente (sesión 14).

Extiende el estado de estimación de la S13 con lo que el equipo necesita coordinar:
  - `status`: dónde está la estimación (validated / needs_review / approved / rejected).
  - `human_decision`: la decisión de la persona (None hasta que el HITL la fija).
  - `audit`: registro ACUMULADO de acciones (qué agente hizo qué, con qué tool) — la
    traza de auditoría del Nivel 3.

Como en la S13, todo es JSON-serializable (el checkpointer lo persiste), y `budget_matches`,
`errors` y `audit` usan el reducer `operator.add` para ACUMULAR entre nodos.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class MultiAgentState(TypedDict, total=False):
    transcript: str
    requirements: list[str]
    components: list[dict[str, str]]
    budget_matches: Annotated[list[dict[str, Any]], operator.add]
    estimate: dict[str, Any] | None
    citation_report: dict[str, Any] | None
    status: str
    human_decision: str | None
    errors: Annotated[list[str], operator.add]
    # Traza de auditoría (Nivel 3): cada agente añade su entrada al actuar.
    audit: Annotated[list[dict[str, Any]], operator.add]
