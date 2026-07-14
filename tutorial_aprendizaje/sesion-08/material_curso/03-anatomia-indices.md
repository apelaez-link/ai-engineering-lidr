# 03 — Anatomía de un índice vectorial: HNSW, IVFFlat y DiskANN

> Material del curso LIDR · AI Engineering · Sesión 8 (Antonio Pérez). (≈40 min) · La más técnica.

Qué pasa exactamente al ejecutar `CREATE INDEX ... USING hnsw` y por qué los parámetros marcan dos
órdenes de magnitud en latencia, recall y memoria. Tres familias, cada una con una estrategia
geométrica distinta.

**Baseline: sin índice = sequential scan.** Calcula la distancia con las filas que sobreviven a los
filtros, ordena, devuelve k. Recall 100%, determinista, **coste lineal**. A partir de decenas de
miles deja de ser "interactivo". Los índices ANN existen para romper esa linealidad.

## IVFFlat — partir el espacio en celdas

Analogía: para los 5 restaurantes más cercanos no comparas con todos, miras el barrio del cliente y
sus vecinos. **Construcción:** k-means sobre los vectores → `lists` centroides (celdas de Voronoi);
cada vector se asigna a su celda (lista invertida). **Consulta:** distancia a los centroides (rápido),
se eligen los `probes` más cercanos y se busca solo en esas celdas.

- `lists ≈ sqrt(rows)` (hasta ~1M); `probes ≈ sqrt(lists)`. Subir `probes` → +recall +latencia.
- **Virtudes:** construcción rápida, memoria moderada, bueno en corpus estáticos.
- **Defectos (por qué se descarta en RAG):** necesita **training** (no se puede crear sobre tabla
  vacía) y **se degrada en silencio con inserciones** (las celdas del k-means original dejan de
  representar la distribución). Para un corpus que crece con cada presupuesto, es riesgo operativo.

## HNSW — grafo multicapa (GPS jerárquico)

Analogía: autopista → nacional → comarcal → calle. Grafo por **capas**: la capa 0 tiene todos los
vectores conectados a sus vecinos por aristas cortas; las capas superiores, subconjuntos cada vez más
pequeños con aristas largas. **Búsqueda de arriba abajo**: avanzas voraz hacia el vecino más cercano
a la query, bajas de capa al agotar mejoras, y en la capa 0 exploras la vecindad final. Complejidad
**logarítmica** con recall alto incluso en alta dimensión (Malkov & Yashunin, 2018).

Tres parámetros en pgvector:
- **`m`** (build-time) — conexiones por nodo/capa. Default **16**, correcto para 1536 dims. Subir a
  32/48: +recall marginal, ×2 memoria y tiempo de construcción. No lo toques sin medir.
- **`ef_construction`** (build-time) — candidatos durante la construcción. Default 64; la comunidad
  2026 recomienda **128** para producción con alta dimensión. Coste: tiempo de construcción.
- **`ef_search`** (query-time, ajustable por sesión/query) — candidatos durante la consulta. Default
  40; subir a 80/100 → +recall, +latencia (curva de recall decreciente). **El que se tunea empíricamente.**

Virtudes (opuestas a IVFFlat): **sin training** (se construye sobre tabla vacía), **absorbe
inserciones** incrementalmente, **recall alto y estable** (>95% con defaults). Coste: **2–5× más
memoria** que IVFFlat. Para el proyecto: **HNSW con `m=16, ef_construction=128, ef_search=40`**.

## DiskANN — el horizonte (más allá de la RAM)

Cuando el índice ya no cabe en RAM. Reemplaza las capas de HNSW por **un grafo plano con aristas
largas estratégicas** (algoritmo Vamana), optimizado para minimizar lecturas de SSD. Una versión
cuantizada vive en RAM; el vector completo se lee del SSD solo para la distancia final → mil millones
de vectores con pocos GB de RAM. En Postgres aparece como **pgvectorscale** (`USING diskann`) o en
Azure. Migras de HNSW a DiskANN cuando el índice no entra en `shared_buffers` o el coste de RAM supera
al de SSD. Para el proyecto estamos órdenes de magnitud por debajo: lo mencionamos como horizonte.

## Tabla de decisión

- **Seq scan (sin índice):** hasta unos miles, muy dinámico, o recall 100% requerido (auditoría). Es
  el baseline contra el que se mide el índice.
- **IVFFlat:** hasta millones, estático, memoria/tiempo de construcción críticos. Evítalo en RAG que crece.
- **HNSW:** el caballo de batalla de casi todo RAG (10⁴–10⁷ vectores, escrituras activas, recall alto).
  **Nuestra elección.**
- **DiskANN:** varios millones donde HNSW aprieta memoria.

## La trampa: operador ↔ operator class

Los tres algoritmos comparten operator classes: `vector_cosine_ops` (`<=>`), `vector_l2_ops` (`<->`),
`vector_ip_ops` (`<#>`). **El operador de la query debe coincidir con la operator class del índice.**
Si construyes con `vector_cosine_ops` y consultas con `<->`, Postgres **ignora el índice en silencio**
(sin error, sin warning) y cae a seq scan: resultados correctos pero latencia 600× peor. Se verifica
con **`EXPLAIN ANALYZE`**: `Index Scan using ...` (bien) vs `Seq Scan on chunks` (índice no usado).
