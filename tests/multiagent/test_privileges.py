"""Tests de privilegio mínimo + auditoría (sesión 14, Niveles 1 y 3)."""

from __future__ import annotations

import pytest

from app.multiagent.privileges import (
    AGENT_PRIVILEGES,
    PrivilegeError,
    audit_entry,
    enforce_privilege,
    is_allowed,
)


def test_privilege_map_least_privilege():
    # supervisor y extractor de requisitos: SIN tools de negocio.
    assert AGENT_PRIVILEGES["supervisor"] == frozenset()
    assert AGENT_PRIVILEGES["requirements_extractor"] == frozenset()
    # cada worker de negocio: exactamente UNA tool.
    assert AGENT_PRIVILEGES["budget_searcher"] == frozenset({"search_budgets"})
    assert AGENT_PRIVILEGES["estimate_generator"] == frozenset({"calculate_estimate"})
    assert AGENT_PRIVILEGES["coherence_validator"] == frozenset({"validate_estimate"})


def test_enforce_allows_own_tool():
    # no lanza
    enforce_privilege("budget_searcher", "search_budgets")
    enforce_privilege("coherence_validator", "validate_estimate")


def test_enforce_blocks_foreign_tool():
    # el buscador NO puede calcular; el validador NO puede buscar
    with pytest.raises(PrivilegeError):
        enforce_privilege("budget_searcher", "calculate_estimate")
    with pytest.raises(PrivilegeError):
        enforce_privilege("coherence_validator", "search_budgets")
    with pytest.raises(PrivilegeError):
        enforce_privilege("supervisor", "search_budgets")


def test_audit_entry_records_allowed_flag():
    ok = audit_entry("budget_searcher", "search_budgets", n=3)
    assert ok == {"agent": "budget_searcher", "tool": "search_budgets", "allowed": True, "n": 3}
    bad = audit_entry("budget_searcher", "calculate_estimate")
    assert bad["allowed"] is False
    assert is_allowed("budget_searcher", "search_budgets") is True
