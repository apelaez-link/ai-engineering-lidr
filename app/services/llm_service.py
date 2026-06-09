"""Capa de negocio del estimador (CAG).

Esta capa NO sabe de OpenAI ni de Anthropic ni de caché ni de fallback. Su única
responsabilidad es:
  - construir el system prompt CAG (rol + ejemplos de estimaciones inyectados),
  - montar la conversación (historial previo + nuevo mensaje) y aplicar la ventana
    deslizante,
  - delegar la llamada en el WRAPPER (`app.services.llm_wrapper`), que se encarga
    de abstracción, fallback, cacheo y logging.

Comparado con la sesión 02, lo único que cambia aquí es la última milla: antes
llamábamos directamente al SDK de OpenAI/Anthropic; ahora llamamos al wrapper. La
lógica CAG es idéntica.
"""

from collections.abc import Iterator

from app.config import get_settings
from app.context.examples import ESTIMATION_EXAMPLES
from app.services.llm_wrapper import wrapper


def _build_system_prompt() -> str:
    """Construye el system prompt: instrucciones + ejemplos de contexto inyectados.

    Esto es la inyección de contexto de CAG: los ejemplos viajan dentro del prompt
    en cada llamada, no se recuperan de ninguna base de datos.
    """
    # Serializamos los ejemplos a texto legible para el modelo.
    ejemplos_texto = "\n\n".join(
        f"### Ejemplo {i}\n"
        f"**Petición del cliente:** {ej['meeting_summary']}\n\n"
        f"**Estimación generada:**\n{ej['estimation']}"
        for i, ej in enumerate(ESTIMATION_EXAMPLES, start=1)
    )

    return f"""Eres un estimador de software senior. Tu trabajo es analizar la \
transcripción de una reunión con un cliente y generar una estimación de \
proyecto clara, realista y bien estructurada.

Te apoyas en estimaciones históricas previas como referencia de formato, nivel \
de detalle y criterio. A continuación tienes ejemplos de estimaciones reales \
que ha producido el equipo:

{ejemplos_texto}

Cuando recibas una nueva transcripción, genera una estimación siguiendo el \
mismo estilo y estructura que los ejemplos anteriores:
- Un título descriptivo del proyecto.
- Un desglose de tareas con horas estimadas para cada una.
- Total de horas estimado.
- Equipo recomendado.
- Duración estimada en semanas.
- Supuestos relevantes que has asumido.

Sé concreto y realista. Si la transcripción no aporta suficiente detalle sobre \
algún punto, indícalo explícitamente como supuesto."""


def _apply_sliding_window(conversation: list[dict], max_turns: int) -> list[dict]:
    """Ventana deslizante: conserva solo los últimos `max_turns` pares (user+assistant).

    El system prompt NO está en esta lista (se añade aparte en el wrapper), así que
    aquí solo recortamos el historial conversacional. Es la estrategia más simple del
    material 05; descarta los turnos más antiguos cuando la conversación crece.
    """
    max_messages = max_turns * 2
    if len(conversation) > max_messages:
        return conversation[-max_messages:]
    return conversation


def _build_conversation(transcription: str, history: list[dict] | None) -> list[dict]:
    """Conversación = turnos previos (solo user/assistant) + el nuevo mensaje + ventana."""
    settings = get_settings()
    conversation: list[dict] = [
        {"role": m["role"], "content": m["content"]} for m in (history or [])
    ]
    conversation.append({"role": "user", "content": transcription})
    return _apply_sliding_window(conversation, settings.llm_max_history_turns)


def generate_estimation(transcription: str, history: list[dict] | None = None) -> dict:
    """Punto de entrada del servicio (no streaming).

    Construye el prompt CAG y la conversación, delega en el wrapper (abstracción +
    fallback + caché + logging) y devuelve la estimación, metadatos de trazabilidad
    y el historial ACTUALIZADO (para reenviarlo en el siguiente turno).
    """
    system_prompt = _build_system_prompt()
    conversation = _build_conversation(transcription, history)

    result = wrapper.complete(system_prompt, conversation)

    # Guardamos la respuesta del modelo en el historial que devolvemos al cliente.
    updated_history = [*conversation, {"role": "assistant", "content": result.content}]

    return {
        "estimation": result.content,
        "model": result.model,
        "provider": result.provider,
        "history": updated_history,
        # Metadatos de trazabilidad (sesión 03): el endpoint los expone y la UI los muestra.
        "cache_hit": result.cache_hit,
        "fallback_used": result.fallback_used,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "cost_usd": result.cost_usd,
        "latency_ms": result.latency_ms,
    }


def stream_estimation(
    transcription: str, history: list[dict] | None = None, *, meta: dict | None = None
) -> Iterator[str]:
    """Versión en streaming: produce la estimación token a token.

    Devuelve un generador de fragmentos de texto (ideal para `st.write_stream` o un
    endpoint SSE). Los metadatos de la llamada (modelo, tokens, coste, cache_hit...)
    se vuelcan en el dict `meta` cuando termina la generación.
    """
    system_prompt = _build_system_prompt()
    conversation = _build_conversation(transcription, history)
    yield from wrapper.stream(system_prompt, conversation, meta=meta)
