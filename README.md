# Estimador CAG — Proyecto 1 (curso AI Engineering LIDR)

> 📂 **Sobre este repositorio (`ai-engineering-lidr`).** Es el repo **continuo** del curso.
> El proyecto crece sesión a sesión y cada entrega se organiza así:
> - `main` → última versión acumulada del proyecto.
> - Una rama por sesión (`sesion-03`, `sesion-04`, …) que se mergea a `main` al terminar.
> - Un tag por entrega (`entrega-sesion-03`, …) que marca el estado exacto entregado.
>
> Para revisar lo entregado en una sesión concreta: `git checkout entrega-sesion-NN`.
> El historial previo (Sesión 2 — scaffolding) vive en su propio repo `01-scaffolding-proyecto-fast-api`.

De **prototipo** a **producto**. Partiendo del endpoint CAG de la sesión 02 (un
servicio FastAPI que convierte transcripciones de reunión en estimaciones de
software), esta sesión añade las capas que separan un script de demo de un sistema
preparado para producción:

| Capa | Qué aporta | Dónde vive |
|---|---|---|
| **Wrapper de abstracción + fallback** | Cambiar de proveedor (OpenAI ↔ Anthropic) es configuración, no código. Si uno falla, rota al siguiente automáticamente. | `app/services/llm_wrapper.py` |
| **Cacheo inteligente** | Misma transcripción + mismo contexto = misma estimación → se sirve de caché. 1ª vez: segundos. 2ª vez: instantáneo y coste 0. | `app/cache/llm_cache.py` |
| **Streaming (SSE)** | El usuario ve la estimación "escribiéndose" token a token, no un spinner de 15 s. | endpoint `/estimate/stream` + `st.write_stream` |
| **Observabilidad** | Cada llamada queda registrada con modelo, tokens, coste, latencia, cache_hit y fallback. | `app/logging_config.py` |
| **Interfaz conversacional** | Streamlit como cara visible del estimador (el ejercicio entregable). | `streamlit_app.py` |

## Arquitectura

```
┌─────────────────────────┐        ┌──────────────────────────┐
│  Interfaz Streamlit      │        │  Cliente HTTP externo     │
│  streamlit_app.py        │        │  (curl, otro front…)      │
└───────────┬─────────────┘        └─────────────┬────────────┘
            │ stream_estimation()                 │ POST /api/v1/estimate[/stream]
            │                                     │
            ▼                                     ▼
        ┌───────────────────────────────────────────────┐
        │  Capa de negocio (CAG)                          │
        │  app/services/llm_service.py                    │
        │  - construye system prompt + ejemplos (CAG)     │
        │  - monta conversación + ventana deslizante      │
        └───────────────────────┬─────────────────────────┘
                                 │ wrapper.complete() / .stream()
                                 ▼
        ┌───────────────────────────────────────────────┐
        │  LLM Wrapper  (app/services/llm_wrapper.py)     │
        │  1. Caché (exact-match)  → app/cache/           │
        │  2. Abstracción (LiteLLM)                       │
        │  3. Fallback por orden de proveedores           │
        │  4. Logging estructurado (structlog)            │
        └───────────────┬───────────────┬─────────────────┘
                        ▼               ▼
                   ┌─────────┐     ┌──────────┐
                   │ OpenAI  │     │Anthropic │
                   └─────────┘     └──────────┘
```

La capa de negocio no sabe qué proveedor respondió ni si la respuesta vino de caché:
recibe un resultado normalizado. Esa es toda la gracia de la abstracción.

## Estructura

```
estimador-pro/
├── app/
│   ├── main.py              # App FastAPI: configura logging, monta router, /health
│   ├── config.py            # Settings (Pydantic): proveedores, fallback, caché, logging
│   ├── logging_config.py    # structlog dual (consola en dev, JSON en prod)
│   ├── routers/
│   │   └── estimations.py   # POST /estimate (sync) + POST /estimate/stream (SSE)
│   ├── services/
│   │   ├── llm_wrapper.py    # ⭐ Wrapper: abstracción + fallback + caché + logging
│   │   └── llm_service.py    # Capa de negocio CAG (prompt + conversación)
│   ├── cache/
│   │   └── llm_cache.py      # Caché exact-match (memoria por defecto, Redis opcional)
│   └── context/
│       └── examples.py       # Contexto estático CAG (few-shot)
├── streamlit_app.py          # ⭐ Ejercicio entregable: chat + streaming + sidebar
├── tests/                    # pytest (LLM mockeado: gratis, rápido, sin API key)
├── tutorial_aprendizaje/     # 🎓 Tutorial didáctico de esta sesión + material del curso
├── .env.example
└── pyproject.toml
```

## Requisitos

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Una API key de OpenAI y/o Anthropic con créditos (dos para probar el fallback de verdad)

## Puesta en marcha

```bash
# 1. Dependencias en un entorno aislado (.venv)
uv sync

# 2. Variables de entorno
cp .env.example .env
# edita .env: rellena OPENAI_API_KEY y/o ANTHROPIC_API_KEY

# 3a. API REST
uv run uvicorn app.main:app --reload      # http://localhost:8000/docs

# 3b. Interfaz conversacional (el ejercicio)
uv run streamlit run streamlit_app.py     # http://localhost:8501
```

## Probar la API

```bash
# Síncrono
curl -X POST http://localhost:8000/api/v1/estimate \
  -H "Content-Type: application/json" \
  -d '{"transcription": "El cliente necesita una landing con formulario e integración con HubSpot. Plazo 4 semanas."}'

# Streaming (SSE): verás eventos token a token y un evento done con métricas
curl -N -X POST http://localhost:8000/api/v1/estimate/stream \
  -H "Content-Type: application/json" \
  -d '{"transcription": "El cliente necesita una app de reservas con pagos."}'
```

La respuesta síncrona incluye los metadatos de trazabilidad:

```json
{
  "estimation": "## Estimación: ...",
  "model": "gpt-4o-mini",
  "provider": "openai",
  "cache_hit": false,
  "fallback_used": false,
  "tokens_in": 1240, "tokens_out": 380,
  "cost_usd": 0.00031, "latency_ms": 3120.5,
  "history": [ ... ]
}
```

## Configuración relevante (`.env`)

| Variable | Por defecto | Qué hace |
|---|---|---|
| `PROVIDER_FALLBACK_ORDER` | `openai,anthropic` | Orden en que se intentan los proveedores. |
| `CACHE_ENABLED` | `true` | Activa/desactiva el cacheo. |
| `CACHE_BACKEND` | `memory` | `memory` (sin infra) o `redis`. |
| `CACHE_TTL_SECONDS` | `86400` | Vida de una entrada de caché (24 h). |
| `ENV` | `development` | `development` → logs de consola; `production` → JSON. |
| `LOG_LEVEL` | `INFO` | Nivel mínimo de log. |

## Tests

```bash
uv run python scripts/check_structure.py   # valida el scaffold
uv run pytest -v                            # 19 tests, sin API key (LLM mockeado)
```

## Aprende cómo funciona

Lee el tutorial paso a paso en [`tutorial_aprendizaje/`](tutorial_aprendizaje/README.md):
explica cada capa de esta sesión conectada al código que tienes delante, con retos
prácticos al final de cada lección.
