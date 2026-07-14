# 00 — Bases de datos vectoriales (introducción)

> Material del curso LIDR · AI Engineering · Sesión 8 (Antonio Pérez). Cierra la base del **Módulo 3 (RAG)**.

La sesión 7 dejó un pipeline que convierte presupuestos en vectores… **en memoria del proceso**. Si
reinicias, se pierden; si escalas a dos réplicas, divergen; buscar "el más parecido" obliga a
recorrer todos los vectores a mano. La sesión 8 cruza la frontera del prototipo: **persistir** los
vectores en PostgreSQL + **pgvector** y exponer **búsqueda semántica**.

Las 5 lecciones forman el arco completo; la 4ª es la referencia directa del ejercicio:

| # | Lección | Idea-ancla |
|---|---------|-----------|
| 1 | [Por qué existen las BBDD vectoriales](01-por-que-bbdd-vectoriales.md) | Búsqueda ANN ≠ búsqueda exacta; 4 propiedades que un array no da; cuándo (y cuándo no) añadirla. |
| 2 | [Estado del mercado 2026](02-mercado-2026.md) | 4 ejes de decisión; pgvector/Qdrant/Weaviate/Milvus/Pinecone; **por qué pgvector**. |
| 3 | [Anatomía de un índice vectorial](03-anatomia-indices.md) | IVFFlat vs HNSW vs DiskANN; parámetros (m, ef_*); la trampa operador↔operator class. |
| 4 | [Diseño del esquema y búsqueda](04-esquema-y-busqueda.md) | Dos tablas, JSONB, coseno con vectores normalizados. **Es el esquema del ejercicio.** |
| 5 | [Del prototipo a producción](05-produccion-tuning.md) | Sizing de memoria, construcción del índice, halfvec, monitorización, señales de migración. |

## El ejercicio (pre-sesión, entregable)

Persistir el pipeline de la sesión 7 en **PostgreSQL + pgvector** y exponer **búsqueda semántica**:
esquema con Alembic (`documents` ──< `chunks`), `POST /embeddings/ingest` refactorizado para
persistir en una transacción (409 si duplicado), `POST /search` (top-k por distancia coseno), y un
`query_examples.py` con 5 consultas → `output_examples.txt`. *Ver [EJERCICIO.md](EJERCICIO.md).*

> 🔑 **Alcance deliberado:** NO se crea el índice vectorial (HNSW/IVFFlat) — el directo lo añade y
> mide su impacto contra el **sequential scan** de ahora. Tampoco filtros por metadata, búsqueda
> híbrida ni tuning: todo eso es el directo.

## Lo que construimos (mapa)

`app/db.py` (engine async + `get_session`), `app/embedding_pipeline/models_db.py` (ORM
Document/Chunk con `Vector(1536)`), `repository.py` (persistencia + búsqueda async), `router.py`
(ingest persistente + `/search`), `alembic/` (migración 0001), `docker-compose.yml` (+Postgres),
`query_examples.py`, `output_examples.txt`. **123 tests** (118 previos + 5 nuevos; el test de
repositorio corre contra Postgres real y se salta si no hay).
