"""Golden set de recuperación (sesión 10): consultas anotadas a mano.

Cada consulta es una "descripción de proyecto a estimar" (como la que escribiría un
comercial) y su conjunto de presupuestos RELEVANTES, anotado a mano según el contenido
real del corpus (15 presupuestos, sectores finance/ecommerce/healthcare/industrial).

La relevancia se define a nivel de PRESUPUESTO (budget_id). En la métrica, un chunk
recuperado cuenta como acierto si su budget_id está en el conjunto relevante (un
presupuesto tiene 2-3 chunks; ver evals/retrieval/metrics.py). Anotamos por
presupuesto —no por chunk— porque es lo que un humano juzga sin ambigüedad ("¿este
presupuesto histórico es un buen antecedente para estimar este proyecto?").

Las 5 consultas están elegidas para EJERCITAR distintos ejes de la recuperación:
  Q1  señal mixta léxica+semántica (flujo de e-commerce)         -> 3 presupuestos
  Q2  paráfrasis semántica sin solape léxico fuerte (telemedicina) -> 2 presupuestos
  Q3  términos EXACTOS raros (OAuth 2.0, PSD2): donde el full-text debería lucir -> 1
  Q4  concepto ambiguo entre dominios ("tiempo real"): donde el reranker debería lucir -> 2
  Q5  concepto puente entre dominios ("inventario"): finanzas/salud vs industria -> 2

Cada anotación lleva un `rationale` corto que justifica por qué esos presupuestos y no
otros (p.ej. por qué el móvil de moda con AR NO cuenta como "tienda con catálogo").
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GoldenQuery:
    """Una consulta del golden set con su verdad-terreno a nivel de presupuesto."""

    id: str
    query: str
    relevant_budget_ids: frozenset[str]
    rationale: str = field(default="")


GOLDEN_SET: list[GoldenQuery] = [
    GoldenQuery(
        id="Q1",
        query=(
            "Online e-commerce storefront with product catalog, search, shopping cart "
            "and checkout"
        ),
        relevant_budget_ids=frozenset(
            {"BUD-2024-045", "BUD-2024-090", "BUD-2023-131"}
        ),
        rationale=(
            "Tiendas/mercados con catálogo, pedidos y pago: headless e-commerce (045), "
            "portal de pedidos B2B (090) y marketplace de alimentación con pago (131). "
            "Se EXCLUYE el móvil de moda con AR (077): va de wishlist y prueba con "
            "realidad aumentada, no de catálogo+checkout."
        ),
    ),
    GoldenQuery(
        id="Q2",
        query=(
            "Let patients book medical appointments and consult a doctor remotely over "
            "video"
        ),
        relevant_budget_ids=frozenset({"BUD-2023-140", "BUD-2024-058"}),
        rationale=(
            "Salud de cara al paciente: plataforma de videoconsulta/telemedicina (140) "
            "y portal del paciente con reserva de cita (058). Se EXCLUYEN inventario de "
            "farmacia (063) y captura de ensayos clínicos (118): no son 'paciente pide "
            "cita / ve al médico'. Paráfrasis: la consulta no dice 'telemedicine'."
        ),
    ),
    GoldenQuery(
        id="Q3",
        query="Secure mobile banking API with OAuth 2.0 authentication and PSD2 payment compliance",
        relevant_budget_ids=frozenset({"BUD-2024-014"}),
        rationale=(
            "Sonda LÉXICA: 'OAuth 2.0' y 'PSD2' son términos exactos y raros que solo "
            "aparecen en la banca móvil (014). Un presupuesto, 3 chunks -> techo de "
            "precisión@5 = 0.6. Mide si la config clava la coincidencia exacta."
        ),
    ),
    GoldenQuery(
        id="Q4",
        query="Real-time monitoring dashboard with live operational metrics",
        relevant_budget_ids=frozenset({"BUD-2023-099", "BUD-2024-102"}),
        rationale=(
            "'Tiempo real' es ambiguo entre dominios: MES de fábrica con monitorización "
            "de máquinas en tiempo real (099) y dashboard de tesorería con posiciones de "
            "caja en tiempo real (102). Buen test de si la recuperación/rerank distingue "
            "los 'monitoring/dashboard' de verdad del ruido."
        ),
    ),
    GoldenQuery(
        id="Q5",
        query="Inventory tracking and stock management for warehouses and pharmacies",
        relevant_budget_ids=frozenset({"BUD-2024-133", "BUD-2024-063"}),
        rationale=(
            "'Inventario' es un puente entre dominios: gestión de almacén/WMS industrial "
            "(133) e inventario de farmacia con cadena de frío en salud (063). La palabra "
            "'inventory' es un ancla léxica; 'warehouse management' es más semántico."
        ),
    ),
]
