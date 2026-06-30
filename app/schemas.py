"""Schemas Pydantic v2 del estimador (sesión 04).

Centraliza los contratos de entrada y salida en un único módulo, de forma que
tanto el router como el servicio y los tests importen desde aquí. El router ya
no define sus propios modelos inline.

Los enums usan str como base para que FastAPI los serialice como cadenas en JSON
(más legible en Swagger y para los clientes).
"""

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class ProjectType(str, Enum):
    """Tipo de proyecto que se quiere estimar."""

    MOBILE_APP = "mobile_app"
    WEB_SAAS = "web_saas"
    INTERNAL_TOOL = "internal_tool"
    DATA_PIPELINE = "data_pipeline"


class DetailLevel(str, Enum):
    """Nivel de detalle deseado en la estimación generada."""

    SUMMARY = "summary"
    MEDIUM = "medium"
    DETAILED = "detailed"


class OutputFormat(str, Enum):
    """Formato de presentación de la estimación."""

    PHASES_TABLE = "phases_table"
    LINE_ITEMS = "line_items"
    NARRATIVE = "narrative"


class ReferenceProject(BaseModel):
    """Proyecto de referencia para contextualizar la estimación (bonus: few-shot propio).

    Si el cliente aporta ejemplos de proyectos similares ya ejecutados, se inyectan
    en el prompt como contexto adicional para mejorar la precisión.
    """

    name: str
    summary: str
    total_cost_eur: int | None = None


class EstimationRequest(BaseModel):
    """Cuerpo de la petición POST /estimate.

    Contiene todo lo que el estimador necesita para generar la estimación:
    la descripción del proyecto, el tipo, el nivel de detalle y el formato
    de salida. Los proyectos de referencia son opcionales (bonus).
    """

    description: str = Field(
        min_length=20,
        max_length=2000,
        description="Descripción del proyecto a estimar (mínimo 20 caracteres).",
        examples=["A SaaS platform for real-time fleet tracking with mobile apps for drivers."],
    )
    project_type: ProjectType = Field(
        description="Categoría del proyecto: mobile_app, web_saas, internal_tool o data_pipeline."
    )
    detail_level: DetailLevel = Field(
        description="Nivel de detalle: summary (rápido), medium o detailed (con supuestos)."
    )
    output_format: OutputFormat = Field(
        description="Formato de salida: phases_table (tabla), line_items (lista) o narrative (prosa)."
    )
    reference_projects: list[ReferenceProject] | None = Field(
        default=None,
        description="Proyectos de referencia opcionales que se inyectan en el prompt como contexto.",
    )


# ── Salida estructurada (sesión 04, "Extracción de datos estructurados") ──────
# Hasta ahora el LLM devolvía texto libre (Markdown). Aquí pasamos a un contrato
# de datos TIPADO: el modelo debe rellenar un objeto JSON con esta forma exacta.
# Instructor (sobre litellm) se encarga de forzarlo y de reintentar si no valida.


class Phase(BaseModel):
    """Una fase del proyecto dentro de la estimación estructurada.

    Cada campo lleva sus propias restricciones (ge/le) para que el LLM no pueda
    devolver valores absurdos (semanas negativas, confianza > 100%, etc.). Si los
    devuelve, Pydantic lanza ValidationError e Instructor pide una corrección.
    """

    name: str = Field(description="Short phase name, e.g. 'Backend API'.")
    duration_weeks: int = Field(
        ge=1, le=52, description="Estimated duration of this phase in weeks (1-52)."
    )
    cost_eur: int = Field(ge=0, description="Estimated cost of this phase in EUR.")
    confidence_pct: int = Field(
        ge=0, le=100, description="Confidence in this phase estimate, 0-100."
    )
    assumptions: list[str] = Field(
        default_factory=list, description="Key assumptions behind this phase estimate."
    )


class EstimationResult(BaseModel):
    """Resultado estructurado completo de la estimación.

    Es el `response_model` que pasamos a Instructor: el LLM debe rellenar este
    objeto. Además del tipado por campo, añadimos un validador "after" con reglas
    de COHERENCIA INTERNA (lección "Extracción de datos estructurados"): de poco
    sirve que cada número sea válido por separado si los totales no cuadran con la
    suma de las fases. Esta es la primera línea de defensa antes de los guardrails.
    """

    summary: str = Field(description="One-paragraph executive summary of the estimate.")
    total_duration_weeks: int = Field(
        ge=1, le=520, description="Total project duration in weeks (sum of phases)."
    )
    total_cost_eur: int = Field(ge=0, description="Total project cost in EUR (sum of phases).")
    confidence_pct: int = Field(
        ge=0, le=100, description="Overall confidence in the estimate, 0-100."
    )
    phases: list[Phase] = Field(
        default_factory=list, description="Breakdown of the project into phases."
    )

    @model_validator(mode="after")
    def _check_totals_consistency(self) -> "EstimationResult":
        """Valida que los totales sean coherentes con la suma de las fases.

        Dos reglas (lección de extracción estructurada):
          - La suma de duration_weeks de las fases debe coincidir con
            total_duration_weeks con una tolerancia de ±1 semana (redondeos).
          - La suma de cost_eur de las fases debe coincidir con total_cost_eur
            con una tolerancia de ±5% (variaciones por blended rates, IVA, etc.).

        Si no hay fases no comprobamos nada (un summary sin desglose es válido,
        p. ej. en el caso "Out of scope"). Si fallan, lanzamos ValueError, que
        Pydantic envuelve en ValidationError; Instructor lo usará para reintentar.
        """
        if not self.phases:
            return self

        sum_weeks = sum(p.duration_weeks for p in self.phases)
        if abs(sum_weeks - self.total_duration_weeks) > 1:
            raise ValueError(
                f"Sum of phase durations ({sum_weeks} weeks) does not match "
                f"total_duration_weeks ({self.total_duration_weeks}); tolerance is +/-1 week."
            )

        sum_cost = sum(p.cost_eur for p in self.phases)
        # Tolerancia del 5% sobre el total declarado. Para totales 0, exigimos suma 0
        # (total_cost_eur tiene ge=0, así que el producto nunca es negativo).
        tolerance = self.total_cost_eur * 0.05
        if abs(sum_cost - self.total_cost_eur) > tolerance:
            raise ValueError(
                f"Sum of phase costs ({sum_cost} EUR) does not match "
                f"total_cost_eur ({self.total_cost_eur}); tolerance is +/-5%."
            )

        return self

    @model_validator(mode="after")
    def _low_confidence_must_be_explicit(self) -> "EstimationResult":
        """Regla de negocio: una confianza muy baja debe declararse honestamente.

        Si el modelo tiene poca confianza (confidence_pct < 30) pero NO marca el
        resultado como fuera de alcance (summary que empiece por "Out of scope"),
        rechazamos. Como este validador vive en el `response_model` que recibe
        Instructor, el ValueError lo usa Instructor para REINTENTAR la generación
        mostrándole el error al LLM: es la política **FIX / RETRY** de la lección de
        guardrails (el modelo corrige bajando la confianza y marcando "Out of scope",
        o reconsidera la estimación). NO es post-hoc: el reintento ocurre aquí.
        """
        if self.confidence_pct < 30 and not self.summary.strip().lower().startswith(
            "out of scope"
        ):
            raise ValueError(
                "confidence_pct < 30 requires an explicit out-of-scope summary "
                "(start it with 'Out of scope:'). Otherwise raise the confidence "
                "or reconsider the estimate."
            )
        return self


class EstimationResponseStructured(BaseModel):
    """Respuesta del endpoint POST /estimate/structured.

    Envuelve el resultado tipado (EstimationResult) junto con la versión del
    prompt usada y un flag `cached` que indica si vino del cacheo semántico.
    """

    result: EstimationResult = Field(description="Estimación estructurada y validada.")
    prompt_version: str = Field(description="Versión del template de prompt usado (v1, v2...).")
    cached: bool = Field(default=False, description="True si la respuesta vino del cacheo semántico.")

    # ── Observabilidad por turno (sesión 06, "Stress test del CAG") ──────────
    # El endpoint conversacional adjunta aquí el dict del evento `turn_observed`
    # (latencia, tokens, coste, tamaño del contexto enriquecido, procedencia de
    # caché...). Es OPCIONAL para no romper el contrato previo: las respuestas del
    # flujo transaccional clásico siguen siendo válidas sin este campo. El runner
    # del stress test lo lee directamente de la respuesta (ver app/services/observation.py).
    observation: dict | None = Field(
        default=None,
        description="Medición estructurada del turno (turn_observed): latencia, tokens, coste, etc.",
    )


class EstimationResponse(BaseModel):
    """Respuesta del endpoint POST /estimate.

    Devuelve el texto de la estimación junto con metadatos de observabilidad
    (modelo, coste, latencia, cache_hit...) que la UI puede mostrar en el sidebar.
    Los metadatos son opcionales para no romper el contrato mínimo del ejercicio.
    """

    text: str = Field(..., description="Estimación generada por el LLM (Markdown o tabla).")
    prompt_version: str = Field(..., description="Versión del template de prompt utilizado (v1, v2...).")

    # Metadatos de observabilidad (sesión 03 heredados): no son obligatorios para el
    # contrato del ejercicio pero permiten al frontend mostrar trazabilidad.
    model: str | None = Field(default=None, description="Modelo concreto usado, p. ej. gpt-4o-mini.")
    cache_hit: bool = Field(default=False, description="True si la respuesta vino de caché.")
    fallback_used: bool = Field(
        default=False, description="True si respondió un proveedor de fallback."
    )
    tokens_in: int = Field(default=0, description="Tokens de entrada (prompt).")
    tokens_out: int = Field(default=0, description="Tokens de salida (respuesta).")
    cost_usd: float = Field(default=0.0, description="Coste estimado de la llamada en USD.")
    latency_ms: float = Field(default=0.0, description="Latencia de la llamada en milisegundos.")
