"""Runner CLI del stress test del CAG (sesión 06, BLOQUE 5).

Orquesta la matriz ESCENARIOS x TAMAÑOS-DE-ADJUNTO x REPETICIONES x TURNOS contra el
estimador conversacional, lee la observación (``turn_observed``) de cada turno, evalúa
las tres métricas deterministas y vuelca una fila por turno a un CSV. Ese CSV es el
material crudo con el que el REPORT dibuja las curvas "dónde empieza a romperse el CAG".

DOS MODOS DE TRANSPORTE:
  - in-process (por defecto): habla con la app vía TestClient de FastAPI, sin levantar
    servidor. Ideal para CI y para iterar rápido.
  - --http <url>: habla con un servidor real por HTTP (httpx). Es el modo del
    deliverable real, con un backend y una API key de verdad.

MODO MOCK (--mock, o automático si no hay API key):
  Parchea las "costuras" que llamarían a litellm/OpenAI (la generación estructurada y
  el extractor de metadatos, ambas vía Instructor->litellm) por funciones SINTÉTICAS
  que NO tocan la red. Así el runner produce un results.csv de MUESTRA con coste 0 y
  sin claves. El mock introduce una latencia simulada proporcional al tamaño del
  contexto, para que las curvas latencia-vs-tokens tengan forma realista. El conteo de
  tokens y el coste se calculan con litellm.token_counter/cost_per_token, que funcionan
  OFFLINE y de forma determinista (no llaman a ninguna API).

  El modo mock SOLO tiene sentido in-process (necesita parchear el proceso de la app);
  con --http el servidor es ajeno y el parcheo no aplica.

LECTURA DE turn_observed: el runner lo lee del campo ``observation`` de la respuesta
JSON del endpoint POST /sessions/{id}/estimate (ver app/services/observation.py y
app/schemas.EstimationResponseStructured). No parsea logs.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from evals.stress.fixtures.build_pdfs import build_pdf_bytes
from evals.stress.metrics import CostBudgetMetric, LatencyBudgetMetric, MemoryDriftMetric
from evals.stress.scenarios import get_scenario

# Presupuestos POR DEFECTO de las métricas (ajustables por CLI). Son didácticos: con
# ellos el REPORT muestra a partir de qué tamaño/turno se "rompe" cada presupuesto.
DEFAULT_LATENCY_BUDGET_MS = 4000.0
DEFAULT_COST_BUDGET_USD = 0.02

# Columnas del CSV. Primero las del turn_observed (en orden estable), luego una por
# métrica (score + passed) y las claves de la fila (escenario, tamaño, repetición).
OBSERVATION_FIELDS: tuple[str, ...] = (
    "turn_index",
    "session_id",
    "enriched_transcript_chars",
    "attachments_total_chars",
    "messages_in_window",
    "anchors_count",
    "summary_chars",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "latency_ms",
    "cache_hit_kind",
    "last_resolved_tier",
)

ROW_FIELDS: tuple[str, ...] = (
    "scenario",
    "attachment_size_kb",
    "repeat",
    *OBSERVATION_FIELDS,
    "fact_to_remember",
    "latency_budget_score",
    "latency_budget_passed",
    "cost_budget_score",
    "cost_budget_passed",
    "memory_drift_score",
    "memory_drift_passed",
)


@dataclass
class RunConfig:
    """Configuración resuelta de una ejecución del runner (desde los args del CLI)."""

    http_url: str | None
    scenarios: list[str]
    attachment_sizes: list[int]
    repeats: int
    output: Path
    mock: bool
    latency_budget_ms: float
    cost_budget_usd: float


# ── Cliente de transporte (in-process TestClient o HTTP httpx) ────────────────


class Transport:
    """Abstracción mínima del transporte: crear sesión, estimar un turno, leer snapshot.

    Dos implementaciones la cumplen (in-process y HTTP) para que el bucle de
    orquestación no sepa por dónde viajan las peticiones.
    """

    def create_session(self) -> str:  # pragma: no cover - interfaz
        raise NotImplementedError

    def estimate(
        self, session_id: str, transcript: str, attachment: tuple[str, bytes] | None
    ) -> dict:  # pragma: no cover - interfaz
        raise NotImplementedError

    def snapshot(self, session_id: str) -> dict:  # pragma: no cover - interfaz
        raise NotImplementedError


class InProcessTransport(Transport):
    """Transporte in-process: usa el TestClient de FastAPI (sin servidor)."""

    def __init__(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import app

        self._client = TestClient(app)

    def create_session(self) -> str:
        resp = self._client.post("/api/v1/sessions")
        resp.raise_for_status()
        return resp.json()["session_id"]

    def estimate(
        self, session_id: str, transcript: str, attachment: tuple[str, bytes] | None
    ) -> dict:
        files = None
        if attachment is not None:
            filename, data = attachment
            files = {"attachments": (filename, data, "application/pdf")}
        resp = self._client.post(
            f"/api/v1/sessions/{session_id}/estimate",
            data={"transcript": transcript},
            files=files,
        )
        resp.raise_for_status()
        return resp.json()

    def snapshot(self, session_id: str) -> dict:
        resp = self._client.get(f"/api/v1/sessions/{session_id}")
        resp.raise_for_status()
        return resp.json()


class HttpTransport(Transport):
    """Transporte HTTP: habla con un servidor real con httpx (modo deliverable real)."""

    def __init__(self, base_url: str) -> None:
        import httpx

        self._base = base_url.rstrip("/")
        self._client = httpx.Client(timeout=60.0)

    def create_session(self) -> str:
        resp = self._client.post(f"{self._base}/api/v1/sessions")
        resp.raise_for_status()
        return resp.json()["session_id"]

    def estimate(
        self, session_id: str, transcript: str, attachment: tuple[str, bytes] | None
    ) -> dict:
        files = None
        if attachment is not None:
            filename, data = attachment
            files = {"attachments": (filename, data, "application/pdf")}
        resp = self._client.post(
            f"{self._base}/api/v1/sessions/{session_id}/estimate",
            data={"transcript": transcript},
            files=files,
        )
        resp.raise_for_status()
        return resp.json()

    def snapshot(self, session_id: str) -> dict:
        resp = self._client.get(f"{self._base}/api/v1/sessions/{session_id}")
        resp.raise_for_status()
        return resp.json()


# ── Modo MOCK: parcheo de las costuras que llamarían a litellm ────────────────


def _synthetic_result(messages: list[dict], *args, **kwargs):
    """Generación estructurada SINTÉTICA (sustituye a la real en modo mock).

    Devuelve un EstimationResult válido y coherente, SIN llamar a ningún LLM. Para que
    las curvas de latencia tengan forma realista, simula un tiempo de proceso
    proporcional al tamaño del contexto enviado (más contexto -> más "lento"), con un
    pequeño coste base. Es puramente didáctico: NO mide nada real, solo da forma a la
    muestra.
    """
    from app.schemas import EstimationResult, Phase

    # Tamaño total del contexto (caracteres de todos los mensajes) -> latencia simulada.
    context_chars = sum(len(m.get("content", "")) for m in messages)
    # ~0.3 ms por cada 1000 caracteres, sobre una base de 50 ms. Cota superior para no
    # eternizar la ejecución de muestra aunque el contexto sea enorme.
    simulated_ms = min(50.0 + context_chars * 0.0003, 1500.0)
    time.sleep(simulated_ms / 1000.0)

    return EstimationResult(
        summary="Synthetic mock estimate for stress testing (no LLM called).",
        total_duration_weeks=10,
        total_cost_eur=80_000,
        confidence_pct=75,
        phases=[
            Phase(name="Backend API", duration_weeks=6, cost_eur=48_000, confidence_pct=80),
            Phase(name="Frontend", duration_weeks=4, cost_eur=32_000, confidence_pct=70),
        ],
    )


def _synthetic_extract_metadata(transcript: str, assistant_text: str, current, *args, **kwargs):
    """Extractor de metadatos SINTÉTICO (sustituye al real en modo mock).

    En lugar de llamar a un LLM, aplica una heurística mínima sobre el transcript para
    que la MEMORIA evolucione de forma plausible turno a turno (y así MemoryDriftMetric
    tenga algo que medir): capta un nombre de proyecto, tecnologías conocidas y guarda
    el último presupuesto mencionado en el alcance. Luego mergea con la memoria previa.

    Modela a propósito un comportamiento IMPERFECTO (lo que un extractor real haría):
    el nombre del proyecto solo se capta cuando aparece el patrón "project X" o
    "building X"; un mero pronombre no basta. Esto hace que el escenario "growing", que
    no repite el nombre cada turno, muestre cierta deriva de memoria en la muestra.
    """
    from app.sessions.models import ProjectMetadata

    text = transcript or ""
    lowered = text.lower()

    # 1) Nombre del proyecto: heurística sobre "project X" / "build(ing) X".
    project_name = None
    for marker in ("project ", "building ", "build "):
        idx = lowered.find(marker)
        if idx != -1:
            tail = text[idx + len(marker):].strip()
            # Primera palabra "tipo nombre propio" (alfanumérica), sin puntuación.
            token = tail.split(",")[0].split(".")[0].split()[0] if tail.split() else ""
            token = token.strip(",.:;")
            if token and token[0].isupper():
                project_name = token
                break

    # 2) Tecnologías conocidas mencionadas en el turno.
    known_techs = ["Django", "React", "Go", "Golang", "Vue", "FastAPI", "Postgres", "Kafka"]
    techs = [t for t in known_techs if t.lower() in lowered]

    # 3) Presupuesto: guardamos el ÚLTIMO mencionado en el alcance (para contradiction).
    scope = ""
    for budget in ("80k", "30k"):
        if budget in lowered:
            scope = f"budget {budget}"
            break

    extracted = ProjectMetadata(
        project_name=project_name,
        mentioned_technologies=techs,
        agreed_scope=scope,
    )
    return current.merge(extracted)


@contextmanager
def mock_litellm_seams() -> Iterator[None]:
    """Parchea, en el proceso de la app, las costuras que llamarían a litellm.

    Sustituye por funciones sintéticas:
      - app.routers.sessions.generate_structured_from_messages (Instructor->litellm).
      - app.routers.sessions.extract_metadata (Instructor->litellm).
    Y neutraliza litellm.moderation (guardrail de entrada) para que no intente red.

    NO parchea litellm.token_counter ni litellm.cost_per_token: funcionan OFFLINE y
    queremos conteos/coste deterministas y realistas en la muestra. Resultado: cero
    llamadas a APIs externas.
    """
    from unittest.mock import patch

    with ExitStack() as stack:
        stack.enter_context(
            patch("app.routers.sessions.generate_structured_from_messages", _synthetic_result)
        )
        stack.enter_context(
            patch("app.routers.sessions.extract_metadata", _synthetic_extract_metadata)
        )
        # Moderación: devolvemos "no flagged" sin tocar red.
        from types import SimpleNamespace

        stack.enter_context(
            patch(
                "litellm.moderation",
                return_value=SimpleNamespace(results=[SimpleNamespace(flagged=False)]),
            )
        )
        yield


def _has_api_key() -> bool:
    """True si hay alguna API key configurada (para decidir el modo mock automático)."""
    try:
        from app.config import get_settings

        settings = get_settings()
        return bool(settings.openai_api_key or settings.anthropic_api_key)
    except Exception:  # noqa: BLE001
        return False


# ── Orquestación ──────────────────────────────────────────────────────────────


def _build_attachment(size_kb: int) -> tuple[str, bytes] | None:
    """Construye el adjunto para un tamaño dado. 0 KB = sin adjunto (None)."""
    if size_kb <= 0:
        return None
    data = build_pdf_bytes(size_kb)
    return (f"lorem_{size_kb}kb.pdf", data)


def _evaluate_row(
    observation: dict,
    snapshot: dict,
    fact: str,
    config: RunConfig,
) -> dict:
    """Evalúa las tres métricas sobre un turno y devuelve la fila completa del CSV."""
    latency = LatencyBudgetMetric(config.latency_budget_ms).evaluate(
        observation.get("latency_ms", 0.0)
    )
    cost = CostBudgetMetric(config.cost_budget_usd).evaluate(observation.get("cost_usd", 0.0))
    # Para la deriva de memoria ampliamos `where` con "history": en nuestra base no hay
    # summary ni anchors, así que el historial (texto de los turnos) es la segunda fuente
    # además del ProjectMetadata. El snapshot del endpoint trae project_metadata.
    drift = MemoryDriftMetric(
        fact=fact, where=["summary", "anchors", "metadata", "history"]
    ).evaluate(snapshot)

    return {
        "latency_budget_score": latency.score,
        "latency_budget_passed": latency.passed,
        "cost_budget_score": cost.score,
        "cost_budget_passed": cost.passed,
        "memory_drift_score": drift.score,
        "memory_drift_passed": drift.passed,
    }


def _estimate_with_retries(
    transport: "Transport",
    session_id: str,
    transcript: str,
    attachment: tuple[str, bytes] | None,
    attempts: int = 3,
) -> dict | None:
    """Llama a ``transport.estimate`` con reintentos + backoff lineal.

    Robustez para ejecuciones DESATENDIDAS contra APIs reales: un 429/500/timeout
    transitorio no debe abortar toda la matriz (que puede ser de cientos de turnos).
    Reintentar el MISMO turno es seguro porque el router solo actualiza el historial y
    el ProjectMetadata en el camino de ÉXITO: si la generación falla (HTTP 5xx), el
    estado de la sesión no avanza y el reintento parte del mismo punto.

    Devuelve la respuesta JSON del turno, o ``None`` si agota los reintentos (el
    llamante salta esa fila con un aviso, en vez de tumbar toda la ejecución). En modo
    mock no hay red, así que el primer intento siempre pasa: este camino solo se activa
    con llamadas reales.
    """
    for attempt in range(1, attempts + 1):
        try:
            return transport.estimate(session_id, transcript, attachment)
        except Exception as exc:  # noqa: BLE001 — cualquier fallo transitorio de transporte/API
            if attempt == attempts:
                print(
                    f"[stress] estimate falló definitivamente ({attempt}/{attempts}): {exc}",
                    file=sys.stderr,
                )
                return None
            print(
                f"[stress] estimate falló ({attempt}/{attempts}), reintento: {exc}",
                file=sys.stderr,
            )
            time.sleep(2.0 * attempt)
    return None


def run(config: RunConfig) -> int:
    """Ejecuta la matriz completa y escribe el CSV. Devuelve el nº de filas escritas."""
    transport = (
        HttpTransport(config.http_url)
        if config.http_url is not None
        else InProcessTransport()
    )

    config.output.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0

    with config.output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(ROW_FIELDS))
        writer.writeheader()

        for scenario_name in config.scenarios:
            turns = get_scenario(scenario_name)
            for size_kb in config.attachment_sizes:
                for repeat in range(1, config.repeats + 1):
                    # Cada (escenario, tamaño, repetición) es una conversación nueva.
                    session_id = transport.create_session()
                    for turn_index, transcript, fact in turns:
                        attachment = _build_attachment(size_kb)
                        response = _estimate_with_retries(
                            transport, session_id, transcript, attachment
                        )
                        if response is None:
                            # Turno irrecuperable tras reintentos: lo saltamos con aviso.
                            # No escribimos fila (mejor un CSV con menos filas y limpio
                            # que una ejecución abortada a la mitad).
                            print(
                                f"[stress] saltado turno {scenario_name}/{size_kb}KB/"
                                f"rep{repeat}/t{turn_index}",
                                file=sys.stderr,
                            )
                            continue
                        observation = response.get("observation") or {}

                        # Snapshot de la sesión + historial reconstruido para el drift.
                        snapshot = transport.snapshot(session_id)
                        snapshot = _enrich_snapshot_with_history(snapshot, transcript)

                        metric_cols = _evaluate_row(observation, snapshot, fact, config)

                        row = {
                            "scenario": scenario_name,
                            "attachment_size_kb": size_kb,
                            "repeat": repeat,
                            "fact_to_remember": fact,
                            **{k: observation.get(k) for k in OBSERVATION_FIELDS},
                            **metric_cols,
                        }
                        writer.writerow(row)
                        rows_written += 1

    return rows_written


def _enrich_snapshot_with_history(snapshot: dict, latest_transcript: str) -> dict:
    """Añade al snapshot un campo "history" (texto) para alimentar MemoryDriftMetric.

    El endpoint GET /sessions/{id} devuelve project_metadata y el nº de turnos, pero no
    el texto del historial. Para que la deriva de memoria pueda detectar un hecho que
    quedó en la conversación pero no en los metadatos, añadimos al menos el transcript
    del turno actual como "history". (Con --http real, project_metadata suele bastar;
    este campo es la red de seguridad del GAP: sin summarizer/anclas, el historial es
    la fuente secundaria.)
    """
    enriched = dict(snapshot)
    enriched["history"] = latest_transcript
    # Normalizamos la clave que espera la métrica.
    if "project_metadata" in enriched and "metadata" not in enriched:
        enriched["metadata"] = enriched["project_metadata"]
    return enriched


# ── CLI ────────────────────────────────────────────────────────────────────────


def _parse_int_list(raw: str) -> list[int]:
    """Parsea "0,5,20,50,100" -> [0, 5, 20, 50, 100]."""
    return [int(x.strip()) for x in raw.split(",") if x.strip() != ""]


def _parse_str_list(raw: str) -> list[str]:
    """Parsea "growing,pivot" -> ["growing", "pivot"]."""
    return [x.strip() for x in raw.split(",") if x.strip()]


def build_config(argv: list[str] | None = None) -> RunConfig:
    """Parsea los argumentos del CLI y resuelve la configuración (incl. mock automático)."""
    parser = argparse.ArgumentParser(
        prog="evals.stress.run",
        description="Stress test del CAG: orquesta escenarios x tamaños x repeticiones y mide.",
    )
    parser.add_argument(
        "--http",
        dest="http_url",
        default=None,
        help="URL del servidor real (modo httpx). Si se omite, modo in-process (TestClient).",
    )
    parser.add_argument(
        "--scenarios",
        default="growing,pivot,contradiction",
        help="Lista separada por comas: growing,pivot,contradiction.",
    )
    parser.add_argument(
        "--attachment-sizes",
        dest="attachment_sizes",
        default="0,5,20,50,100",
        help="Tamaños de adjunto en KB separados por comas. 0 = sin adjunto.",
    )
    parser.add_argument("--repeats", type=int, default=3, help="Repeticiones por combinación.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/stress/results.csv"),
        help="Ruta del CSV de salida.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Fuerza el modo mock (parchea litellm). Automático si no hay API key.",
    )
    parser.add_argument(
        "--latency-budget-ms",
        dest="latency_budget_ms",
        type=float,
        default=DEFAULT_LATENCY_BUDGET_MS,
        help=f"Presupuesto de latencia por turno (ms). Default {DEFAULT_LATENCY_BUDGET_MS}.",
    )
    parser.add_argument(
        "--cost-budget-usd",
        dest="cost_budget_usd",
        type=float,
        default=DEFAULT_COST_BUDGET_USD,
        help=f"Presupuesto de coste por turno (USD). Default {DEFAULT_COST_BUDGET_USD}.",
    )
    args = parser.parse_args(argv)

    # Mock automático: si no se fuerza y no hay API key, vamos a mock para no fallar.
    # Con --http el mock no aplica (el servidor es ajeno): solo se respeta in-process.
    mock = args.mock or (args.http_url is None and not _has_api_key())

    return RunConfig(
        http_url=args.http_url,
        scenarios=_parse_str_list(args.scenarios),
        attachment_sizes=_parse_int_list(args.attachment_sizes),
        repeats=args.repeats,
        output=args.output,
        mock=mock,
        latency_budget_ms=args.latency_budget_ms,
        cost_budget_usd=args.cost_budget_usd,
    )


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada del CLI. Devuelve un código de salida (0 = ok)."""
    config = build_config(argv)

    mode = "HTTP" if config.http_url else "in-process"
    mock_note = " (MOCK: sin llamadas reales a APIs)" if config.mock else ""
    print(
        f"[stress] modo={mode}{mock_note} scenarios={config.scenarios} "
        f"sizes={config.attachment_sizes}KB repeats={config.repeats} -> {config.output}"
    )

    if config.mock and config.http_url is not None:
        print(
            "[stress] AVISO: --mock no aplica con --http (el servidor es un proceso ajeno). "
            "Para datos reales lanza el servidor con una API key y omite --mock.",
            file=sys.stderr,
        )

    if config.mock and config.http_url is None:
        # Parcheamos las costuras de litellm SOLO en modo mock in-process.
        with mock_litellm_seams():
            rows = run(config)
    else:
        rows = run(config)

    print(f"[stress] listo: {rows} filas escritas en {config.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
