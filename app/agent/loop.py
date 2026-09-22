"""El bucle agéntico, construido A MANO sobre la Responses API (sesión 12).

Este es el ejercicio: no hay framework. El bucle es:

    1. Llamas al modelo con el system prompt + la transcripción + las tools.
    2. Recorres `response.output` buscando items `function_call`.
    3. Si los hay: ejecutas TÚ cada función con sus `arguments` y le devuelves un
       `function_call_output` con el MISMO `call_id`. Encadenas con
       `previous_response_id` y repites (razona → actúa → observa → repite).
    4. Si NO los hay: el modelo ha dado su respuesta final (structured output vía
       `text_format=AgentEstimate`). Sales del bucle.

Con una CONDICIÓN DE PARADA dura (`MAX_STEPS`), llamadas a tools en PARALELO
(`asyncio.gather`), tratamiento de errores COMO OBSERVACIÓN (try/except en el registro),
una TRAZA por paso y un contador de COSTE (`usage`). Es la implementación de referencia
de la lección 4.

El SDK de OpenAI (`client.responses.parse`) es síncrono/bloqueante; lo sacamos del event
loop con `asyncio.to_thread`, igual que hace el embedder.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from openai import OpenAI

from app.config import get_settings
from app.logging_config import get_logger

from .schemas import AgentEstimate, AgentRun, CostSummary, ToolCallTrace, TraceStep
from .tools import TOOL_REGISTRY, TOOL_SCHEMAS, ToolContext

logger = get_logger(component="agent")

SYSTEM_PROMPT = """You are a senior software estimator working as an autonomous agent.

You are given the transcript of a client meeting. Produce an hours estimate for the \
project by REUSING evidence from historical project budgets, never from general \
knowledge alone.

Work in a loop, deciding each step yourself:
1. Read the transcript and decompose the project into its distinct components \
(e.g. authentication, payments integration, data migration).
2. For EACH component, call `search_budgets` with a precise query — one component per \
call, never combine unrelated components in a single query.
3. From the returned evidence (which usually contains the historical hours), decide the \
hours for each component. If a component has no supporting evidence, still include it but \
say so in its rationale and estimate conservatively.
4. Once you have hours for every component, call `calculate_estimate` with all of them to \
get a total that is guaranteed consistent with the line items. Optionally call \
`validate_estimate` to double-check.
5. Then give your FINAL answer as the structured estimate: one line item per component \
(with hours and a short rationale referencing the evidence), the total, and a one- \
paragraph summary.

Be decisive: do not loop forever. As soon as you have searched every component and \
totalled the estimate, return the final structured answer."""


def build_openai_client() -> OpenAI:
    """Construye el cliente de OpenAI desde el .env (la Responses API es de OpenAI)."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError(
            "OPENAI_API_KEY no está configurada. El agente de la sesión 12 usa la "
            "Responses API de OpenAI directamente; rellena la clave en el .env."
        )
    return OpenAI(api_key=settings.openai_api_key)


def _is_reasoning_model(model: str) -> bool:
    """gpt-5* y la familia o* aceptan (y facturan) `reasoning`; gpt-4o* no."""
    m = model.lower()
    return m.startswith("gpt-5") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4")


def _text_of(response: Any) -> str:
    """Extrae el texto/razonamiento emitido por el modelo en una respuesta (para la traza)."""
    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        itype = getattr(item, "type", None)
        if itype == "message":
            for part in getattr(item, "content", []) or []:
                if getattr(part, "type", None) == "output_text":
                    parts.append(getattr(part, "text", "") or "")
        elif itype == "reasoning":
            for summary in getattr(item, "summary", []) or []:
                text = getattr(summary, "text", "") or ""
                if text:
                    parts.append(text)
    return "\n".join(p for p in parts if p).strip()


def _function_calls(response: Any) -> list[Any]:
    """Items function_call de la respuesta (lo que el modelo pide ejecutar)."""
    return [it for it in (getattr(response, "output", []) or []) if getattr(it, "type", None) == "function_call"]


async def _execute_call(call: Any, ctx: ToolContext) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ejecuta una function_call y devuelve (argumentos, observación).

    Errores COMO OBSERVACIÓN (lección 2): si la tool peta (p.ej. BBDD caída) o el modelo
    manda argumentos inválidos, no rompemos el bucle — devolvemos {"error": ...} para que
    el modelo lo lea y reaccione en la siguiente vuelta.
    """
    try:
        args = json.loads(call.arguments or "{}")
    except json.JSONDecodeError as exc:
        return {}, {"error": f"invalid JSON arguments: {exc}"}

    impl = TOOL_REGISTRY.get(call.name)
    if impl is None:
        return args, {"error": f"unknown tool '{call.name}'"}

    try:
        observation = await impl(args, ctx)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de tool es una observación
        logger.warning("agent_tool_failed", tool=call.name, error=str(exc))
        observation = {"error": f"{type(exc).__name__}: {exc}"}
    return args, observation


async def run_agent(
    transcript: str,
    ctx: ToolContext,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
    max_steps: int | None = None,
    reasoning_effort: str | None = None,
) -> AgentRun:
    """Ejecuta el agente sobre una transcripción y devuelve estimación + traza + coste.

    Args:
        transcript: transcripción de la reunión a estimar.
        ctx: dependencias de las tools (sesión de BBDD + embedder).
        client: cliente OpenAI (inyectable para tests; si None se construye del .env).
        model: modelo a usar (si None, settings.agent_model).
        max_steps: tope de vueltas del bucle (si None, settings.agent_max_steps).
        reasoning_effort: esfuerzo de razonamiento para modelos gpt-5/o* (si None, settings).
    """
    settings = get_settings()
    client = client or build_openai_client()
    model = model or settings.agent_model
    max_steps = max_steps or settings.agent_max_steps
    reasoning_effort = reasoning_effort or settings.agent_reasoning_effort

    common: dict[str, Any] = {
        "model": model,
        "instructions": SYSTEM_PROMPT,
        "tools": TOOL_SCHEMAS,
        "text_format": AgentEstimate,
    }
    if _is_reasoning_model(model):
        common["reasoning"] = {"effort": reasoning_effort}

    input_items: list[Any] = [{"role": "user", "content": transcript}]
    previous_response_id: str | None = None

    trace: list[TraceStep] = []
    in_tok = out_tok = reason_tok = tot_tok = 0
    estimate: AgentEstimate | None = None
    stopped_reason = "max_steps"

    logger.info("agent_run_started", model=model, max_steps=max_steps)

    for step in range(1, max_steps + 1):
        kwargs = dict(common, input=input_items)
        if previous_response_id is not None:
            kwargs["previous_response_id"] = previous_response_id

        response = await asyncio.to_thread(client.responses.parse, **kwargs)
        previous_response_id = response.id

        # Coste: acumula el usage de esta vuelta (lección 6). Los tokens de razonamiento
        # ya van DENTRO de output_tokens; los llevamos aparte solo para ver su fracción.
        usage = getattr(response, "usage", None)
        if usage is not None:
            in_tok += getattr(usage, "input_tokens", 0) or 0
            out_tok += getattr(usage, "output_tokens", 0) or 0
            tot_tok += getattr(usage, "total_tokens", 0) or 0
            details = getattr(usage, "output_tokens_details", None)
            reason_tok += getattr(details, "reasoning_tokens", 0) or 0

        reasoning_text = _text_of(response)
        calls = _function_calls(response)

        if not calls:
            # No pide más tools: es la respuesta final (structured output).
            estimate = getattr(response, "output_parsed", None)
            trace.append(TraceStep(step=step, reasoning=reasoning_text, tool_calls=[]))
            stopped_reason = "final_answer"
            logger.info("agent_run_final", step=step, has_estimate=estimate is not None)
            break

        # Paso de acción: ejecuta TODAS las tools pedidas EN PARALELO (asyncio.gather).
        results = await asyncio.gather(*(_execute_call(c, ctx) for c in calls))

        tool_traces: list[ToolCallTrace] = []
        next_input: list[Any] = []
        for call, (args, observation) in zip(calls, results):
            tool_traces.append(
                ToolCallTrace(name=call.name, arguments=args, observation=observation)
            )
            next_input.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(observation, ensure_ascii=False),
                }
            )

        trace.append(TraceStep(step=step, reasoning=reasoning_text, tool_calls=tool_traces))
        input_items = next_input  # con previous_response_id solo mandamos lo NUEVO

    # Si agotó MAX_STEPS sin respuesta final, forzamos un último cierre sin tools.
    if estimate is None and stopped_reason == "max_steps":
        logger.warning("agent_run_max_steps_forcing_final", steps=max_steps)
        kwargs = dict(common, input=input_items)
        kwargs.pop("tools", None)  # sin tools: obligamos a cerrar
        kwargs["instructions"] = SYSTEM_PROMPT + "\n\nProvide your FINAL estimate now."
        if previous_response_id is not None:
            kwargs["previous_response_id"] = previous_response_id
        response = await asyncio.to_thread(client.responses.parse, **kwargs)
        usage = getattr(response, "usage", None)
        if usage is not None:
            in_tok += getattr(usage, "input_tokens", 0) or 0
            out_tok += getattr(usage, "output_tokens", 0) or 0
            tot_tok += getattr(usage, "total_tokens", 0) or 0
            details = getattr(usage, "output_tokens_details", None)
            reason_tok += getattr(details, "reasoning_tokens", 0) or 0
        estimate = getattr(response, "output_parsed", None)
        trace.append(TraceStep(step=max_steps + 1, reasoning=_text_of(response), tool_calls=[]))
        stopped_reason = "max_steps_forced_final"

    cost = CostSummary(
        steps=len(trace),
        input_tokens=in_tok,
        output_tokens=out_tok,
        reasoning_tokens=reason_tok,
        total_tokens=tot_tok,
    )
    return AgentRun(
        estimate=estimate,
        trace=trace,
        cost=cost,
        stopped_reason=stopped_reason,
        model=model,
    )
