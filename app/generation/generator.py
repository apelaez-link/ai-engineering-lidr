"""Generador de estimaciones con citación por línea (sesión 11).

Toma la consulta (descripción del proyecto) y los chunks recuperados, y genera un objeto
`Estimate` donde CADA línea cita el/los chunk(s) que la respaldan, copiando la evidencia
verbatim. Usa Instructor sobre litellm con `response_model=Estimate` (mismo patrón que la
salida estructurada de la sesión 04): Instructor fuerza el JSON, lo valida contra los
@model_validator del schema (regla de integridad grounded/sources) y reintenta si falla.

El enunciado describe su implementación de referencia con la Responses API de OpenAI
(client.responses.parse); aquí usamos Instructor para mantener la abstracción de
proveedores del repo (litellm). El contrato de salida (JSON estricto tipado) es el mismo.
"""

from __future__ import annotations

from typing import Any

import instructor
import litellm

from app.config import get_settings
from app.logging_config import get_logger
from app.services.structured import _resolve_primary_model

from .schemas import Estimate

logger = get_logger(component="rag_generator")

litellm.telemetry = False
litellm.drop_params = True

# Prompt de sistema. Reglas duras de atribución: citar solo ids del contexto, copiar
# evidencia verbatim, y marcar grounded=False (sin inventar horas) cuando no hay soporte.
GENERATION_SYSTEM = """You are a senior software estimator. You estimate a NEW software \
project by reusing evidence from HISTORICAL project budgets that has been retrieved for \
you. You never estimate from general knowledge alone.

You are given a CONTEXT: a list of retrieved chunks, each labelled with its chunk_id and \
document_id. Break the estimate into line items, one per component/workstream of the new \
project, and follow these rules strictly:

1. For every line item that you can support with the CONTEXT, set grounded=true, provide \
the hours, and cite in `sources` the chunk_id(s) from the CONTEXT that back it. Copy into \
`evidence` the VERBATIM figure or span from that chunk (e.g. the hours or the sentence) — \
do not paraphrase.
2. Only ever cite chunk_id values that appear literally in the CONTEXT. Never invent or \
guess a chunk_id.
3. If NO chunk in the CONTEXT supports a component, set grounded=false, hours=0, \
sources=[] and state 'insufficient historical data' in the rationale. Do NOT estimate \
its hours from general knowledge.
4. total_hours must equal the sum of the line item hours.

Return only the structured object."""


def _format_context(chunks: list[dict[str, Any]]) -> str:
    """Formatea los chunks recuperados con su id trazable, para que el LLM los cite.

    Usa el chunk_id trazable de la metadata ("{budget_id}::{component_id}") y el budget_id
    como document_id: son legibles y es lo que verify_citations comparará después.
    """
    blocks: list[str] = []
    for row in chunks:
        md = row.get("metadata") or {}
        chunk_id = md.get("chunk_id") or str(row.get("chunk_id"))
        document_id = md.get("budget_id") or str(row.get("document_id"))
        content = " ".join((row.get("content") or "").split())
        blocks.append(f"[chunk_id={chunk_id} | document_id={document_id}]\n{content}")
    return "\n\n".join(blocks)


def retrieved_chunk_ids(chunks: list[dict[str, Any]]) -> set[str]:
    """Conjunto de chunk_id (trazables) pasados al generador — la 'verdad' de verify."""
    ids: set[str] = set()
    for row in chunks:
        md = row.get("metadata") or {}
        ids.add(md.get("chunk_id") or str(row.get("chunk_id")))
    return ids


def generate_estimate(query: str, chunks: list[dict[str, Any]]) -> Estimate:
    """Genera la estimación estructurada y citada a partir de la consulta + contexto."""
    settings = get_settings()
    model, api_key = _resolve_primary_model()
    client = instructor.from_litellm(litellm.completion)

    user = (
        f"PROJECT TO ESTIMATE:\n{query}\n\n"
        f"CONTEXT (retrieved historical budget chunks):\n{_format_context(chunks)}"
    )

    logger.info("rag_generation_started", model=model, context_chunks=len(chunks))
    estimate: Estimate = client.chat.completions.create(
        model=model,
        api_key=api_key,
        temperature=0.2,  # estimación: queremos consistencia, no creatividad
        max_tokens=settings.llm_max_tokens,
        response_model=Estimate,
        max_retries=3,
        messages=[
            {"role": "system", "content": GENERATION_SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    logger.info(
        "rag_generation_completed",
        model=model,
        line_items=len(estimate.line_items),
        grounded_lines=sum(1 for li in estimate.line_items if li.grounded),
        total_hours=estimate.total_hours,
    )
    return estimate
