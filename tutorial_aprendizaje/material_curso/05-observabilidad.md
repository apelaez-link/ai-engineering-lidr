# 05 — Observabilidad, logging y trazabilidad

> Material del curso LIDR · AI Engineering · Sesión 3 (Antonio Pérez). Recuperado de la plataforma. (≈16 min)

## Por qué el logging estándar no es suficiente

En web registras errores, requests y algún evento de negocio. Con LLMs ese nivel es **ciego**:
sabes que `/estimate` respondió 200 en 4.2 s, pero no qué prompt se envió, cuántos tokens
consumió, cuánto costó, qué modelo respondió (¿OpenAI o el fallback a Anthropic?), si vino de
caché, ni por qué la calidad es dudosa. En apps clásicas el código es determinista; con LLMs
el modelo es una **caja negra probabilística** cuya calidad depende de factores que no
controlas del todo. Debuggear sin trazabilidad es trabajar a ciegas.

La trazabilidad necesita cubrir tres dimensiones que el logging web no contempla:
- **Qué se envió y recibió** — prompt completo (system+user), respuesta literal, parámetros.
- **Cuánto costó** — tokens in/out, modelo, coste. Un bug que genera respuestas larguísimas
  multiplica tu factura antes de que lo notes.
- **Qué camino siguió** — ¿caché? ¿fallback? ¿reintentos? ¿cuánto tardó cada fase?

## Structured logging: la base

En vez de texto plano (`"LLM call completed in 3.2s"`), registramos **objetos estructurados
con campos tipados**, parseables por máquinas:
```json
{"timestamp":"2026-04-02T10:30:15.123Z","level":"info","event":"llm_call_completed",
 "model":"gpt-4o-mini","provider":"openai","tokens_in":1847,"tokens_out":423,
 "cost_usd":0.00089,"latency_ms":3215,"cache_hit":false,"fallback_used":false}
```
Ahora puedes filtrar por modelo, agregar costes por periodo, detectar picos de latencia y
calcular tu hit rate — programáticamente, sin regex.

## Structlog (la librería que usamos)

"Los logs son datos, no strings." Configuración dual (consola legible en dev, JSON en prod):
```python
import structlog, logging, os

def configure_logging():
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    shared = [
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.EventRenamer("msg"),
    ]
    if os.environ.get("ENV") == "production":
        structlog.configure(processors=shared + [structlog.processors.JSONRenderer()],
            wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level)))
    else:
        structlog.configure(processors=shared + [structlog.dev.ConsoleRenderer()],
            wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level)))
```
**Cadena de procesadores:** cada uno recibe el dict del evento, lo enriquece y lo pasa al
siguiente; el último es el *renderer* (JSON en prod, consola en dev). La config dual es un
patrón que usarás en casi todo proyecto: en dev lees rápido en el terminal; en prod tus logs
los ingiere Elasticsearch/Loki/CloudWatch (todos esperan JSON).

**Contexto vinculado** con `bind()` — no repites campos comunes en cada llamada:
```python
request_logger = logger.bind(request_id="req-abc-123", endpoint="/estimate")
request_logger.info("llm_call_started", model="gpt-4o-mini", tokens_in=1847)
request_logger.info("llm_call_completed", latency_ms=3215, cache_hit=False)
```
En FastAPI, el `bind` del `request_id` se haría en un middleware por request entrante.

## Qué registrar en cada llamada al LLM

- **Al inicio:** modelo solicitado, proveedor destino, tokens de entrada, si viene de caché.
- **Al completar:** tokens de salida, latencia (ms), coste (USD), `finish_reason`, si hubo
  fallback y a qué proveedor.
- **En error:** tipo de error (timeout/rate limit/auth/server), proveedor que falló, si se
  intentará fallback, número de reintento.

```python
class LLMWrapper:
    def completion(self, messages, model):
        call_logger = logger.bind(model=model)
        call_logger.info("llm_call_started")
        start = time.time()
        try:
            response = self._call_provider(messages, model)
            call_logger.info("llm_call_completed",
                latency_ms=round((time.time()-start)*1000, 1),
                tokens_in=response.usage.prompt_tokens, tokens_out=response.usage.completion_tokens,
                finish_reason=response.choices[0].finish_reason, cache_hit=False)
            return response
        except Exception as e:
            call_logger.error("llm_call_failed", error_type=type(e).__name__, error_msg=str(e),
                latency_ms=round((time.time()-start)*1000, 1))
            raise
```
Patrón log-al-inicio / log-al-completar / log-en-error, igual que para requests HTTP o queries;
lo que cambia son los campos (tokens y costes en vez de status codes y row counts).

## Más allá del logging: herramientas de observabilidad

- **Full-stack:** **Pydantic Logfire** (del equipo de Pydantic, sobre OpenTelemetry) — trazas
  unificadas (HTTP entrante → Redis → LLM → respuesta), paneles para LLMs, monitorización de
  costes, instrumentación nativa de FastAPI/OpenAI/Anthropic/LiteLLM/Redis con 1 línea, SQL
  sobre las trazas. Free tier 10M spans/mes.
- **Específicas de LLMs:** **LangSmith** (de LangChain; integración automática si usas
  LangChain/LangGraph; ideal para razonamiento de agentes). **Langfuse** (open source, MIT,
  auto-hosteable, OpenTelemetry; tracing + prompts + evals + datasets). **Helicone** (cambias
  una URL base y listo).

**Recomendación práctica:** empieza con **structlog** (sin dependencias externas, base que
alimenta a todas las demás); añade **Logfire** si quieres observabilidad visual (natural para
Pydantic+FastAPI); **Langfuse** si necesitas open source auto-hosteable; **LangSmith** si ya
usas LangChain (módulos 12-14). No necesitas todas a la vez.

## Recursos
- Better Stack — "A Comprehensive Guide to Python Logging with Structlog"
- Pydantic Logfire — "AI & LLM Observability"
- Firecrawl — "Best LLM Observability Tools in 2026"
