"""Observabilidad por TURNO del estimador conversacional (sesión 06).

Lección de la sesión 06: "Stress test del CAG — medir dónde rompe". Antes de poder
decir *dónde* se degrada el CAG (Context-Augmented Generation), necesitamos MEDIR
cada turno de forma estructurada. Este módulo define el contrato de esa medición —
el evento ``turn_observed`` — y la función que lo construye a partir de lo que SÍ
existe en nuestra base (pre-session-05).

¿Por qué un módulo aparte y no inline en el router?
  - El router orquesta el flujo HTTP; la MEDICIÓN es una preocupación transversal.
  - Aislarla aquí la hace testeable sin levantar la app y reutilizable si mañana
    extraemos el flujo de estimación a un servicio.

GAP respecto al enunciado del directo (documentado a conciencia):
  El enunciado original asume piezas que en NUESTRA base aún no existen porque eran
  del DIRECTO de la sesión 5 (no implementado): anclas (anchors), summarizer
  acumulativo, tier dinámico y Actor-Critic-Boss. Por tanto medimos lo que existe y
  emitimos los campos dependientes de esas piezas con un valor por defecto explícito:

    - anchors_count    -> 0     (no hay sistema de anclas)
    - summary_chars    -> 0     (no hay summarizer acumulativo)
    - last_resolved_tier -> None (no hay tier dinámico)

  Mantenemos los campos en el contrato (en lugar de borrarlos) para que el harness
  de stress y el REPORT tengan el MISMO esquema que tendría la versión "completa":
  el día que se implementen esas piezas, basta con rellenar estos campos y el resto
  del pipeline de medición no cambia.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import litellm

from app.logging_config import get_logger

logger = get_logger(component="observation")

# Tipo del campo cache_hit_kind: de dónde vino la respuesta del turno.
#   "none"     -> generación real (sin caché).
#   "exact"    -> cacheo exact-match (app/cache/llm_cache.py).
#   "semantic" -> cacheo semántico (app/cache/semantic.py).
CacheHitKind = Literal["none", "exact", "semantic"]


@dataclass
class TurnObservation:
    """Una observación estructurada de UN turno conversacional (evento ``turn_observed``).

    Es el "registro de medición" que el stress test analiza después. Reúne tres
    familias de señales:

      1. CONTEXTO (cuánto le metemos al modelo):
         - enriched_transcript_chars: tamaño del contexto enriquecido del turno
           (transcript del usuario + texto extraído de los adjuntos), en caracteres.
         - attachments_total_chars: solo la parte de adjuntos (subconjunto del anterior).
         - messages_in_window: nº de mensajes del historial que sobreviven a la
           ventana deslizante (proxy de "cuánta memoria viaja").
         - anchors_count / summary_chars: a 0 por el GAP (ver módulo docstring).

      2. COSTE/RENDIMIENTO (qué nos cuesta):
         - tokens_in / tokens_out: contados con litellm.token_counter.
         - cost_usd: derivado con litellm.cost_per_token.
         - latency_ms: medido con time.perf_counter alrededor de la generación.

      3. PROCEDENCIA (de dónde vino):
         - cache_hit_kind: none/exact/semantic.
         - last_resolved_tier: None por el GAP (no hay tier dinámico).

    Identidad del turno: turn_index (1-based dentro de la sesión) + session_id.
    """

    turn_index: int
    session_id: str
    enriched_transcript_chars: int
    attachments_total_chars: int
    messages_in_window: int
    anchors_count: int
    summary_chars: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: float
    cache_hit_kind: CacheHitKind
    last_resolved_tier: str | None

    def to_dict(self) -> dict:
        """Serializa la observación a un dict plano (para el log y la respuesta HTTP)."""
        return asdict(self)


def count_tokens_and_cost(
    model: str, messages: list[dict], output_text: str
) -> tuple[int, int, float]:
    """Cuenta tokens de entrada/salida y estima el coste en USD de un turno.

    Reutiliza exactamente la mecánica de ``llm_wrapper._stream_usage`` (la referencia
    que pide el enunciado): ``litellm.token_counter`` para los tokens y
    ``litellm.cost_per_token`` para el coste. Es DEFENSIVA: si el tokenizer o el mapa
    de precios no conocen el modelo (o si litellm está parcheado en modo mock),
    devolvemos ceros en lugar de romper la medición.

    Args:
        model: Identificador del modelo (el mismo que se pasó a la generación).
        messages: La lista de mensajes enviada al modelo (system + historial + turno).
        output_text: El texto de la respuesta del asistente (aquí, el ``summary``).

    Returns:
        (tokens_in, tokens_out, cost_usd).
    """
    try:
        tokens_in = litellm.token_counter(model=model, messages=messages)
        tokens_out = litellm.token_counter(model=model, text=output_text)
    except Exception:  # noqa: BLE001 — la medición nunca debe tumbar el turno
        return 0, 0, 0.0

    try:
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=model, prompt_tokens=tokens_in, completion_tokens=tokens_out
        )
        cost = float(prompt_cost) + float(completion_cost)
    except Exception:  # noqa: BLE001 — modelo sin precio en el mapa, etc.
        cost = 0.0

    return tokens_in, tokens_out, cost


def emit_turn_observed(observation: TurnObservation) -> dict:
    """Emite el evento ``turn_observed`` por structlog y devuelve su dict.

    DOBLE SALIDA, por decisión de diseño explícita del ejercicio:

      1. LOG estructurado: ``logger.info("turn_observed", ...)``. Es la fuente de
         verdad para producción (lo ingiere Loki/Logfire/CloudWatch y se agrega ahí).
      2. DICT devuelto: el router lo adjunta como campo ``observation`` en la respuesta
         HTTP. Así el runner del stress test lo lee DIRECTAMENTE de la respuesta del
         endpoint, sin tener que parsear logs ni instrumentar un colector. Es la vía
         más simple y robusta para un harness de evals que orquesta muchos turnos.

    Devuelve el mismo dict que loguea, para que el llamante lo reutilice sin recalcular.
    """
    payload = observation.to_dict()
    logger.info("turn_observed", **payload)
    return payload
