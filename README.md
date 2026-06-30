# Estimador de software — Proyecto 1 (curso AI Engineering LIDR)

> 📂 **Sobre este repositorio (`ai-engineering-lidr`).** Es el repo **continuo** del curso.
> El proyecto crece sesión a sesión:
> - `main` → última versión acumulada.
> - Una rama por sesión (`sesion-03`, `pre-session-04`, …) y un tag por entrega (`entrega-sesion-NN`).
> - El historial de la Sesión 2 (scaffolding) vive en su repo `01-scaffolding-proyecto-fast-api`.

## Sesión 04 — del chat a interfaz de producto

El estimador deja de ser un **chat** y pasa a ser un **producto**: el usuario ya no escribe el
prompt, rellena un **formulario tipado** y el backend compone el prompt a partir de **templates
Jinja2 versionados**. Así la calidad deja de depender de cómo promptea cada usuario.

- **Formulario, no chat** — el cliente Streamlit envía un `EstimationRequest`
  (`description` + `project_type` + `detail_level` + `output_format`) por HTTP a la API.
- **Prompts como artefactos** — viven en `app/prompts/estimation/v1·v2/{system,user,examples}.j2`,
  cargados por `app/prompts/loader.py`. El endpoint acepta `?prompt_version=` para A/B testing.
- **Bajo el capó (sesión 03):** el wrapper de proveedores con fallback, la caché exact-match,
  el streaming SSE y la observabilidad con structlog siguen funcionando intactos.

> Los temas del directo (salida JSON estructurada, guardrails y cacheo semántico) **no** están en
> esta entrega por decisión del enunciado; viven como teoría en `tutorial_aprendizaje/sesion-04/`.

## Sesión 05 — memoria conversacional + contexto enriquecido (rama `pre-session-05`)

El estimator pasa de **transaccional** a **conversacional**: mantiene memoria entre turnos dentro de
una sesión y acepta adjuntos. (Parte de `session-04-live`, así que incluye además structured outputs +
guardrails + cacheo semántico de la referencia del directo 04.)

- **Sesiones y memoria** (`app/sessions/`): `POST /api/v1/sessions` crea una sesión (UUID) en un
  **store en memoria del proceso**. `ConversationHistory` aplica **ventana deslizante** (`MAX_HISTORY_TURNS=6`
  pares, preserva el system); `ProjectMetadata` guarda los **hechos** del proyecto (nombre, equipo,
  tecnologías, alcance) **separados del historial**, así que sobreviven al truncado.
- **Endpoint multi-turno**: `POST /api/v1/sessions/{id}/estimate` acepta **`multipart/form-data`**
  (`transcript` + `attachments`) y devuelve la estimación estructurada. `GET /api/v1/sessions/{id}`
  expone la memoria (lo usa el sidebar de Streamlit).
- **Adjuntos — Camino B (extracción local)** (`app/attachments/extractor.py`): se extrae el texto con
  **`pypdf`** (PDF) y **`python-docx`** (Word) y se concatena al transcript con separadores
  `--- attachment: <archivo> ---`. *Por qué B y no A (multimodal):* independiente del proveedor, control
  fino sobre qué entra al prompt, y prepara el terreno para el chunking de RAG del módulo 3.
- **`project_metadata` — extractor LLM con Instructor** (`app/sessions/metadata_extractor.py`): tras cada
  turno, una llamada con `instructor.from_litellm(response_model=ProjectMetadata)` extrae los hechos
  nuevos y se **mergean** con los previos sin perderlos. El prompt incluye una constraint anti-alucinación
  (*"nunca nombres una tecnología que no aparezca en la transcripción"*) + un ejemplo de formato.
- **Cliente Streamlit conversacional**: crea la sesión al cargar, permite subir ficheros, muestra la
  memoria en un panel y tiene botón "Nueva conversación".

```bash
uv run uvicorn app.main:app --reload        # API: POST /sessions, POST /sessions/{id}/estimate (/docs)
uv run streamlit run streamlit_app.py       # UI conversacional → http://localhost:8501
uv run pytest -q                            # 83 tests, sin API key (LLM/parsers mockeados)
```

> Lo que **no** entra (se hace en el directo de la sesión 5): memoria con anclas, tier dinámico y
> Actor-Critic-Boss. Teoría y guía en `tutorial_aprendizaje/sesion-05/`.

## Arquitectura

```
┌──────────────────────────┐        ┌──────────────────────────┐
│  Formulario Streamlit     │        │  Cliente HTTP (curl, …)   │
│  streamlit_app.py         │        │                           │
└───────────┬──────────────┘        └─────────────┬─────────────┘
            │  POST /api/v1/estimate (httpx, JSON tipado)        │
            ▼                                       ▼
        ┌───────────────────────────────────────────────┐
        │  Router FastAPI (app/routers/estimations.py)    │
        │  valida EstimationRequest · ?prompt_version     │
        └───────────────────────┬─────────────────────────┘
                                ▼
        ┌───────────────────────────────────────────────┐
        │  Orquestación (app/services/llm_service.py)     │
        │  render_estimation_prompt(req, version)         │
        │     └─ templates Jinja2: app/prompts/…/v1·v2    │
        └───────────────────────┬─────────────────────────┘
                                │  wrapper.complete(system, [user])
                                ▼
        ┌───────────────────────────────────────────────┐
        │  LLM Wrapper (sesión 03): abstracción LiteLLM,  │
        │  fallback, caché exact-match, logging structlog │
        └───────────────┬───────────────┬─────────────────┘
                        ▼               ▼
                   ┌─────────┐     ┌──────────┐
                   │ OpenAI  │     │Anthropic │
                   └─────────┘     └──────────┘
```

Streamlit es **solo presentación**: no llama al LLM, hace POST a la API. Toda la lógica vive en el servicio.

## Estructura

```
ai-engineering-lidr/
├── app/
│   ├── main.py              # App FastAPI: logging, router, /health, /static
│   ├── config.py            # Settings (Pydantic): proveedores, fallback, caché, logging
│   ├── logging_config.py    # structlog dual (consola en dev, JSON en prod)
│   ├── schemas.py           # ⭐ EstimationRequest / EstimationResponse + enums (Pydantic v2)
│   ├── prompts/             # ⭐ Prompts como artefactos versionados
│   │   ├── loader.py        #   render_estimation_prompt(request, version)
│   │   └── estimation/v1·v2/{system,user,examples}.j2
│   ├── routers/
│   │   └── estimations.py   # POST /estimate (+ ?prompt_version) y /estimate/stream (SSE)
│   ├── services/
│   │   ├── llm_service.py    # Orquestación: render del prompt + llamada al wrapper
│   │   ├── llm_wrapper.py    # ⭐ Wrapper: abstracción + fallback + caché + logging (sesión 03)
│   │   └── evaluation.py     # Evaluación estructural (reto sesión 03)
│   └── cache/
│       └── llm_cache.py      # Caché exact-match (memoria por defecto, Redis opcional)
├── streamlit_app.py          # ⭐ Formulario tipado que consume la API (httpx)
├── tests/                    # pytest (LLM mockeado: gratis, rápido, sin API key)
├── tutorial_aprendizaje/     # 🎓 Tutorial (sesión 03 en la raíz + sesion-04/)
├── docker-compose.yml        # Redis opcional para CACHE_BACKEND=redis
├── .env.example
└── pyproject.toml
```

## Requisitos
- Python 3.11+ · [uv](https://docs.astral.sh/uv/)
- Una API key de OpenAI y/o Anthropic (dos para probar el fallback de verdad)

## Puesta en marcha

```bash
uv sync                                    # 1. dependencias en .venv
cp .env.example .env                       # 2. configura: rellena OPENAI_API_KEY y/o ANTHROPIC_API_KEY
uv run uvicorn app.main:app --reload       # 3a. API       → http://localhost:8000/docs
uv run streamlit run streamlit_app.py      # 3b. formulario → http://localhost:8501
```
La interfaz Streamlit necesita el backend levantado (le hace POST). Lee `API_BASE_URL` del entorno
(por defecto `http://localhost:8000`).

## Probar la API

```bash
curl -X POST "http://localhost:8000/api/v1/estimate?prompt_version=v1" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "App móvil de fitness: login, chat en tiempo real y notificaciones push.",
    "project_type": "mobile_app",
    "detail_level": "detailed",
    "output_format": "phases_table"
  }'
```
`project_type` ∈ {mobile_app, web_saas, internal_tool, data_pipeline} ·
`detail_level` ∈ {summary, medium, detailed} ·
`output_format` ∈ {phases_table, line_items, narrative}.

Respuesta (texto libre por ahora + metadatos de trazabilidad):
```json
{
  "text": "| phase | duration_weeks | cost_eur | confidence_pct |\n...",
  "prompt_version": "v1",
  "model": "gpt-4o-mini",
  "cache_hit": false, "fallback_used": false,
  "tokens_in": 491, "tokens_out": 184,
  "cost_usd": 0.00018, "latency_ms": 4350.7
}
```
También hay `POST /api/v1/estimate/stream` (SSE) con el mismo schema de entrada.

## Configuración relevante (`.env`)

| Variable | Por defecto | Qué hace |
|---|---|---|
| `PROVIDER_FALLBACK_ORDER` | `openai,anthropic` | Orden en que se intentan los proveedores. |
| `CACHE_ENABLED` / `CACHE_BACKEND` | `true` / `memory` | Cacheo exact-match; `memory` (sin infra) o `redis`. |
| `CACHE_TTL_SECONDS` | `86400` | Vida de una entrada de caché (24 h). |
| `ENV` / `LOG_LEVEL` | `development` / `INFO` | Logs de consola vs JSON; nivel mínimo. |
| `API_BASE_URL` | `http://localhost:8000` | URL del backend que usa el formulario Streamlit. |

## Tests

```bash
uv run python scripts/check_structure.py   # valida el scaffold
uv run pytest -v                            # 35 tests, sin API key (LLM mockeado)
```
Incluye los tests de template (`tests/prompts/test_estimation_v1.py`): verifican que el prompt
renderizado contiene lo esperado según los parámetros, en milisegundos y sin coste de API.

## Aprende cómo funciona

- **Sesión 04** (esta entrega): [`tutorial_aprendizaje/sesion-04/`](tutorial_aprendizaje/sesion-04/README.md)
  — del chat al producto, prompts versionados, y la teoría del directo.
- **Sesión 03** (bajo el capó): [`tutorial_aprendizaje/`](tutorial_aprendizaje/README.md)
  — wrapper + fallback, caché, streaming, observabilidad, y 4 retos extra.
