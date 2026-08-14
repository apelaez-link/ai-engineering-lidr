"""Tests del runner del stress test en modo MOCK (sesión 06, BLOQUE 5/6).

Verifican que el runner produce un CSV bien formado SIN llamar a ninguna API real:
  - El modo mock parchea las costuras de litellm (generación + extractor + moderación).
  - El CSV resultante tiene todas las columnas esperadas (turn_observed + métricas).
  - Hay al menos una fila, y el contenido es coherente (turn_index monótono, las
    columnas de métricas tienen valores en {0.0, 1.0}).

No se levanta servidor (transporte in-process con TestClient) ni se tocan claves.
"""

import csv

from evals.stress.run import ROW_FIELDS, RunConfig, mock_litellm_seams, run


def _mock_config(tmp_path) -> RunConfig:
    """Config mínima del runner en modo mock para un test rápido (1 escenario, 2 tamaños)."""
    return RunConfig(
        http_url=None,
        scenarios=["growing"],
        attachment_sizes=[0, 5],
        repeats=1,
        output=tmp_path / "results.csv",
        mock=True,
        latency_budget_ms=4000.0,
        cost_budget_usd=0.02,
    )


def test_runner_mock_writes_csv_with_expected_columns(tmp_path) -> None:
    """El runner en modo mock escribe un CSV con TODAS las columnas esperadas y >=1 fila."""
    config = _mock_config(tmp_path)

    with mock_litellm_seams():
        rows_written = run(config)

    assert rows_written >= 1
    assert config.output.exists()

    with config.output.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        # Las columnas del CSV deben coincidir EXACTAMENTE con el contrato ROW_FIELDS.
        assert reader.fieldnames == list(ROW_FIELDS)
        data = list(reader)

    # 1 escenario "growing" (8 turnos) x 2 tamaños x 1 repetición = 16 filas.
    assert len(data) == rows_written == 16


def test_runner_mock_rows_are_coherent(tmp_path) -> None:
    """Las filas del CSV son coherentes: columnas de turn_observed y métricas presentes."""
    config = _mock_config(tmp_path)

    with mock_litellm_seams():
        run(config)

    with config.output.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    # Comprobamos la primera fila: campos clave de la observación rellenos.
    first = rows[0]
    assert first["scenario"] == "growing"
    assert int(first["turn_index"]) == 1
    assert int(first["tokens_in"]) > 0  # token_counter offline cuenta de verdad
    assert first["cache_hit_kind"] == "none"  # el flujo conversacional no cachea (GAP documentado)

    # Las métricas binarias deben puntuar en {0.0, 1.0}.
    for row in rows:
        assert row["latency_budget_score"] in {"0.0", "1.0"}
        assert row["cost_budget_score"] in {"0.0", "1.0"}
        assert row["memory_drift_score"] in {"0.0", "1.0"}

    # turn_index es monótono y 1-based dentro de cada conversación (tamaño 0, repeat 1).
    size0 = [r for r in rows if r["attachment_size_kb"] == "0"]
    assert [int(r["turn_index"]) for r in size0] == list(range(1, 9))


def test_runner_mock_does_not_call_real_apis(tmp_path) -> None:
    """En modo mock el coste es bajo y no se lanza ninguna excepción de red/credenciales.

    No hay forma directa de "probar la ausencia de red"; como proxy, comprobamos que el
    runner completa la matriz y que el coste por turno es plausible y finito (calculado
    offline con litellm.cost_per_token), nunca None.
    """
    config = _mock_config(tmp_path)

    with mock_litellm_seams():
        run(config)

    with config.output.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    for row in rows:
        cost = float(row["cost_usd"])
        assert cost >= 0.0
        # El coste de muestra es pequeño (modelo económico, salida sintética corta).
        assert cost < 1.0
