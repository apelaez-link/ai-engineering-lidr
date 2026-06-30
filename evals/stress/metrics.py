"""Métricas DETERMINISTAS del stress test (sesión 06, BLOQUE 4).

Tres métricas que evalúan cada turno SIN llamar a ningún LLM ni calcular embeddings:
son baratas, reproducibles y ejecutables en CI. Esto es deliberado: el stress test
mide PRESUPUESTOS y MEMORIA, no calidad semántica (eso vendría con LLM-as-judge en
sesiones posteriores). Una métrica determinista da el mismo resultado siempre, lo que
la hace ideal para detectar regresiones.

Todas devuelven un ``MetricResult`` uniforme (name, score, passed, details), de modo
que el runner las trate de forma homogénea y vuelque sus campos a columnas del CSV.

  - LatencyBudgetMetric(budget_ms) : ¿el turno respondió dentro del presupuesto de latencia?
  - CostBudgetMetric(budget_usd)   : ¿el turno costó menos que el presupuesto?
  - MemoryDriftMetric(fact, where) : ¿la memoria sigue conteniendo el hecho clave?
    (1.0 si el fact aparece, case-insensitive, en los campos disponibles del snapshot).

Sobre el GAP (ver app/services/observation.py): el enunciado original contempla
``where=["summary", "anchors", "metadata"]``, pero en nuestra base no existen ni el
summarizer acumulativo ni el sistema de anclas. Tratamos esos campos como VACÍOS y la
búsqueda recae sobre lo que SÍ tenemos: el ProjectMetadata acumulado y (si el snapshot
lo aporta) el texto del historial. Mantenemos los tres nombres en ``where`` para que el
contrato sea idéntico al de la versión completa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricResult:
    """Resultado uniforme de evaluar una métrica sobre un turno.

    Campos:
      - name    : identificador de la métrica (p. ej. "latency_budget"). Sirve de
                  prefijo para las columnas del CSV.
      - score   : puntuación en [0.0, 1.0]. 1.0 = ideal, 0.0 = peor caso. Para las
                  métricas binarias de presupuesto/memoria es 1.0 o 0.0.
      - passed  : booleano de conveniencia (típicamente score >= umbral). Para las
                  métricas de aquí, passed == (score == 1.0).
      - details : diccionario con el "porqué" (valores medidos vs presupuesto, dónde
                  se buscó el fact...), útil para depurar y para el REPORT.
    """

    name: str
    score: float
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


class LatencyBudgetMetric:
    """¿El turno respondió dentro del presupuesto de latencia?

    score = 1.0 si latency_ms <= budget_ms; 0.0 en caso contrario. Es la métrica que
    revela cuándo el CAG empieza a ir "lento" al crecer el contexto: en el REPORT se
    cruza con tokens_in para ver a partir de qué tamaño se rompe el presupuesto.
    """

    def __init__(self, budget_ms: float) -> None:
        self.budget_ms = float(budget_ms)
        self.name = "latency_budget"

    def evaluate(self, latency_ms: float) -> MetricResult:
        within = latency_ms <= self.budget_ms
        return MetricResult(
            name=self.name,
            score=1.0 if within else 0.0,
            passed=within,
            details={"latency_ms": latency_ms, "budget_ms": self.budget_ms},
        )


class CostBudgetMetric:
    """¿El turno costó menos que el presupuesto de coste?

    score = 1.0 si cost_usd <= budget_usd; 0.0 en caso contrario. Cruzada con el
    turn_index (coste acumulado), enseña cómo el coste por conversación escala con la
    longitud: el "impuesto" de reenviar el historial completo en cada turno.
    """

    def __init__(self, budget_usd: float) -> None:
        self.budget_usd = float(budget_usd)
        self.name = "cost_budget"

    def evaluate(self, cost_usd: float) -> MetricResult:
        within = cost_usd <= self.budget_usd
        return MetricResult(
            name=self.name,
            score=1.0 if within else 0.0,
            passed=within,
            details={"cost_usd": cost_usd, "budget_usd": self.budget_usd},
        )


# Campos por defecto donde buscar el hecho (contrato del enunciado original). En
# nuestra base, "summary" y "anchors" se tratan como vacíos (GAP); "metadata" es
# el ProjectMetadata acumulado. El runner además puede inyectar "history".
DEFAULT_WHERE: tuple[str, ...] = ("summary", "anchors", "metadata")


class MemoryDriftMetric:
    """¿La memoria de la sesión sigue conteniendo el hecho clave (sin "derivar")?

    "Drift" (deriva) = que un hecho que el cliente dio antes desaparezca o se
    contradiga en turnos posteriores. Esta métrica lo detecta de forma simple y
    determinista: busca el ``fact`` (case-insensitive) en los campos indicados por
    ``where`` del snapshot de la sesión.

      score = 1.0 si el fact APARECE en alguno de los campos disponibles; 0.0 si no.

    El ``snapshot`` es un dict flexible. Esta métrica busca el fact en:
      - snapshot["metadata"] (o "project_metadata"): el ProjectMetadata acumulado,
        aplanado a texto (nombre, tecnologías, alcance...). Es la pieza principal en
        nuestra base.
      - snapshot["summary"] y snapshot["anchors"]: si existen. En nuestra base no
        existen (GAP), así que normalmente vendrán vacíos y no aportan.
      - snapshot["history"]: si el runner lo añade (texto concatenado de los turnos),
        permite detectar el fact aunque el extractor de metadatos no lo haya captado.

    ``where`` controla qué campos se consultan. Por defecto, los tres del enunciado
    (summary/anchors/metadata); el runner puede ampliarlo con "history".
    """

    def __init__(self, fact: str, where: list[str] | tuple[str, ...] | None = None) -> None:
        self.fact = (fact or "").strip()
        self.where: tuple[str, ...] = tuple(where) if where is not None else DEFAULT_WHERE
        self.name = "memory_drift"

    def _field_text(self, snapshot: dict, field_name: str) -> str:
        """Extrae y aplana a texto el contenido de un campo del snapshot.

        Es DEFENSIVA con la forma del snapshot:
          - "metadata"/"project_metadata": acepta dict (lo serializa a texto) o str.
          - resto de campos: acepta str, list (los une) o dict (los aplana).
        Si el campo no existe o está vacío, devuelve "".
        """
        # "metadata" puede venir bajo dos claves según cómo lo arme el runner.
        if field_name == "metadata":
            value = snapshot.get("metadata", snapshot.get("project_metadata"))
        else:
            value = snapshot.get(field_name)

        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            # Aplanamos valores anidados (project_name, mentioned_technologies, ...).
            return " ".join(str(v) for v in _flatten_values(value))
        if isinstance(value, (list, tuple)):
            return " ".join(str(v) for v in value)
        return str(value)

    def evaluate(self, snapshot: dict) -> MetricResult:
        """Evalúa la deriva de memoria contra un snapshot de la sesión.

        Args:
            snapshot: estado de la sesión (típicamente lo que devuelve GET /sessions/{id},
                      posiblemente enriquecido por el runner con "history").

        Returns:
            MetricResult con score 1.0 si el fact aparece, 0.0 si no, y details con
            el haystack consultado y los campos usados.
        """
        # Un fact vacío no se puede rastrear: lo consideramos "no aplica" -> pasa.
        # (El runner solo construye esta métrica cuando hay un fact que rastrear.)
        if not self.fact:
            return MetricResult(
                name=self.name,
                score=1.0,
                passed=True,
                details={"fact": "", "reason": "no_fact_to_track"},
            )

        haystacks: list[str] = []
        for field_name in self.where:
            text = self._field_text(snapshot, field_name)
            if text:
                haystacks.append(text)

        haystack = " \n ".join(haystacks).lower()
        found = self.fact.lower() in haystack

        return MetricResult(
            name=self.name,
            score=1.0 if found else 0.0,
            passed=found,
            details={
                "fact": self.fact,
                "found": found,
                "where": list(self.where),
                "haystack_chars": len(haystack),
            },
        )


def _flatten_values(value: Any) -> list[Any]:
    """Aplana recursivamente los valores de un dict/list a una lista plana de escalares.

    Lo usa MemoryDriftMetric para convertir un ProjectMetadata serializado (dict con
    listas anidadas como mentioned_technologies) en texto buscable.
    """
    out: list[Any] = []
    if isinstance(value, dict):
        for v in value.values():
            out.extend(_flatten_values(v))
    elif isinstance(value, (list, tuple)):
        for v in value:
            out.extend(_flatten_values(v))
    elif value is not None:
        out.append(value)
    return out
