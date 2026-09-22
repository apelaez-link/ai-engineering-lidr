"""Schemas de la capa de agentes (sesión 12).

Dos familias:

1. La SALIDA ESTRUCTURADA final del agente (`AgentEstimate`). El camino del agente es
   no-determinista (cuántas vueltas da, qué tools llama y en qué orden lo decide el
   modelo), pero la SALIDA sí es determinista en forma: le pasamos este schema como
   `text_format` a la Responses API y el modelo está obligado a rellenarlo. Así el
   backend de negocio recibe siempre el mismo contrato, dé el agente 2 vueltas o 6.

2. La TRAZA (`TraceStep`, `AgentRun`). El ejercicio pide que el agente devuelva, además
   de la estimación, una traza que muestre por paso su razonamiento, la acción y la
   observación. La traza es la herramienta nº1 para depurar y optimizar un agente
   (lección 5): leerla es cómo descubres que una descripción de tool está mal.

Todo el contrato hacia el modelo (AgentEstimate) va en inglés; la prosa explicativa en
español, como el resto del repo didáctico.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ── Salida estructurada final (text_format de la Responses API) ──────────────────


class AgentEstimateLine(BaseModel):
    """One estimated component of the project."""

    component: str = Field(description="Short name of the component being estimated.")
    hours: float = Field(ge=0, description="Estimated effort in hours for this component.")
    rationale: str = Field(
        description="Short justification, referencing the historical evidence used."
    )


class AgentEstimate(BaseModel):
    """The agent's final structured estimate for the whole project."""

    line_items: list[AgentEstimateLine] = Field(
        description="The estimate broken down by component, one line each."
    )
    total_hours: float = Field(ge=0, description="Sum of the line item hours.")
    summary: str = Field(description="One-paragraph executive summary of the estimate.")


# ── Traza del bucle agéntico ─────────────────────────────────────────────────────


class ToolCallTrace(BaseModel):
    """Una llamada a tool dentro de un paso: qué pidió el modelo y qué observó."""

    name: str = Field(description="Nombre de la tool invocada.")
    arguments: dict = Field(description="Argumentos que el modelo pasó a la tool.")
    observation: dict = Field(
        description="Resultado devuelto por la tool (la 'observación' del bucle)."
    )


class TraceStep(BaseModel):
    """Un paso del bucle: el razonamiento del modelo + las acciones + sus observaciones.

    `reasoning` recoge el texto que el modelo emitió en ese paso (si lo hubo). En un paso
    de acción, `tool_calls` lleva 1+ llamadas (pueden ir en paralelo). En el paso final,
    `tool_calls` va vacío y `reasoning` puede llevar el mensaje de cierre.
    """

    step: int = Field(description="Índice del paso (1-based).")
    reasoning: str = Field(default="", description="Texto/razonamiento del modelo en el paso.")
    tool_calls: list[ToolCallTrace] = Field(
        default_factory=list, description="Acciones ejecutadas en el paso y su observación."
    )


class CostSummary(BaseModel):
    """Resumen de coste en tokens acumulado (lección 6: el coste es medible al token)."""

    steps: int = Field(description="Número de llamadas al modelo (vueltas del bucle).")
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = Field(
        default=0, description="Tokens de razonamiento (van INCLUIDOS en output_tokens)."
    )
    total_tokens: int = 0


class AgentRun(BaseModel):
    """Resultado completo de una ejecución del agente: estimación + traza + coste.

    `estimate` es None si el agente agotó MAX_STEPS sin producir una estimación final
    (se refleja también en `stopped_reason`).
    """

    estimate: AgentEstimate | None = None
    trace: list[TraceStep] = Field(default_factory=list)
    cost: CostSummary
    stopped_reason: str = Field(
        description="Por qué paró el bucle: 'final_answer' o 'max_steps'."
    )
    model: str = Field(description="Modelo usado en la ejecución.")
