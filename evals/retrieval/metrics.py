"""Métricas de recuperación (sesión 10): precisión@k. Funciones PURAS (sin BBDD).

precisión@k = (nº de resultados relevantes entre los k primeros) / k

Aquí un "resultado" es un CHUNK y es relevante si su budget_id está en el conjunto
relevante de la consulta (verdad-terreno anotada a nivel de presupuesto). Dividimos
SIEMPRE entre k (no entre el nº devuelto): si una config devuelve menos de k, esos
huecos cuentan como no-relevantes, que es lo justo al comparar configuraciones.

Nota de techo: si una consulta tiene pocos chunks relevantes en el corpus (p.ej. un
solo presupuesto con 3 chunks), su precisión@5 no puede pasar de 3/5. Es una propiedad
del corpus, no de la técnica; por eso comparamos configs ENTRE SÍ, no contra 1.0.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def precision_at_k(
    retrieved_budget_ids: Sequence[str], relevant_budget_ids: Iterable[str], k: int
) -> float:
    """Precisión@k de una lista de chunks recuperados (identificados por su budget_id).

    Args:
        retrieved_budget_ids: budget_id de cada chunk devuelto, EN ORDEN de ranking.
        relevant_budget_ids: conjunto de presupuestos relevantes para la consulta.
        k: corte (5 en la sesión 10).
    """
    if k <= 0:
        raise ValueError("k debe ser > 0")
    relevant = set(relevant_budget_ids)
    top_k = retrieved_budget_ids[:k]
    hits = sum(1 for bid in top_k if bid in relevant)
    return hits / k


def mean(values: Sequence[float]) -> float:
    """Media aritmética (0.0 si la secuencia está vacía)."""
    return sum(values) / len(values) if values else 0.0
