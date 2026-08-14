# ✍️ Ejercicio (pre-sesión): Pipeline mínimo de embeddings y chunking

> Material del curso LIDR · AI Engineering · Sesión 7 (Antonio Pérez). Enunciado fiel.

## Objetivo

Construir dentro del servicio IA un **pipeline funcional mínimo** que reciba presupuestos históricos
en JSON, los parta en chunks respetando la estructura, genere embeddings con OpenAI y devuelva los
vectores listos para uso posterior. Cierra con un CLI que verifica que los embeddings discriminan,
comparando la similitud entre tres parejas de textos. Al terminar: pipeline end-to-end ejecutable +
sanity check. El directo partirá de aquí para introducir otras estrategias de chunking.

## Contexto

La sesión 6 dejó los presupuestos limpios y normalizados en JSON. Aquí damos el primer paso hacia la
búsqueda semántica: convertirlos en vectores. **No se persiste todavía** en ninguna BBDD vectorial
(eso es la sesión 8 con PostgreSQL + pgvector); los vectores se generan en memoria y se devuelven por
HTTP. Módulo nuevo: `embedding_pipeline/` dentro del servicio IA. Interfaz y backend de negocio no se tocan.

## Entra / No entra

**Entra:** chunker estructural para presupuestos JSON (1 componente = 1 chunk); embedder que invoca
`text-embedding-3-small`; endpoint `POST /embeddings/ingest`; CLI `compare.py` (similitud coseno);
validación con 3 parejas.

**No entra (es del directo):** otras estrategias de chunking (recursive, semantic, hierarchical, late,
contextual…); comparativa de modelos; enriquecimiento con LLM; persistencia vectorial; retrieval;
métricas formales (recall@k, NDCG); cambios en la interfaz o el backend.

## Datos

`data/budgets_sample.json`: 15 presupuestos normalizados (sectores variados: fintech, e-commerce,
healthcare, industrial). Esquema por presupuesto: `budget_id`, `client_metadata` {name, sector,
country}, `project_summary`, `main_technology`, `year`, `total_estimated_hours`, `components[]`. Cada
componente: `component_id`, `name`, `description`, `tech_stack[]`, `estimated_hours`, `complexity`,
`dependencies[]`. (Se puede traer el dataset propio de la sesión 6 si respeta el esquema.)

## Pasos

1. **Estructura + deps.** Árbol `embedding_pipeline/` (`__init__`, `chunker`, `embedder`, `schemas`,
   `router`) + `scripts/compare.py` + `data/`. Añadir `openai>=1.0.0` y `tiktoken>=0.7.0`. **NO añadir
   numpy/scikit-learn**: la similitud coseno se calcula a mano con la biblioteca estándar.
2. **Modelos Pydantic v2** (`schemas.py`): `BudgetComponent`, `Budget`, `Chunk` (chunk_id, text,
   metadata, token_count), `EmbeddedChunk` (+ embedding), `IngestRequest` (budgets[]), `IngestResponse`
   (chunks[] + stats: total_budgets, total_chunks, total_tokens, estimated_cost_usd).
3. **Chunker estructural** (`chunker.py`): `JSONStructuralChunker.chunk(budgets) -> list[Chunk]`. Un
   componente = un chunk; `text` = header contextual del padre + detalles; metadata filtrable;
   `chunk_id = {budget_id}::{component_id}`; `token_count` con tiktoken. Sin overlap ni splitting de
   descripciones largas.
4. **Embedder** (`embedder.py`): `OpenAIEmbedder.embed_one(text)` y `embed_many(chunks)`.
   `text-embedding-3-small` dim por defecto (1536). Batches (100/llamada). Retry ante `RateLimitError`
   (3 intentos: 1s/2s/4s). structlog por batch (chunks, tokens, latencia). Coste: **$0.02/1M tokens de
   entrada** como constante de módulo.
5. **Endpoint** (`router.py`): `POST /embeddings/ingest` (IngestRequest → IngestResponse). 200 / 422
   (validación) / 500 (error de la API, mensaje genérico + detalle en logs). Registrar en `main.py`
   bajo `/embeddings`. Verificar en `/docs`.
6. **CLI** (`scripts/compare.py`): `--text-a`/`--text-b` → embebe ambos → coseno **a mano**. Ejecutable
   dentro del contenedor (`docker compose exec`) y fuera (`uv run`).
7. **Validación (3 parejas)** → `embedding_pipeline/SANITY_CHECK.md`:
   - **A** (cercanos, se espera > 0.6): "OAuth 2.0 authentication backend with JWT tokens for fintech mobile app" vs "Authorization service using JSON Web Tokens for a banking application".
   - **B** (no relacionados, se espera < 0.4): A1 vs "Database migration from MySQL to PostgreSQL with zero downtime".
   - **C** (genéricos/ambiguos, sin expectativa): "Backend services" vs "API development".
   Incluir los 3 valores + comentario (3-5 líneas) sobre si encajan con la intuición y qué llama la atención.

## Entregable

Rama con: `embedding_pipeline/` completo, `scripts/compare.py`, endpoint registrado y accesible en
`/docs`, `SANITY_CHECK.md`, README actualizado (cómo invocar el endpoint y `compare.py` dentro/fuera del
contenedor), `pyproject.toml` con las deps nuevas. **Tests no son requisito** (diferidos a otra sesión);
si escribes alguno, perfecto.

> El enunciado sugiere la rama `session-07/pre-exercise`. Nosotros mantenemos la convención del repo
> continuo: rama **`pre-session-07`** + tag `entrega-sesion-07`.

## Entrega

Enlace a la rama por mail a **george@lidr.co** hasta **2 días antes** del directo (plazo estricto:
necesitan margen para preparar la sesión sobre los problemas reales encontrados). Rama accesible
(pública o con permisos para el revisor).
