"""Tools del agente (sesión 12): schemas planos + implementaciones.

Dos mitades, como enseña la lección 3:
  - El SCHEMA de cada tool (nombre, descripción, parámetros). Es lo único que ve el
    modelo: no lee tu código, lee esto. Por eso la descripción es un PROMPT que se
    itera (lección 5): la restricción "un componente por búsqueda" vive en el texto.
  - La IMPLEMENTACIÓN en Python. El modelo NO ejecuta tu código: PIDE una llamada
    (function_call) y la ejecutas TÚ, devolviéndole el resultado (function_call_output).

Formato de la Responses API: schema PLANO (`type`/`name`/`parameters` al mismo nivel),
no anidado bajo `function` como en Chat Completions. `strict: true` fuerza que el modelo
rellene exactamente los parámetros declarados.

Las tools envuelven piezas que YA existen:
  - `search_budgets`     → el retrieval híbrido (RRF) de la sesión 10. No se reimplementa.
  - `calculate_estimate` → función DETERMINISTA de Python (no llama al LLM): suma horas.
  - `validate_estimate`  → chequeo determinista de coherencia (tool opcional del enunciado).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.hybrid import hybrid_search
from app.embedding_pipeline.models_db import FULLTEXT_CONFIG


@dataclass
class ToolContext:
    """Dependencias que necesitan las tools con efectos (search_budgets toca BBDD).

    Se construye una vez por ejecución del agente (en el endpoint) y se pasa a cada
    tool. Las tools deterministas (calculate/validate) lo ignoran.
    """

    session: AsyncSession
    embedder: OpenAIEmbedder
    k: int = 5
    candidate_pool: int = 50
    rrf_k: int = 60
    fulltext_config: str = FULLTEXT_CONFIG


# ── Schemas de las tools (formato PLANO de la Responses API) ─────────────────────

_COMPONENT_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "component": {"type": "string", "description": "Short component name."},
        "hours": {"type": "number", "description": "Estimated hours for the component."},
    },
    "required": ["component", "hours"],
    "additionalProperties": False,
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "search_budgets",
        "description": (
            "Search historical project budgets for evidence to estimate ONE component "
            "at a time. Returns up to k references, each with chunk_id, document_id, a "
            "content snippet (often including the historical hours) and a relevance "
            "score. Call it ONCE PER COMPONENT; never combine unrelated components like "
            "an authentication module and a payments integration in a single query, "
            "because mixed results cannot be compared. Use a precise natural-language "
            "query describing the single component."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Natural-language description of ONE component to find "
                        "historical evidence for (e.g. 'OAuth 2.0 authentication with "
                        "JWT sessions and refresh tokens')."
                    ),
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "calculate_estimate",
        "description": (
            "Deterministically total the estimate. Pass EVERY component together with "
            "the hours you decided from the retrieved evidence; the tool echoes them "
            "back and returns their exact sum. Only call this AFTER you have searched "
            "budgets for every component and decided its hours, and BEFORE giving your "
            "final answer. This tool does no reasoning: it only adds up the numbers you "
            "provide, so the total is always consistent with the line items."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "components": {
                    "type": "array",
                    "description": "All estimated components with their hours.",
                    "items": _COMPONENT_ITEM_SCHEMA,
                }
            },
            "required": ["components"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "validate_estimate",
        "description": (
            "Optional sanity check on a finished estimate before returning it. Verifies "
            "that total_hours equals the sum of the components and flags empty or "
            "non-positive lines. Returns {ok, issues, computed_total}. Use it if you "
            "want to double-check coherence before your final answer."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "total_hours": {"type": "number"},
                "components": {"type": "array", "items": _COMPONENT_ITEM_SCHEMA},
            },
            "required": ["total_hours", "components"],
            "additionalProperties": False,
        },
    },
]


# ── Implementaciones ─────────────────────────────────────────────────────────────


def _trim(text: str | None, limit: int = 400) -> str:
    """Recorta el contenido del chunk para no inflar el contexto (lección 6).

    Que search_budgets devuelva referencias limpias y cortas, no 200 filas: el contexto
    del agente crece en cada vuelta y ese crecimiento es el factor DOMINANTE del coste.
    """
    normalized = " ".join((text or "").split())
    return normalized if len(normalized) <= limit else normalized[:limit] + "…"


async def _tool_search_budgets(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Envuelve el retrieval híbrido de S10 y devuelve referencias limpias."""
    query = args["query"]
    # embed_one es síncrono (HTTP bloqueante); lo sacamos del event loop.
    vector = await asyncio.to_thread(ctx.embedder.embed_one, query)
    rows = await hybrid_search(
        ctx.session,
        query_vector=vector,
        query_text=query,
        k=ctx.k,
        candidate_pool=ctx.candidate_pool,
        rrf_k=ctx.rrf_k,
        fulltext_config=ctx.fulltext_config,
    )
    results = []
    for row in rows:
        md = row.get("metadata") or {}
        results.append(
            {
                "chunk_id": md.get("chunk_id") or str(row.get("chunk_id")),
                "document_id": md.get("budget_id") or str(row.get("document_id")),
                "content": _trim(row.get("content")),
                "score": round(float(row.get("rrf_score", 0.0)), 5),
            }
        )
    return {"query": query, "results": results, "n": len(results)}


def _sum_components(components: list[dict[str, Any]]) -> float:
    return round(sum(float(c["hours"]) for c in components), 2)


def calculate_estimate(components: list[dict[str, Any]]) -> dict[str, Any]:
    """Suma DETERMINISTA de horas por componente (sin LLM, sin BBDD).

    Es pura: mismas entradas → misma salida. El agente decide las horas (a partir de la
    evidencia); esta tool solo garantiza que el total cuadre siempre con las líneas.
    Se expone como función normal (no async) para poder testearla directamente.
    """
    line_items = [
        {"component": str(c["component"]), "hours": float(c["hours"])}
        for c in components
    ]
    return {"line_items": line_items, "total_hours": _sum_components(line_items)}


def validate_estimate(total_hours: float, components: list[dict[str, Any]]) -> dict[str, Any]:
    """Chequeo DETERMINISTA de coherencia de una estimación (tool opcional del enunciado)."""
    computed = _sum_components(components) if components else 0.0
    issues: list[str] = []
    if not components:
        issues.append("no components provided.")
    if abs(computed - float(total_hours)) > 0.5:
        issues.append(
            f"total_hours ({total_hours}) does not match the sum of components ({computed})."
        )
    for c in components:
        if float(c["hours"]) <= 0:
            issues.append(f"component '{c['component']}' has non-positive hours.")
    return {"ok": not issues, "issues": issues, "computed_total": computed}


async def _tool_calculate_estimate(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    return calculate_estimate(args["components"])


async def _tool_validate_estimate(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    return validate_estimate(args["total_hours"], args["components"])


# Registro nombre → implementación async(args, ctx). El bucle lo consulta para ejecutar
# cada function_call. Las tools deterministas se envuelven en async por uniformidad.
ToolImpl = Callable[[dict[str, Any], ToolContext], Awaitable[dict[str, Any]]]

TOOL_REGISTRY: dict[str, ToolImpl] = {
    "search_budgets": _tool_search_budgets,
    "calculate_estimate": _tool_calculate_estimate,
    "validate_estimate": _tool_validate_estimate,
}
