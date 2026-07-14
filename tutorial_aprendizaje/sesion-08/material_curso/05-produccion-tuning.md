# 05 — Del prototipo a producción: tuning, monitorización y techo de pgvector

> Material del curso LIDR · AI Engineering · Sesión 8 (Antonio Pérez). (≈40 min) · Cierra la sesión.

Las piezas que cruzan la frontera "funciona en la demo" → "funciona dos años en producción". No se
aplican en el ejercicio (el volumen no lo exige), pero son lo que defenderás el día que lleves un RAG
sobre pgvector a producción.

## Sizing de memoria: la regla que gobierna todo

**El 80% del rendimiento de HNSW se decide por una variable: ¿el índice cabe en memoria?** HNSW es un
grafo; una búsqueda salta entre nodos. Si cada salto lee de SSD, lo que en RAM son 5 µs pasa a ~100 µs,
y con ~30 saltos/query la latencia se va a milisegundos solo por I/O (el "long tail" que ningún tuning
de app arregla).

Sizing: cada vector de 1536 dims = **~6 KB** (1M chunks ≈ 6 GB); el índice HNSW ≈ **2–3×** los
vectores (1M ≈ 12–18 GB); + overhead de Postgres. Regla conservadora: **RAM ≥ 1.5× (índice + vectores)**.
Para el proyecto (cientos de miles de chunks, índice de pocos GB) no es problema; el fallo común es
extrapolar el setup del prototipo a un cliente con millones y descubrir en producción que la latencia
de 5 ms es ahora 500 ms porque el índice ya no entra.

Tres parámetros de `postgresql.conf` (los defaults son para una BBDD pequeña, **inadecuados** para RAG):
- `shared_buffers` ≈ **25%** de la RAM.
- `effective_cache_size` ≈ **75%** (pista al planner, no reserva real).
- `work_mem` ≈ 64–256 MB.

## Construcción del índice (parámetros distintos a los de la query)

- **`maintenance_work_mem`** — default 64 MB, **trágico** para HNSW: si el grafo no cabe, la
  construcción cae a disco (10–50× más lenta). Súbelo a varios GB antes de crear un índice grande.
- **`max_parallel_maintenance_workers`** — default 2; con 4 la construcción se acelera notablemente
  (declara `shm_size` suficiente en docker-compose o los workers crashean con OOM crípticos).
- **`CONCURRENTLY`** — obligatorio en producción: sin él, `CREATE INDEX` bloquea la tabla para
  escrituras durante toda la construcción.

```sql
SET maintenance_work_mem = '4GB';
SET max_parallel_maintenance_workers = 4;
CREATE INDEX CONCURRENTLY chunks_embedding_idx ON chunks
USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 128);
```

## halfvec: la mitad del almacenamiento

`halfvec` (pgvector 0.7) guarda cada dimensión en **16 bits** en vez de 32: **la mitad** de espacio y
de tiempo de construcción, con recall **>99%** sobre embeddings normalizados de OpenAI. No es
cuantización agresiva (como la binaria); es una pérdida de precisión indistinguible en la práctica.
**Recomendación 2026: `halfvec` desde el día 1 en producción** (migrar después con millones de
vectores es doloroso). Se indexa con `(embedding::halfvec(1536)) halfvec_cosine_ops` sin cambiar la
columna ni las queries. En el ejercicio no lo usamos (setup mínimo); es lo primero que añadirías en prod.

## Monitorización

- **¿Se usa el índice?** `pg_stat_user_indexes` (`idx_scan`, `last_idx_scan`). `idx_scan = 0` tras un
  tiempo en prod ⇒ casi seguro el antipatrón operador/operator class.
- **¿Cuánto tarda cada query?** `pg_stat_statements` (llamadas, tiempo total/medio/máx). Habilítalo el
  día 1. (Logfire, ya en el stack, correlaciona esto con las trazas de LLM: visión end-to-end.)
- **¿Se degrada el índice?** Bloat (updates/deletes) y estadísticas obsoletas. Ciclo: `VACUUM ANALYZE`
  semanal, `REINDEX INDEX CONCURRENTLY` mensual (o cuando la latencia suba), `ANALYZE` cuando solo
  hagan falta estadísticas.

## Señales objetivas de migración (medibles, no "qué mola")

1. **El índice HNSW ya no cabe en memoria** (ratio índice/RAM > ~70%): latencia p99 impredecible →
   más RAM o migrar a pgvectorscale/DiskANN.
2. **p99 supera el SLO de forma sostenida** (>100–200 ms para RAG interactivo) tras descartar tuning,
   antipatrones y bloat → Qdrant/Milvus dan 2–5× mejor p99.
3. **Necesitas funcionalidades nativas** que pgvector no tiene (multimodal de primera clase, sharding
   multi-región con SLA estricto) **de verdad**, no nice-to-haves.

Si ninguna se cumple, mantener pgvector es casi siempre correcto — la complejidad de un sistema
dedicado tiene su propio coste y solo se justifica cuando las señales lo exigen.

## Cierre del Módulo 3

El arco completo: por qué existen las BBDD vectoriales y cuándo añadirlas · el mercado y por qué
pgvector · IVFFlat/HNSW/DiskANN y sus parámetros · el esquema, las métricas y el antipatrón silencioso
· y qué separa desarrollo de producción. El ejercicio construye la primera mitad (persistir, indexar
esquema, consultar); el directo añade el índice HNSW y mide su impacto, compara métricas de distancia,
y monta búsqueda híbrida. **La sesión 9 empieza el RAG propiamente dicho:** cómo el retriever que
acabas de montar se integra con el generador.
