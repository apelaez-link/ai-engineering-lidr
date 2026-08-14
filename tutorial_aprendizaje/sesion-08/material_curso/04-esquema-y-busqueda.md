# 04 — Diseño del esquema y búsqueda semántica en pgvector

> Material del curso LIDR · AI Engineering · Sesión 8 (Antonio Pérez). (≈32 min) · La referencia del ejercicio.

El modelo de tablas, los operadores de distancia y el antipatrón silencioso. Es la pieza aplicada:
contiene el esquema SQL que el ejercicio implementa.

## Dos tablas, no una

El reflejo es una sola tabla `chunks` con la metadata del documento repetida en cada fila. Funciona,
pero si un presupuesto produce 17 chunks, duplicas la metadata 17 veces, y actualizar/borrar exige
tocar 17 filas en coherencia. El modelo correcto: **`documents` (1) ──< `chunks` (N)** con
`ON DELETE CASCADE` (borrar el documento borra sus chunks sin lógica aplicativa).

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    id BIGSERIAL PRIMARY KEY,
    source_path TEXT NOT NULL,
    document_type VARCHAR(50) NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Cinco decisiones a defender:
- **Columnas tipadas vs JSONB.** Lo estable y consultado estructuradamente (tipo, fechas) en columnas;
  lo variable/enriquecible (sector, tecnologías, tags) en **JSONB** con índice **GIN**. Ni todo en un
  JSONB (pierde eficiencia) ni una columna nueva por cada campo (cada cambio = migración).
- **Índice GIN sobre `metadata`.** Sin él, `WHERE metadata->>'sector'='fintech'` hace seq scan.
- **`vector(1536)`.** Dimensión de text-embedding-3-small, hardcodeada (cambiarla = reembeder todo).
- **`embedding` nullable.** Permite insertar el chunk y rellenar el embedding después (ingesta async
  futura). Aquí ingestamos chunk+embedding atómicamente.
- **Sin índice vectorial todavía.** El directo mide sin índice, lo crea y vuelve a medir.

## Las tres métricas de distancia

- **Coseno (`<=>`)** — ángulo, ignora magnitud. Estándar para texto de modelos modernos (el
  significado está en la dirección).
- **L2 (`<->`)** — distancia euclídea, sensible a magnitud. Para datos donde la magnitud informa
  (coordenadas, imagen). Rara vez correcta en texto.
- **Inner product negativo (`<#>`)** — producto escalar; negado porque Postgres solo ordena ASC.

**OpenAI normaliza sus embeddings (norma = 1).** Para vectores normalizados, coseno e inner product
**ordenan idéntico**; `<#>` es un pelín más eficiente (ahorra dividir por normas). Aun así usamos
**`<=>` / `vector_cosine_ops`** por dos razones: convención de la literatura RAG (menos fricción al
consultar fuentes) y **robustez** — si algún día se migra a un modelo que **no** normaliza (un
Sentence Transformer local), la query sigue siendo correcta sin sorpresas.

## El antipatrón que destruye el rendimiento sin errores

Un índice HNSW con `vector_cosine_ops` **solo** acelera queries con `<=>`. Si la query usa `<->`, el
índice **no se activa**: Postgres no da error ni warning, cae a **seq scan** recalculando L2 contra
cada fila. Resultados correctos, latencia ×1000.

> **Regla:** el operador de la query (`<=>`/`<->`/`<#>`) debe coincidir con la operator class del
> índice (`vector_cosine_ops`/`vector_l2_ops`/`vector_ip_ops`). Siempre.

En el proyecto: índice con `vector_cosine_ops`, queries con `<=>`. En el directo:
```sql
CREATE INDEX chunks_embedding_idx ON chunks
USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128);

SELECT id, document_id, chunk_type, content, metadata,
       embedding <=> :query_vector AS distance
FROM chunks ORDER BY embedding <=> :query_vector LIMIT :k;
```
(Los dos `<=>` son el mismo operador; el planner calcula la distancia una vez por fila.)

## Verificar con EXPLAIN ANALYZE

`Index Scan using chunks_embedding_idx` = índice activo; `Seq Scan on chunks` = no. Tres causas
frecuentes del seq scan: desalineamiento operador/operator class, filtros muy selectivos (Postgres
prefiere escanear el subconjunto — se resuelve con `hnsw.iterative_scan` de pgvector 0.8), y
estadísticas obsoletas (`ANALYZE chunks`).

> 💡 En nuestro repo, `EXPLAIN ANALYZE` sobre el corpus ingestado (37 chunks) muestra hoy
> **`Seq Scan on chunks`** — el baseline correcto, porque aún no hay índice vectorial.

## La query completa: tres capas en una sentencia atómica

En la práctica quieres búsqueda + filtros relacionales + filtros JSONB + joins, todo con ACID:
```sql
SELECT c.id, c.content, c.embedding <=> :q AS distance, d.metadata->>'sector' AS sector
FROM chunks c JOIN documents d ON d.id = c.document_id
WHERE d.metadata->>'sector' = 'fintech'
  AND d.ingested_at > NOW() - INTERVAL '24 months'
ORDER BY c.embedding <=> :q LIMIT 5;
```
Esto es lo que Pinecone/Qdrant/Weaviate **no** pueden hacer sin coordinar dos sistemas, y la razón
principal de elegir pgvector. (Con filtros muy selectivos, `hnsw.iterative_scan` de pgvector 0.8
expande la búsqueda hasta cumplir el `LIMIT` — se activa y mide en el directo.)
