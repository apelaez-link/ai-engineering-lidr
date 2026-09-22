"""Tests del bucle agéntico (sesión 12) con un cliente OpenAI FALSO.

No tocamos la red ni la BBDD: inyectamos un cliente cuyo `responses.parse` devuelve una
secuencia de respuestas guionizadas. Así verificamos la MECÁNICA del bucle: recorrer
function_call → ejecutar la tool → devolver function_call_output con el call_id →
encadenar con previous_response_id → terminar en la salida estructurada. Y que la traza
y el coste se acumulan bien, y que un error de tool se convierte en observación.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.agent.loop import run_agent
from app.agent.schemas import AgentEstimate, AgentEstimateLine
from app.agent.tools import ToolContext


# ── Utilidades para fabricar respuestas falsas de la Responses API ──────────────


def _fc(name: str, arguments: dict, call_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="function_call", name=name, arguments=json.dumps(arguments), call_id=call_id
    )


def _message(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="message", content=[SimpleNamespace(type="output_text", text=text)]
    )


def _usage(inp: int, out: int, reasoning: int = 0, total: int | None = None):
    return SimpleNamespace(
        input_tokens=inp,
        output_tokens=out,
        total_tokens=total if total is not None else inp + out,
        output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
    )


class _FakeResponse:
    def __init__(self, id, output, output_parsed=None, usage=None):
        self.id = id
        self.output = output
        self.output_parsed = output_parsed
        self.usage = usage


class _FakeResponses:
    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self._scripted.pop(0)


class _FakeClient:
    def __init__(self, scripted):
        self.responses = _FakeResponses(scripted)


def _ctx() -> ToolContext:
    # session/embedder no se usan en los caminos testeados (calculate_estimate es puro;
    # en el test de search_budgets parcheamos hybrid_search y usamos un embedder falso).
    return ToolContext(session=None, embedder=None)  # type: ignore[arg-type]


# ── Tests ────────────────────────────────────────────────────────────────────────


def test_loop_executes_tool_then_returns_structured_final():
    final = AgentEstimate(
        line_items=[
            AgentEstimateLine(component="auth", hours=40, rationale="ev"),
            AgentEstimateLine(component="payments", hours=60, rationale="ev"),
        ],
        total_hours=100,
        summary="Two components.",
    )
    scripted = [
        _FakeResponse(
            id="resp_1",
            output=[
                _fc(
                    "calculate_estimate",
                    {"components": [
                        {"component": "auth", "hours": 40},
                        {"component": "payments", "hours": 60},
                    ]},
                    "call_1",
                )
            ],
            usage=_usage(100, 20, total=120),
        ),
        _FakeResponse(
            id="resp_2",
            output=[_message("Done.")],
            output_parsed=final,
            usage=_usage(150, 30, total=180),
        ),
    ]
    client = _FakeClient(scripted)

    result = asyncio.run(
        run_agent("transcript", _ctx(), client=client, model="gpt-4o", max_steps=8)
    )

    # Terminó solo con la salida estructurada.
    assert result.stopped_reason == "final_answer"
    assert result.estimate is not None
    assert result.estimate.total_hours == 100

    # Traza: 2 pasos; el primero con la tool y su observación determinista (40+60=100).
    assert len(result.trace) == 2
    assert result.trace[0].tool_calls[0].name == "calculate_estimate"
    assert result.trace[0].tool_calls[0].observation["total_hours"] == 100.0
    assert result.trace[1].tool_calls == []

    # Coste acumulado de las 2 vueltas.
    assert result.cost.steps == 2
    assert result.cost.input_tokens == 250
    assert result.cost.output_tokens == 50
    assert result.cost.total_tokens == 300

    # La 2ª llamada encadenó con previous_response_id y mandó el function_call_output.
    second_call = client.responses.calls[1]
    assert second_call["previous_response_id"] == "resp_1"
    sent = second_call["input"]
    assert sent[0]["type"] == "function_call_output"
    assert sent[0]["call_id"] == "call_1"
    assert json.loads(sent[0]["output"])["total_hours"] == 100.0


def test_loop_wraps_search_budgets_and_records_observation(monkeypatch):
    """search_budgets envuelve el retrieval S10: parcheamos hybrid_search (sin BBDD)."""
    async def fake_hybrid_search(session, **kwargs):
        return [
            {
                "chunk_id": 7,
                "document_id": 3,
                "content": "OAuth 2.0 auth module. Estimated hours: 45.",
                "rrf_score": 0.0312,
                "metadata": {"chunk_id": "BUD-1::AUTH", "budget_id": "BUD-1"},
            }
        ]

    monkeypatch.setattr("app.agent.tools.hybrid_search", fake_hybrid_search)

    final = AgentEstimate(
        line_items=[AgentEstimateLine(component="auth", hours=45, rationale="ev")],
        total_hours=45,
        summary="One component.",
    )
    scripted = [
        _FakeResponse(
            id="r1",
            output=[_fc("search_budgets", {"query": "OAuth 2.0 authentication"}, "c1")],
            usage=_usage(80, 10),
        ),
        _FakeResponse(id="r2", output=[_message("done")], output_parsed=final, usage=_usage(90, 10)),
    ]
    client = _FakeClient(scripted)
    ctx = ToolContext(
        session=None,  # type: ignore[arg-type]
        embedder=SimpleNamespace(embed_one=lambda text: [0.0] * 1536),  # type: ignore[arg-type]
    )

    result = asyncio.run(
        run_agent("t", ctx, client=client, model="gpt-4o", max_steps=8)
    )

    obs = result.trace[0].tool_calls[0].observation
    assert obs["n"] == 1
    assert obs["results"][0]["chunk_id"] == "BUD-1::AUTH"
    assert "Estimated hours: 45" in obs["results"][0]["content"]
    assert result.estimate.total_hours == 45


def test_loop_tool_error_becomes_observation(monkeypatch):
    """Si la tool peta (p.ej. BBDD caída), el error entra como observación, no rompe el bucle."""
    async def boom(session, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.agent.tools.hybrid_search", boom)

    final = AgentEstimate(line_items=[], total_hours=0, summary="no data")
    scripted = [
        _FakeResponse(
            id="r1",
            output=[_fc("search_budgets", {"query": "auth"}, "c1")],
            usage=_usage(10, 5),
        ),
        _FakeResponse(id="r2", output=[_message("done")], output_parsed=final, usage=_usage(10, 5)),
    ]
    client = _FakeClient(scripted)
    ctx = ToolContext(
        session=None,  # type: ignore[arg-type]
        embedder=SimpleNamespace(embed_one=lambda text: [0.0] * 1536),  # type: ignore[arg-type]
    )

    result = asyncio.run(run_agent("t", ctx, client=client, model="gpt-4o"))

    obs = result.trace[0].tool_calls[0].observation
    assert "error" in obs
    assert "db down" in obs["error"]
    assert result.stopped_reason == "final_answer"  # el bucle siguió y terminó
