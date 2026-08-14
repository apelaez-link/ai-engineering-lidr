# 🎓 Tutorial — Sesión 08: Bases de datos vectoriales (pgvector)

Cierra la base del **Módulo 3 (RAG)**. Los vectores de la sesión 7 dejan de vivir en memoria y pasan
a **PostgreSQL + pgvector**, con un endpoint de **búsqueda semántica**.

> 🔑 El ejercicio es **pre-sesión** (rama `pre-session-08`, enlace por mail a `george@lidr.co`). El
> directo añade el índice HNSW, lo mide, y monta búsqueda híbrida sobre este código.

## Qué construimos (el entregable)

| Pieza | Qué | En el repo |
|-------|-----|-----------|
| Capa DB | engine async + `get_session` (SQLAlchemy 2.0 + asyncpg) | [`app/db.py`](../../app/db.py) |
| Modelos ORM | `Document` ──< `Chunk` con `Vector(1536)` | [`models_db.py`](../../app/embedding_pipeline/models_db.py) |
| Repository | `persist_document` / `search_chunks` / `get_document_id_by_source` (async) | [`repository.py`](../../app/embedding_pipeline/repository.py) |
| Endpoints | `POST /embeddings/ingest` (persiste, 409 duplicado) + `POST /search` (coseno top-k) | [`router.py`](../../app/embedding_pipeline/router.py) |
| Migración | extensión + `documents` + `chunks` + índices (sin vectorial) | [`alembic/versions/0001_initial_schema.py`](../../alembic/versions/0001_initial_schema.py) |
| Infra | Postgres `pgvector/pgvector:pg16` | [`docker-compose.yml`](../../docker-compose.yml) |
| Validación | 5 consultas → salida real | [`query_examples.py`](../../query_examples.py) · [`output_examples.txt`](../../output_examples.txt) |

Parte de **`pre-session-07`** (incluye chunker + embedder + similarity). **123 tests** (118 previos +
5 nuevos; el test de repositorio corre contra Postgres real y se salta si no hay).

## ⚠️ Puerto 5433 (no 5432) — a propósito

En esta máquina el **5432 ya lo ocupa otro Postgres** (el del proyecto de microservicios). Para no
tocarlo, nuestro `docker-compose` publica el Postgres del ejercicio en **`localhost:5433`**, y
`DATABASE_URL` / `config.database_url` apuntan ahí. Si tu 5432 estuviera libre, cambia el mapeo.

## Cómo ejecutarlo (paso a paso, para correrlo y entenderlo)

```bash
cd ~/Documents/AIEngineering/ai-engineering-lidr-s08   # o tu checkout de pre-session-08
uv sync

# 1) Postgres + pgvector en 5433
docker compose up -d postgres
docker exec estimador-postgres psql -U estimator -d estimator -c "SELECT version();"

# 2) Esquema (extensión + tablas + índices; NO el índice vectorial)
uv run alembic upgrade head
docker exec estimador-postgres psql -U estimator -d estimator -c "\dt"

# 3) Servidor (necesita OPENAI_API_KEY en .env)
uv run uvicorn app.main:app --reload            # /docs: POST /embeddings/ingest y POST /search

# 4) Ingesta del corpus (los 15 presupuestos de data/budgets_sample.json), uno por documento:
#    (bucle httpx; ver la sección "Ingesta" más abajo o el propio README raíz)

# 5) Las 5 consultas de ejemplo -> output_examples.txt
uv run python query_examples.py                  # con el corpus ya ingestado
uv run python query_examples.py > output_examples.txt

# tests (el de repositorio se salta si no hay Postgres del proyecto en 5433)
uv run pytest -q                                 # 123 tests
```

Ingesta rápida del corpus (una llamada por presupuesto):
```python
import json, httpx
c = httpx.Client(base_url="http://localhost:8000", timeout=60)
for b in json.load(open("data/budgets_sample.json")):
    c.post("/embeddings/ingest", json={
        "source_path": f"data/budgets/{b['budget_id']}.json",
        "document_type": "historical_budget", "content": b,
    })
```

## Las decisiones que defenderías en el directo

- **Dos tablas, no una** — `documents` ──< `chunks` con `ON DELETE CASCADE`; evita duplicar la
  metadata del documento en cada chunk y da integridad referencial.
- **`metadata` en JSONB + índice GIN** — estable en columnas tipadas, variable en JSONB sin migrar el
  esquema cada vez.
- **`cosine_distance` (`<=>`)** — embeddings de OpenAI normalizados ⇒ coseno e inner product ordenan
  igual; elegimos coseno por convención y para **alinear con la operator class** del índice HNSW del
  directo (un desalineamiento haría que Postgres ignore el índice en silencio).
- **Sin índice vectorial** — deliberado; `EXPLAIN ANALYZE` confirma `Seq Scan on chunks` hoy (baseline).
- **Idempotencia (409)** — no re-ingestar el mismo `source_path`.
- **Transacción única en la ingesta** — un fallo del embedder no deja `documents` huérfanos.
- **`repository` separado del router** — router testeable sin BBDD (repo parcheado); repo testeable
  contra Postgres real (skipif sin BBDD).

## Salida real (output_examples.txt)

Generado con embeddings reales contra el corpus (15 presupuestos, 37 chunks). La estructura confirma
que discrimina: la consulta fintech+JWT recupera los chunks de OAuth/PSD2 (distancias ~0.41); la
consulta de dominio ajeno ("restaurant reservations") deja todas las distancias por encima de ~0.60;
la de microservicios+Kubernetes (nada parecido en el corpus) no baja de ~0.67. Sin índice, cada
`/search` es un sequential scan — a este volumen, sub-milisegundo.

## Comparación con el enunciado

- App en local (`uv`) + solo Postgres en Docker (camino más simple para ejecutar/entender), en vez de
  containerizar la app; el enunciado plantea un `ai_service` containerizado. Puerto 5433 en vez de 5432.
- Rama `pre-session-08` (convención del repo continuo), no `session-08/pre-exercise`.
- Añadimos tests mockeados + un test de repositorio real (skipif) aunque el enunciado no los exija.

## Material del curso (teoría fiel)
[00 intro](material_curso/00-intro.md) ·
[01 por qué BBDD vectoriales](material_curso/01-por-que-bbdd-vectoriales.md) ·
[02 mercado 2026](material_curso/02-mercado-2026.md) ·
[03 anatomía de índices](material_curso/03-anatomia-indices.md) ·
[04 esquema y búsqueda](material_curso/04-esquema-y-busqueda.md) ·
[05 producción y tuning](material_curso/05-produccion-tuning.md) ·
[✍️ EJERCICIO](material_curso/EJERCICIO.md).

## Siguiente (sesión 9)
Empieza el **RAG propiamente dicho**: cómo el retriever que acabamos de montar se integra con el
generador, estrategias de recuperación más allá del top-k, y cómo anclar la respuesta del LLM en los
chunks recuperados.
