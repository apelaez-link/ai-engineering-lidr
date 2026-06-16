"""Tests del template Jinja2 v1 del estimador.

Verifican directamente la función render_estimation_prompt sin llamar a ningún
LLM ni API real: son rápidos, deterministas y funcionan en CI sin API key.

Cada test ejercita una capacidad diferente del sistema de templates:
  1. Que el prompt de usuario envuelve la descripción en XML tags correctas.
  2. Que el bloque condicional de output_format genera el contenido adecuado
     (p. ej. "confidence_pct" solo aparece con phases_table, no con narrative).
  3. Que el bloque condicional de detail_level añade la instrucción de supuestos
     solo cuando el nivel es "detailed", no cuando es "summary".
  4. (bonus) Que los proyectos de referencia se inyectan en el system prompt.
"""

import pytest

from app.prompts.loader import render_estimation_prompt
from app.schemas import (
    DetailLevel,
    EstimationRequest,
    OutputFormat,
    ProjectType,
    ReferenceProject,
)


def _make_request(**kwargs) -> EstimationRequest:
    """Factory de EstimationRequest con valores por defecto razonables."""
    defaults = {
        "description": "A platform for managing real estate listings with search and bookings.",
        "project_type": ProjectType.WEB_SAAS,
        "detail_level": DetailLevel.MEDIUM,
        "output_format": OutputFormat.PHASES_TABLE,
        "reference_projects": None,
    }
    defaults.update(kwargs)
    return EstimationRequest(**defaults)


# ── Test 1: el user prompt contiene el XML tag con la descripción literal ────

def test_user_prompt_contains_xml_tag_with_description() -> None:
    """El prompt de usuario debe envolver la descripción en <project_description>."""
    description = "A platform for managing real estate listings with search and bookings."
    request = _make_request(description=description)
    _, user = render_estimation_prompt(request, version="v1")

    assert "<project_description>" in user
    assert description in user
    assert "</project_description>" in user


# ── Test 2: output_format condiciona el contenido del system prompt ──────────

def test_system_prompt_phases_table_contains_table_instruction() -> None:
    """Con output_format=phases_table el system debe incluir la instrucción de tabla Markdown."""
    request = _make_request(output_format=OutputFormat.PHASES_TABLE)
    system, _ = render_estimation_prompt(request, version="v1")

    # La instrucción explícita de la tabla solo aparece en el bloque phases_table.
    assert "Markdown table" in system
    assert "confidence_pct" in system


def test_system_prompt_narrative_contains_paragraph_instruction() -> None:
    """Con output_format=narrative el system debe incluir la instrucción de prosa en párrafos."""
    request = _make_request(output_format=OutputFormat.NARRATIVE)
    system, _ = render_estimation_prompt(request, version="v1")

    # La instrucción de "3 paragraphs" solo aparece en el bloque narrative.
    assert "3 paragraphs" in system or "three" in system.lower()
    # Y la instrucción de tabla markdown NO debe estar.
    assert "Markdown table" not in system


# ── Test 3: detail_level condiciona la instrucción de supuestos por fase ─────

def test_system_prompt_detailed_includes_assumptions_instruction() -> None:
    """Con detail_level=detailed el system debe pedir asupciones por fase."""
    request = _make_request(detail_level=DetailLevel.DETAILED)
    system, _ = render_estimation_prompt(request, version="v1")

    assert "assumptions" in system.lower()


def test_system_prompt_summary_does_not_include_assumptions_instruction() -> None:
    """Con detail_level=summary el system NO debe incluir la instrucción de supuestos."""
    request = _make_request(detail_level=DetailLevel.SUMMARY)
    system, _ = render_estimation_prompt(request, version="v1")

    # El bloque {% if detail_level == "detailed" %} no debe activarse.
    # Comprobamos que la instrucción específica del bloque no aparece.
    assert "assumptions per phase" not in system.lower()


# ── Test bonus: proyectos de referencia inyectados en el system prompt ───────

def test_reference_projects_are_injected_in_system_prompt() -> None:
    """Con reference_projects, el nombre y resumen deben aparecer en el system."""
    refs = [
        ReferenceProject(
            name="Legacy ERP Migration",
            summary="Migration of Oracle ERP to SAP for 500 users.",
            total_cost_eur=120000,
        )
    ]
    request = _make_request(reference_projects=refs)
    system, _ = render_estimation_prompt(request, version="v1")

    assert "Legacy ERP Migration" in system
    assert "Migration of Oracle ERP" in system
    assert "120000" in system


def test_no_reference_projects_no_section_in_system_prompt() -> None:
    """Sin reference_projects el bloque de referencia no debe aparecer en el system."""
    request = _make_request(reference_projects=None)
    system, _ = render_estimation_prompt(request, version="v1")

    assert "Reference projects" not in system
