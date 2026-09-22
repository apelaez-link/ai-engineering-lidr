"""Estado tipado del grafo de estimación (sesión 13, Nivel 1).

El estado es el "hilo" que recorre el grafo: cada nodo lee lo que necesita y devuelve
una ACTUALIZACIÓN PARCIAL (un dict con solo las claves que toca). LangGraph funde esa
actualización en el estado según la política de cada clave:

  - Clave normal  → la actualización SOBREESCRIBE el valor anterior.
  - Clave con REDUCER (Annotated[tipo, fn]) → la actualización se COMBINA con la fn.
    Aquí `budget_matches` y `errors` usan `operator.add`: los nodos ACUMULAN (append)
    en vez de sobreescribir. Es el requisito del enunciado (≥1 reducer acumulador) y lo
    que permitirá, en el directo/S14, que varias búsquedas en PARALELO (Send) aporten
    cada una sus matches sin pisarse.

Mantenemos todos los valores JSON-serializables (str/list/dict), no objetos Pydantic,
porque el checkpointer (Nivel 2) SERIALIZA el estado en Postgres. Convertimos a/desde
Pydantic dentro de los nodos, en los bordes.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class EstimationState(TypedDict, total=False):
    """Estado compartido del grafo. `total=False`: los nodos devuelven claves parciales.

    Campos:
      transcript:      entrada — la transcripción de la reunión.
      requirements:    salida de extract_requirements (requisitos funcionales en bruto).
      components:      salida de classify_components — [{name, search_query}, ...].
      budget_matches:  ACUMULADOR (reducer operator.add) — evidencia recuperada por
                       search_budgets: [{component, chunk_id, document_id, content, score}].
      estimate:        salida de generate_estimate — Estimate.model_dump() (o None).
      citation_report: salida de validate_and_consolidate — CitationReport.model_dump().
      status:          "validated" | "needs_review" (lo fija la validación; Nivel 3).
      errors:          ACUMULADOR (reducer) — mensajes de incidencia recogidos por los nodos.
    """

    transcript: str
    requirements: list[str]
    components: list[dict[str, str]]
    budget_matches: Annotated[list[dict[str, Any]], operator.add]
    estimate: dict[str, Any] | None
    citation_report: dict[str, Any] | None
    status: str
    errors: Annotated[list[str], operator.add]
