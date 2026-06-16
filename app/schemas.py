"""Schemas Pydantic v2 del estimador (sesión 04).

Centraliza los contratos de entrada y salida en un único módulo, de forma que
tanto el router como el servicio y los tests importen desde aquí. El router ya
no define sus propios modelos inline.

Los enums usan str como base para que FastAPI los serialice como cadenas en JSON
(más legible en Swagger y para los clientes).
"""

from enum import Enum

from pydantic import BaseModel, Field


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
