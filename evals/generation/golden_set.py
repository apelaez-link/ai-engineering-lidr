"""Golden set de GENERACIÓN (sesión 11) = golden set de la S10 + ground_truth.

No partimos de cero: reutilizamos las 5 consultas del golden set de recuperación
(sesión 10) y a cada una le añadimos una **respuesta de referencia** (ground_truth): la
estimación esperada para esa descripción, según criterio de experto. Ese ground_truth es
una de las cuatro entradas que RAGAS necesita (question, answer, contexts, ground_truth).

Las horas de referencia se han fijado a partir de las horas reales por componente de los
presupuestos históricos relevantes (las mismas que ve el retrieval), no inventadas: así el
ground_truth es un objetivo realista contra el que medir la generación.
"""

from __future__ import annotations

from dataclasses import dataclass

from evals.retrieval.golden_set import GOLDEN_SET as _RETRIEVAL_GOLDEN

# Respuesta de referencia por consulta (criterio de experto sobre el histórico real).
# En inglés, coherente con el corpus y con las estimaciones que genera el pipeline.
GROUND_TRUTH: dict[str, str] = {
    "Q1": (
        "Historical budgets cover the storefront well: product catalog ~180h, shopping "
        "cart & checkout ~160h, payment processing ~130h, promotions/coupons ~120h. "
        "Product search is part of the catalog work. Reference total ~590h."
    ),
    "Q2": (
        "Patient-facing healthcare: appointment booking ~160h, video consultation ~200h, "
        "GDPR consent ~150h, electronic health records ~150h. Reference total ~660h."
    ),
    "Q3": (
        "Secure mobile banking: OAuth 2.0 authentication ~120h, PSD2 compliance and "
        "payments ~200h, double-entry ledger ~160h. Reference total ~480h."
    ),
    "Q4": (
        "Real-time monitoring: metrics/OEE dashboard ~210h, machine monitoring and "
        "maintenance ~200h, real-time cash-position dashboard ~170h. Reference total ~580h."
    ),
    "Q5": (
        "Inventory and stock: warehouse management/WMS ~230h, pharmacy inventory ~150h, "
        "cold-chain tracking ~170h, labeling ~90h. Reference total ~640h."
    ),
}


@dataclass(frozen=True)
class GenerationGoldenQuery:
    """Consulta del golden set enriquecida con la respuesta de referencia."""

    id: str
    query: str
    relevant_budget_ids: frozenset[str]
    ground_truth: str


GENERATION_GOLDEN_SET: list[GenerationGoldenQuery] = [
    GenerationGoldenQuery(
        id=q.id,
        query=q.query,
        relevant_budget_ids=q.relevant_budget_ids,
        ground_truth=GROUND_TRUTH[q.id],
    )
    for q in _RETRIEVAL_GOLDEN
]
