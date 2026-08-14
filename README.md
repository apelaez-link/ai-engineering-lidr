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

## Sesión 06 — stress test del CAG (rama `pre-session-06`)

Instrumentación y medición: un evento `turn_observed` por turno y un harness autónomo
`evals/stress/` (escenarios multi-turno, adjuntos calibrados, métricas de latencia/coste/memoria)
que mide **dónde se rompe el CAG** antes de adoptar RAG. Deliverable: `evals/stress/REPORT.md` +
`results.csv` (datos reales). Teoría y guía en `tutorial_aprendizaje/sesion-06/`.

## Sesión 07 — embeddings y chunking (rama `pre-session-07`)

Abre la parte práctica del **Módulo 3 (RAG)**: convierte los presupuestos históricos (JSON) en
**vectores**. Módulo nuevo `app/embedding_pipeline/`:

- **Chunker estructural** (`chunker.py`): `JSONStructuralChunker` — **un componente de presupuesto =
  un chunk**, con un **header contextual** del presupuesto padre prepended al texto (proyecto,
  sector, año, tecnología), metadata filtrable, `chunk_id = {budget_id}::{component_id}` y
  `token_count` contado con **tiktoken**.
- **Embedder** (`embedder.py`): `OpenAIEmbedder` sobre `text-embedding-3-small` (1536 dims), llamadas
  en **batches de 100**, reintento exponencial ante `RateLimitError`, coste estimado ($0.02/1M tokens).
- **Endpoint** `POST /embeddings/ingest` (`router.py`): recibe presupuestos, devuelve sus chunks
  vectorizados + estadísticas (total_budgets/chunks/tokens/cost). Registrado bajo `/embeddings`.
- **`similarity.py`** (coseno/dot/euclídea a mano, sin numpy) + **`scripts/compare.py`** (CLI de
  similitud coseno entre dos textos) + **`data/budgets_sample.json`** (15 presupuestos, 37
  componentes) + **`SANITY_CHECK.md`** (3 parejas con embeddings reales).

```bash
uv run uvicorn app.main:app --reload         # POST /embeddings/ingest (ver /docs)
uv run python scripts/compare.py --text-a "OAuth 2.0 auth backend" --text-b "JWT authorization service"
uv run pytest -q                             # 118 tests, sin API key (LLM/embeddings mockeados)
```

> Lo que **no** entra (es el directo / la sesión 8): otras estrategias de chunking, comparativa de
> modelos, retrieval y **persistencia en pgvector**. Teoría y guía en `tutorial_aprendizaje/sesion-07/`.

## Sesión 08 — persistencia vectorial: pgvector + búsqueda semántica (rama `pre-session-08`)

Los vectores de la sesión 07 dejan de vivir en memoria y pasan a **PostgreSQL + pgvector**, con un
endpoint de **búsqueda semántica**. Persistencia con SQLAlchemy 2.0 async + asyncpg, esquema
gestionado con **Alembic**.

- **Esquema (`alembic/versions/0001_initial_schema.py`, modelos en `app/embedding_pipeline/models_db.py`):**
  dos tablas `documents` (1) ──< `chunks` (N) con `ON DELETE CASCADE`, extensión `vector`, índices
  B-tree + **GIN** sobre `metadata`. `embedding vector(1536)`. **Sin índice vectorial** todavía.
- **`POST /embeddings/ingest`** (refactorizado): recibe `{source_path, document_type, content}`,
  trocea el presupuesto, embebe sus chunks y **persiste document + chunks en una transacción**.
  Devuelve `{document_id, chunks_created, embedding_dimension, ingestion_time_ms}`. **409** si el
  `source_path` ya existe (idempotencia).
- **`POST /search`** (nuevo): embebe la query y devuelve los `k` chunks más cercanos por **distancia
  coseno** (`<=>`), alineada con la operator class que tendrá el índice HNSW del directo.
- **`query_examples.py`** (reemplaza a `compare.py`): 5 consultas contra `/search`. Salida real en
  **`output_examples.txt`**.

### Decisiones de esquema (justificación)

- **Dos tablas, no una.** Un presupuesto produce N chunks; una sola tabla duplicaría la metadata del
  documento en cada chunk y perdería integridad referencial. Con `documents` ──< `chunks` y
  `ON DELETE CASCADE`, borrar un presupuesto borra sus chunks sin lógica aplicativa.
- **`metadata` en JSONB, no columnas.** Lo estable y consultado de forma estructurada (tipo de
  documento/chunk, fechas) va en columnas tipadas; lo variable/enriquecible (sector, tecnologías,
  chunk_id, token_count) va en JSONB con índice **GIN** — flexible sin migrar el esquema cada vez.
- **`cosine_distance` (`<=>`), no L2 ni inner product.** Los embeddings de OpenAI están normalizados,
  así que coseno e inner product ordenan igual; usamos coseno por convención de la literatura RAG y
  para que, al crear el índice HNSW en el directo con `vector_cosine_ops`, **operador e índice queden
  alineados** (un desalineamiento haría que Postgres ignore el índice en silencio y caiga a seq scan).
- **Sin índice vectorial todavía.** Deliberado: el directo mide la latencia del `/search` **sin**
  índice (sequential scan), crea el índice HNSW y vuelve a medir. `EXPLAIN ANALYZE` sobre nuestro
  corpus confirma hoy `Seq Scan on chunks` — el baseline correcto.

```bash
docker compose up -d postgres                # Postgres+pgvector en localhost:5433 (5432 suele estar ocupado)
uv run alembic upgrade head                  # crea extensión + tablas + índices (no el vectorial)
uv run uvicorn app.main:app --reload         # POST /embeddings/ingest y POST /search (ver /docs)
uv run python query_examples.py              # 5 consultas de ejemplo (con el corpus ingestado)
uv run pytest -q                             # 123 tests (repo test se salta si no hay Postgres)
```

> Lo que **no** entra (es el directo): índice HNSW/IVFFlat y su tuning, filtros por metadata en la
> query, búsqueda híbrida (full-text + vector). Teoría y guía en `tutorial_aprendizaje/sesion-08/`.

## Sesión 09 — diagnóstico arquitectónico del RAG actual (rama `session-09/pre-work`)

Sesión de **razonamiento**, no de código: un diagnóstico ([`arquitectura-actual.md`](arquitectura-actual.md))
del sistema de recuperación actual sobre una traza real de una transcripción ambigua —los 4 estadios
del RAG (Query → Retrieval → Augmentation → Generation), 5 fallos concretos y un diagrama de evolución.
La conclusión que arrastra a la sesión 10: **la recuperación domina**.

## Sesión 10 — recuperación avanzada: híbrida + reranking (rama `session-10/pre-work`)

Cierra lo que la sesión 08 dejaba para el futuro: **búsqueda híbrida** (full-text + vector) y
**reranking**. Pero el foco real es **medir si valen la pena**.

- **Full-text** (`alembic/versions/0002_fulltext_tsvector.py`): columna **generada** `content_tsv`
  (`tsvector`, config `english`) + índice **GIN** sobre `chunks`. Búsqueda léxica en
  `repository.lexical_search_chunks` con matching **OR** (`_or_tsquery`) y ranking `ts_rank_cd`.
- **Híbrida** (`app/embedding_pipeline/hybrid.py`): fusiona la lista vectorial y la léxica con
  **Reciprocal Rank Fusion** (RRF, `k=60`). `reciprocal_rank_fusion()` es pura y testeable.
- **Reranking** (`app/embedding_pipeline/reranker.py`): `CrossEncoderReranker` (cross-encoder
  `ms-marco-MiniLM`, carga perezosa, *scorer* inyectable) con patrón **recall-then-rerank** (top-15 → top-5).
- **`POST /search`** ahora acepta `mode: vector|hybrid` y `rerank: true|false` — **4 configs sin tocar código**.
- **Medición** (`evals/retrieval/`): golden set de 5 consultas anotadas + **precisión@5** + latencia,
  sobre las 4 configuraciones (A/B/C/D). Deliverable: [`evals/retrieval/REPORT.md`](evals/retrieval/REPORT.md)
  + `results.csv` (datos reales).

**Resultado (corpus de 37 chunks):** la vectorial sola (A) ya está en el techo (**P@5=0.92 @ 1.7 ms**);
la híbrida sin rerank **empeora** (0.80, mete ruido léxico); el rerank la rescata (0.92) pero **cuesta
~14× latencia** (24 ms) sin ganar precisión sobre A. **Conclusión: en este corpus gana A**; híbrida y
rerank empezarán a pagar cuando el corpus crezca y se ensucie. *Medir antes de adoptar.* Guía completa
con la tabla y la interpretación en `tutorial_aprendizaje/sesion-10/`.

```bash
docker compose up -d postgres && uv run alembic upgrade head    # incluye la migración 0002 (tsvector + GIN)
DATABASE_URL=…@localhost:5433/estimator uv run python -m evals.retrieval.run   # mide A/B/C/D (real)
uv run pytest -q                                                # 142 tests (los de BBDD se saltan sin Postgres)
```

> **Nota (Opción B):** el enunciado asumía el pipeline RAG de la sesión 9-live y un cross-encoder ya
> provisto, y sugería un fork del repo del profesor. Lo hicimos sobre **nuestro repo continuo** y
> **nuestros datos** (desviación consciente); detalle en `tutorial_aprendizaje/sesion-10/README.md` §6.

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
