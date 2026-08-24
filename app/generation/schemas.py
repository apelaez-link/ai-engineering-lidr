"""Schemas de la generación con citación verificable por línea (sesión 11).

Todo en inglés (nombres, descripciones): es el contrato que se le impone al LLM y que
consume, en la implementación de referencia, un backend de negocio. La prosa explicativa
(estos docstrings) va en español, como el resto del repo didáctico.

El salto respecto a la salida estructurada de la sesión 04 (EstimationResult, citación
GRUESA a nivel de estimación global): aquí cada LÍNEA de la estimación transporta sus
propias fuentes, y esas fuentes son verificables contra el contexto que se le pasó al
modelo (ver app/generation/verify.py). Una cita a un chunk que no estaba en el contexto
NO es una cita: es una alucinación con apariencia de rigor.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class SourceReference(BaseModel):
    """A single piece of retrieved evidence backing one estimate line."""

    chunk_id: str = Field(description="Id of the retrieved chunk supporting this line.")
    document_id: str = Field(
        description="Historical budget document the chunk belongs to."
    )
    evidence: str = Field(
        description="Verbatim span or figure copied from the source (not paraphrased)."
    )


class EstimateLineItem(BaseModel):
    """One component of the estimate (e.g. 'authentication', 'payments module')."""

    component: str = Field(description="Short name of the component being estimated.")
    hours: float = Field(ge=0, description="Estimated effort in hours (0 if not grounded).")
    rationale: str = Field(description="Short justification for this line.")
    grounded: bool = Field(
        description="True iff the estimate is backed by at least one retrieved source."
    )
    sources: list[SourceReference] = Field(
        default_factory=list,
        description="Supporting sources; non-empty iff grounded is True.",
    )

    @model_validator(mode="after")
    def _check_grounding(self) -> "EstimateLineItem":
        """Regla de integridad del enunciado (validada aquí; Instructor reintenta si falla):

        - grounded=True  -> debe citar AL MENOS una fuente.
        - grounded=False -> NO puede inventar horas (hours debe ser 0) ni traer fuentes;
          es una línea explícitamente marcada como "sin datos suficientes".
        """
        if self.grounded:
            if not self.sources:
                raise ValueError("a grounded line item must cite at least one source")
        else:
            if self.sources:
                raise ValueError("an ungrounded line item must not carry sources")
            if self.hours != 0:
                raise ValueError(
                    "an ungrounded line item must not invent hours (set hours to 0 "
                    "and mark it as insufficient data)"
                )
        return self


class Estimate(BaseModel):
    """A structured software estimate whose every line is source-attributed."""

    line_items: list[EstimateLineItem] = Field(
        description="The estimate broken down by component, one line each."
    )
    total_hours: float = Field(ge=0, description="Sum of the grounded line hours.")
    summary: str = Field(description="One-paragraph executive summary of the estimate.")

    @model_validator(mode="after")
    def _check_total(self) -> "Estimate":
        """total_hours debe cuadrar con la suma de las líneas (tolerancia por redondeos)."""
        line_sum = sum(li.hours for li in self.line_items)
        if abs(line_sum - self.total_hours) > 0.5:
            raise ValueError(
                f"total_hours ({self.total_hours}) must equal the sum of line item "
                f"hours ({line_sum})"
            )
        return self

    def as_text(self) -> str:
        """Render legible de la estimación (para el `answer` de RAGAS y para logs)."""
        lines = [self.summary, ""]
        for li in self.line_items:
            mark = f"{li.hours:g}h" if li.grounded else "insufficient data"
            lines.append(f"- {li.component}: {mark} — {li.rationale}")
        lines.append("")
        lines.append(f"Total: {self.total_hours:g}h")
        return "\n".join(lines)


# ── Verificación de citaciones (post-generación) ─────────────────────────────────


class CitationStatus(str, Enum):
    """Resultado de verificar las citas de una línea contra el contexto recuperado."""

    GROUNDED = "grounded"  # cita solo chunks presentes en el contexto
    DANGLING = "dangling"  # cita ≥1 chunk_id que NO estaba en el contexto (alucinación)
    INSUFFICIENT = "insufficient"  # línea marcada grounded=False (sin datos suficientes)


class LineCitationResult(BaseModel):
    """Veredicto de citación de una línea concreta."""

    component: str
    status: CitationStatus
    cited_chunk_ids: list[str] = Field(default_factory=list)
    dangling_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Cited ids that were NOT in the retrieved context.",
    )


class CitationReport(BaseModel):
    """Informe agregado de la verificación de citaciones de una estimación."""

    total_lines: int
    grounded: int
    dangling: int
    insufficient: int
    results: list[LineCitationResult] = Field(default_factory=list)

    @property
    def has_dangling(self) -> bool:
        """True si alguna línea cita una fuente colgante (fallo de calidad)."""
        return self.dangling > 0
