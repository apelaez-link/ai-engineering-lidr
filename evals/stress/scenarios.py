"""Perfiles multi-turno del stress test (sesión 06, BLOQUE 2).

Cada perfil es una conversación SIMULADA con el estimador: una lista de turnos que
el runner reproduce uno a uno contra el endpoint conversacional. Sirven para someter
al CAG a tres "formas de estrés" distintas y ver dónde empieza a degradarse:

  - "growing"       : la conversación CRECE de forma coherente, turno a turno se
                      añaden requisitos sin contradecir nada. Mide cómo escalan
                      latencia/coste/tokens con el tamaño acumulado del contexto.
  - "pivot"         : a mitad de conversación (turno 5) el cliente CAMBIA el stack
                      tecnológico. Mide si la memoria adopta el dato nuevo (¿aparece
                      la nueva tecnología en los turnos posteriores?).
  - "contradiction" : el cliente da un presupuesto (30k) y más tarde otro (80k). Mide
                      qué hecho preserva la memoria cuando dos datos se contradicen.

ESTRUCTURA DE CADA TURNO — tupla ``(turn_index, transcript, fact_to_remember)``:
  - turn_index       : índice 1-based del turno dentro de la conversación.
  - transcript       : el texto que el cliente envía en ese turno.
  - fact_to_remember : string CORTO que ``MemoryDriftMetric`` buscará (case-insensitive)
                       en el snapshot de la sesión en turnos POSTERIORES. Es el "hecho
                       que no se debe olvidar". Puede ser "" en turnos donde no rastreamos
                       ningún hecho nuevo; el runner solo evalúa drift cuando hay fact.

Los textos están en INGLÉS (es el idioma del dominio del estimador y de los prompts);
los comentarios, en español didáctico, según la convención del proyecto.
"""

from __future__ import annotations

# Tipo de un turno del escenario. Lo dejamos explícito para que el runner y los
# tests compartan el contrato sin ambigüedad.
ScenarioTurn = tuple[int, str, str]


# ── Perfil "growing": requisitos coherentes que se acumulan ───────────────────
# El nombre del proyecto ("Helios") se fija en el turno 1 y NO debe perderse: es el
# fact que rastreamos en todos los turnos siguientes. La conversación solo añade
# alcance, nunca lo contradice.
GROWING: list[ScenarioTurn] = [
    (
        1,
        "We are starting project Helios, a web SaaS for solar panel fleet monitoring. "
        "We need a rough estimate to begin planning.",
        "Helios",  # fact: el nombre del proyecto, fijado en el turno 1
    ),
    (
        2,
        "Add real-time dashboards showing per-panel energy output and alerts.",
        "Helios",
    ),
    (
        3,
        "We also need role-based access control for installers, operators and admins.",
        "Helios",
    ),
    (
        4,
        "Include a mobile app for field technicians to log maintenance visits offline.",
        "Helios",
    ),
    (
        5,
        "Add a billing module that invoices customers monthly based on energy produced.",
        "Helios",
    ),
    (
        6,
        "We want multi-tenant support so we can resell Helios to other solar operators.",
        "Helios",
    ),
    (
        7,
        "Add an analytics export to CSV and a public status page for end customers.",
        "Helios",
    ),
    (
        8,
        "Finally, please give me the consolidated estimate including everything discussed.",
        "Helios",
    ),
]


# ── Perfil "pivot": cambio de stack a mitad de conversación ───────────────────
# Arrancamos con un stack (Django + React) y en el turno 5 PIVOTAMOS a otro
# (Go + Vue). A partir de ahí el fact a recordar es la NUEVA tecnología: queremos
# ver si la memoria adopta el cambio (no que se quede anclada en lo viejo).
PIVOT: list[ScenarioTurn] = [
    (
        1,
        "We want to build Orion, an internal tool for inventory management. "
        "Our default stack is Django on the backend and React on the frontend.",
        "Django",  # fact inicial: el stack de partida
    ),
    (
        2,
        "It should support barcode scanning and bulk stock adjustments.",
        "Django",
    ),
    (
        3,
        "Add supplier management and automatic reorder thresholds.",
        "Django",
    ),
    (
        4,
        "We need audit logs for every stock movement.",
        "Django",
    ),
    (
        5,
        "Important change: drop Django, we will build the backend in Go (Golang) instead. "
        "Please re-estimate with Go as the backend language.",
        "Go",  # PIVOTE: a partir de aquí el fact relevante es la nueva tecnología
    ),
    (
        6,
        "The frontend also moves from React to Vue. Account for the migration.",
        "Go",
    ),
    (
        7,
        "Add a reporting dashboard on top of the new Go backend.",
        "Go",
    ),
    (
        8,
        "Give me the final estimate assuming the Go backend and Vue frontend.",
        "Go",
    ),
]


# ── Perfil "contradiction": dos presupuestos incompatibles ────────────────────
# En el turno 3 el cliente dice un presupuesto (30k) y en el turno 8 dice otro
# (80k). El hecho que DEBE preservarse es el MÁS RECIENTE y explícito (80k): cuando
# un cliente corrige un dato, la memoria debería quedarse con la última versión.
# Por eso el fact rastreado en los turnos posteriores al 8 es "80k".
CONTRADICTION: list[ScenarioTurn] = [
    (
        1,
        "We want Atlas, a data pipeline to consolidate sales data from several sources.",
        "Atlas",  # nombre del proyecto, contexto base
    ),
    (
        2,
        "It should ingest CSV uploads and a couple of REST APIs daily.",
        "Atlas",
    ),
    (
        3,
        "Our budget for this is 30k EUR maximum, please keep the scope realistic.",
        "30k",  # primer presupuesto declarado
    ),
    (
        4,
        "Add data quality checks and alerting on failed ingestions.",
        "30k",
    ),
    (
        5,
        "We also need a small dashboard to monitor pipeline health.",
        "30k",
    ),
    (
        6,
        "Add historical backfill for the last two years of data.",
        "30k",
    ),
    (
        7,
        "Include role-based access so finance and ops see different views.",
        "30k",
    ),
    (
        8,
        "Correction: we secured more funding, the budget is now 80k EUR, not 30k. "
        "Please re-estimate against the 80k budget.",
        "80k",  # presupuesto CORREGIDO: este es el que debe preservarse a partir de aquí
    ),
]


# Registro de escenarios por nombre, para que el runner los seleccione por --scenarios.
SCENARIOS: dict[str, list[ScenarioTurn]] = {
    "growing": GROWING,
    "pivot": PIVOT,
    "contradiction": CONTRADICTION,
}


def get_scenario(name: str) -> list[ScenarioTurn]:
    """Devuelve la lista de turnos de un escenario por nombre.

    Raises:
        KeyError: con un mensaje claro si el nombre no existe (ayuda al CLI).
    """
    try:
        return SCENARIOS[name]
    except KeyError as exc:
        valid = ", ".join(sorted(SCENARIOS))
        raise KeyError(f"Unknown scenario '{name}'. Valid scenarios: {valid}.") from exc
