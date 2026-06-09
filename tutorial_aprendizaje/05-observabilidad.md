# 05 — Observabilidad y trazabilidad

> 📚 **Concepto del curso:** [material_curso/05](material_curso/05-observabilidad.md)
> 🧩 **Código:** `app/logging_config.py` (+ uso en `app/services/llm_wrapper.py`)

## La idea en una frase

Con LLMs, "respondió 200 en 4 s" no te dice nada útil. Necesitas saber qué modelo respondió,
cuántos tokens, cuánto costó, si vino de caché y si hubo fallback. Eso se consigue tratando los
**logs como datos** (campos tipados), no como frases.

## Structured logging con structlog (`logging_config.py`)

La pieza central es la **cadena de procesadores**: cada uno recibe el dict del evento, lo
enriquece y lo pasa al siguiente; el último es el *renderer*. Configuración **dual**:
```python
shared_processors = [
    structlog.contextvars.merge_contextvars,   # contexto por request
    structlog.processors.add_log_level,         # "level"
    structlog.processors.TimeStamper(fmt="iso"),# "timestamp"
    ...
]
renderer = JSONRenderer() if env == "production" else ConsoleRenderer(colors=True)
```
- **`ENV=development`** → consola coloreada y legible (lo que viste en el smoke test:
  `llm_call_completed   model=gpt-4o-mini tokens_in=120 tokens_out=210 cost_usd=0.0003 …`).
- **`ENV=production`** → una línea JSON por evento, lista para Elasticsearch/Loki/CloudWatch/
  Logfire/Langfuse.

El mismo código, dos salidas. Cambiar de una a otra es una variable de entorno.

## Qué registra el wrapper en cada llamada

En `llm_wrapper.py`, cada proveedor que se intenta tiene un logger con contexto vinculado:
```python
call_log = logger.bind(provider=provider, model=model, fallback=is_fallback)
call_log.info("llm_call_started")
# ... éxito:
call_log.info("llm_call_completed", latency_ms=..., tokens_in=..., tokens_out=...,
              cost_usd=..., finish_reason=..., fallback_used=is_fallback)
# ... error:
call_log.warning("fallback_triggered", error_type=..., next_provider=...)   # rate limit/timeout/5xx
call_log.error("llm_call_failed", error_type=..., error_msg=...)            # auth/inesperado
```
Es el patrón **inicio / completado / error** del material, con los campos propios de LLMs
(tokens, coste) en vez de status codes. `logger.bind(...)` añade `provider`, `model` y
`fallback` a *todas* las líneas de esa llamada sin repetirlos.

Esos mismos campos viajan también al cliente: en la respuesta de `/estimate`
(`cache_hit`, `tokens_in`, `cost_usd`, `latency_ms`, `fallback_used`) y en el evento `done` del
streaming. Así, la trazabilidad no solo está en los logs del servidor, también en la API y en
el sidebar de Streamlit.

## Por qué structlog y no las herramientas grandes (todavía)

El material presenta Logfire (full-stack, sobre OpenTelemetry, free tier generoso), Langfuse
(open source auto-hosteable) y LangSmith (si usas LangChain). **La recomendación es empezar por
structlog**: cero dependencias externas, y los logs JSON que produce son directamente
ingeribles por *cualquiera* de esas herramientas el día que las añadas. Es la base, no un
competidor de ellas. (Logfire encaja especialmente bien con nuestro stack Pydantic+FastAPI; se
deja como mejora opcional.)

## Reto

1. **Mira los logs en dev:** arranca el servidor y haz una estimación. Observa en el terminal
   `llm_call_started` y `llm_call_completed` con sus campos. Repite la misma transcripción y
   busca `llm_cache_hit`.
2. **Cambia a JSON:** pon `ENV=production` en `.env`, reinicia, repite. Ahora cada evento es una
   línea JSON. Cópiala y pégala mentalmente en un dashboard: ya puedes filtrar por `model` o
   sumar `cost_usd`.
3. **`request_id` por petición (mini-reto pro):** añade un middleware en `app/main.py` que en
   cada request haga `structlog.contextvars.bind_contextvars(request_id=...)`. Como ya incluimos
   `merge_contextvars` en la cadena, ese `request_id` aparecerá automáticamente en *todos* los
   logs de esa petición. Pista: `from uuid import uuid4`.
4. **Coste acumulado:** suma el `cost_usd` de varias llamadas (de los logs JSON) y estima cuánto
   te costaría 1.000 estimaciones. Conecta con la lección 03: ¿cuánto ahorra la caché con un
   hit rate del 50%?
