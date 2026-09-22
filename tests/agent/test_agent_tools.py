"""Tests de las tools deterministas del agente (sesión 12).

calculate_estimate y validate_estimate son PURAS (sin LLM, sin BBDD), así que se testean
directamente. También comprobamos que los schemas de las tools tienen el formato PLANO y
estricto de la Responses API.
"""

from __future__ import annotations

from app.agent.tools import (
    TOOL_REGISTRY,
    TOOL_SCHEMAS,
    calculate_estimate,
    validate_estimate,
)


def test_calculate_estimate_sums_hours_deterministically():
    result = calculate_estimate(
        [
            {"component": "auth", "hours": 40},
            {"component": "payments", "hours": 60.5},
        ]
    )
    assert result["total_hours"] == 100.5
    assert result["line_items"] == [
        {"component": "auth", "hours": 40.0},
        {"component": "payments", "hours": 60.5},
    ]


def test_calculate_estimate_empty_is_zero():
    assert calculate_estimate([])["total_hours"] == 0.0


def test_validate_estimate_ok_when_total_matches():
    report = validate_estimate(
        100.0, [{"component": "auth", "hours": 40}, {"component": "pay", "hours": 60}]
    )
    assert report["ok"] is True
    assert report["issues"] == []
    assert report["computed_total"] == 100.0


def test_validate_estimate_flags_total_mismatch_and_bad_lines():
    report = validate_estimate(
        999.0, [{"component": "auth", "hours": 0}, {"component": "pay", "hours": 60}]
    )
    assert report["ok"] is False
    # detecta el total incoherente y la línea con horas no positivas
    assert any("does not match" in i for i in report["issues"])
    assert any("non-positive" in i for i in report["issues"])


def test_validate_estimate_flags_empty():
    report = validate_estimate(0.0, [])
    assert report["ok"] is False
    assert any("no components" in i for i in report["issues"])


def test_tool_schemas_are_flat_and_strict():
    """Formato Responses API: type/name/parameters al MISMO nivel (no anidado en 'function')."""
    names = {t["name"] for t in TOOL_SCHEMAS}
    assert names == {"search_budgets", "calculate_estimate", "validate_estimate"}
    for tool in TOOL_SCHEMAS:
        assert tool["type"] == "function"
        assert "function" not in tool  # NO es el formato anidado de Chat Completions
        assert tool["strict"] is True
        params = tool["parameters"]
        assert params["type"] == "object"
        assert params["additionalProperties"] is False
        # strict exige que todas las propiedades declaradas sean required
        assert set(params["required"]) == set(params["properties"].keys())
    # cada tool del schema tiene su implementación registrada
    assert names <= set(TOOL_REGISTRY)
