# ✍️ Ejercicio (pre-sesión): Migración a pgvector + endpoint de búsqueda

> Material del curso LIDR · AI Engineering · Sesión 8 (Antonio Pérez). Enunciado fiel.

## Objetivo

Persistir el pipeline de la sesión 7 en **PostgreSQL + pgvector** y exponer un endpoint de **búsqueda
semántica** sobre los presupuestos históricos. Al terminar, el servicio IA debe: levantar un Postgres
con pgvector como dependencia declarada; tener un esquema relacional propio (`documents`, `chunks`)
gestionado con migraciones **Alembic**; persistir cada presupuesto como un `document` con sus `chunks`
(cada uno con su embedding) en **una transacción**; y resolver una query semántica vía SQL devolviendo
los `k` chunks más cercanos por **distancia coseno**.

## Lo que NO entra (es el directo)

Índices vectoriales (HNSW/IVFFlat) — el **sequential scan** es el baseline contra el que se mide el
índice · filtros por metadata (`WHERE metadata->>'sector'='fintech'`) · búsqueda híbrida (full-text +
vector) · tuning (`shared_buffers`, `ef_search`…). *"Resiste la tentación de ir más allá: la disciplina
de scoping es parte del ejercicio."*

## Stack

`sqlalchemy>=2.0` · `asyncpg>=0.29` · `pgvector>=0.3` · `alembic>=1.13`.

## Pasos

1. **Postgres con pgvector en docker-compose** (`pgvector/pgvector:pg16`, DB/usuario/pass `estimator`,
   healthcheck). Verificar `SELECT version();` antes de seguir.
2. **Alembic async** (`alembic init -t async`). Configurar `env.py` para tomar `DATABASE_URL` del
   entorno y **registrar el tipo `vector`** (`connection.dialect.ischema_names["vector"] = Vector`).
3. **Esquema (migración 0001):** `CREATE EXTENSION vector` + tablas `documents` y `chunks`
   (columnas exactas del enunciado; `embedding vector(1536)` nullable; FK `ON DELETE CASCADE`) +
   índices `ix_documents_source_path`, `ix_chunks_document_id`, `ix_chunks_chunk_type` y
   `ix_chunks_metadata_gin` (**GIN**). **Sin índice vectorial.**
4. **Refactor `POST /embeddings/ingest`:** de devolver vectores a **persistir en una transacción**.
   Request `{source_path, document_type, content}`. Response 200 `{document_id, chunks_created,
   embedding_dimension, ingestion_time_ms}`. **409** `{detail, document_id}` si el `source_path` ya
   existe. Secuencia: comprobar duplicado → crear `documents` → chunker → embedder por lotes →
   `add_all` de `chunks` → commit.
5. **Nuevo `POST /search`:** request `{query, k}`. Embebe la query con el **mismo modelo** que la
   ingesta y ejecuta la query con `Chunk.embedding.cosine_distance(query_vector)` ordenando por esa
   distancia, `LIMIT k`. Response con `search_time_ms` y los resultados (chunk_id, document_id,
   chunk_type, content, distance, metadata). Usar **`cosine_distance` (`<=>`)** para alinear con la
   operator class del índice del directo.
6. **`query_examples.py`** (reemplaza a `compare.py`): 5 consultas que ejercitan el corpus desde
   ángulos distintos → componente directo (sanity check), reformulación semántica, dominio distinto,
   consulta ambigua, consulta muy específica. Top-5 por consulta (chunk_id, distance 4 dec, chunk_type,
   ~120 chars de content). Guardar la salida en **`output_examples.txt`**.

## Entregable

`docker-compose.yml` con postgres · migración Alembic · `POST /embeddings/ingest` refactorizado (con
409) · `POST /search` funcional · `query_examples.py` ejecutable · `output_examples.txt` con la salida
real · sección de README (máx. 1 pág.) justificando: **(a)** dos tablas y no una, **(b)** metadata como
JSONB, **(c)** `cosine_distance` y no L2/inner product, **(d)** por qué deliberadamente no hay índice
vectorial todavía.

> El enunciado no exige tests. Nosotros mantenemos la convención del repo continuo: rama
> **`pre-session-08`** + tag `entrega-sesion-08`.

## Entrega

Enlace a la rama por mail a **george@lidr.co** (plazo estricto: 2 días antes del directo). Rama
accesible (pública o con permisos para el revisor).
