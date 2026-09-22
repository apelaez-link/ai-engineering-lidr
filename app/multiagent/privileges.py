"""Privilegio mínimo + validación de acciones + auditoría (sesión 14, Niveles 1 y 3).

Cada agente recibe SOLO las tools que su rol necesita. Esto no es estética: es seguridad.
Un worker que redacta no debe poder tocar la BBDD; uno que busca no debe poder calcular el
total. Aquí lo hacemos EXPLÍCITO y COMPROBABLE, no con un `if` escondido dentro del worker:

  - `AGENT_PRIVILEGES`: el mapa rol → tools permitidas (las 3 tools de negocio de S12).
  - `enforce_privilege(agent, tool)`: se llama ANTES de usar una tool. Si el agente no la
    tiene concedida, AUDITA el intento y lanza `PrivilegeError` (la acción se bloquea).
  - `audit_entry(agent, tool)`: la entrada que el worker añade al `audit` del estado.

La auditoría (Nivel 3) sale por structlog (`agent_action`), con quién pidió qué y si se
permitió — lo que un servicio en producción necesita para trazabilidad y post-mortem.
"""

from __future__ import annotations

from typing import Any

from app.logging_config import get_logger

logger = get_logger(component="multiagent_privileges")

# Las 3 tools de NEGOCIO (las de la sesión 12). El supervisor y el extractor de
# requisitos no tienen ninguna: el supervisor solo enruta; el extractor solo usa el LLM.
AGENT_PRIVILEGES: dict[str, frozenset[str]] = {
    "supervisor": frozenset(),
    "requirements_extractor": frozenset(),
    "budget_searcher": frozenset({"search_budgets"}),
    "estimate_generator": frozenset({"calculate_estimate"}),
    "coherence_validator": frozenset({"validate_estimate"}),
}


class PrivilegeError(PermissionError):
    """Se lanza cuando un agente intenta usar una tool que no tiene concedida."""


def is_allowed(agent: str, tool: str) -> bool:
    return tool in AGENT_PRIVILEGES.get(agent, frozenset())


def enforce_privilege(agent: str, tool: str) -> None:
    """Comprueba y AUDITA el uso de una tool. Lanza PrivilegeError si no está permitida."""
    allowed = is_allowed(agent, tool)
    logger.info("agent_action", agent=agent, tool=tool, allowed=allowed)
    if not allowed:
        raise PrivilegeError(
            f"agent '{agent}' is not allowed to use tool '{tool}' "
            f"(allowed: {sorted(AGENT_PRIVILEGES.get(agent, []))})"
        )


def audit_entry(agent: str, tool: str, **extra: Any) -> dict[str, Any]:
    """Entrada de auditoría que el worker añade al estado (`audit`, reducer acumulador)."""
    return {"agent": agent, "tool": tool, "allowed": is_allowed(agent, tool), **extra}
