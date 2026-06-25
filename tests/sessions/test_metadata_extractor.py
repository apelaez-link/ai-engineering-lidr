"""Tests del extractor LLM de metadatos del proyecto (sesión 05).

Mockeamos Instructor (instructor.from_litellm) para que devuelva un ProjectMetadata
controlado, sin llamadas reales. Comprobamos:
  - El resultado se MERGEA con la memoria previa (no se pierde lo anterior).
  - Si el extractor revienta, la función es DEFENSIVA y devuelve `current` intacto.
"""

from unittest.mock import MagicMock, patch

from app.sessions.metadata_extractor import extract_metadata
from app.sessions.models import ProjectMetadata


@patch("app.sessions.metadata_extractor.instructor.from_litellm")
def test_extract_metadata_merges_with_current(mock_from_litellm: MagicMock) -> None:
    """El extractor devuelve hechos nuevos y se mergean con la memoria previa."""
    # El extractor LLM "detecta" un nuevo team size y una tecnología extra.
    extracted = ProjectMetadata(
        assumed_team_size=6,
        mentioned_technologies=["AWS"],
        agreed_scope="Add reporting module",
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = extracted
    mock_from_litellm.return_value = mock_client

    current = ProjectMetadata(
        project_name="FleetX",
        assumed_team_size=4,
        mentioned_technologies=["React"],
        agreed_scope="MVP",
    )

    merged = extract_metadata(
        transcript="We grew the team to 6 and we'll deploy on AWS.",
        assistant_text="Updated estimate with reporting module.",
        current=current,
    )

    # Hecho previo conservado.
    assert merged.project_name == "FleetX"
    # Hecho nuevo prevalece.
    assert merged.assumed_team_size == 6
    # Unión de tecnologías.
    assert merged.mentioned_technologies == ["React", "AWS"]
    # Alcance más reciente.
    assert merged.agreed_scope == "Add reporting module"
    mock_client.chat.completions.create.assert_called_once()


@patch("app.sessions.metadata_extractor.instructor.from_litellm")
def test_extract_metadata_is_defensive_on_error(mock_from_litellm: MagicMock) -> None:
    """Si el extractor lanza una excepción, devolvemos la memoria previa sin cambios."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("LLM down")
    mock_from_litellm.return_value = mock_client

    current = ProjectMetadata(project_name="FleetX", assumed_team_size=4)
    result = extract_metadata("hi", "ho", current=current)

    # No se pierde nada: devolvemos exactamente `current`.
    assert result == current
