# Sesión 10 — Recuperación avanzada: búsqueda híbrida + reranking

> Rama `session-10/pre-work`. Módulo 4 (RAG). Construimos las dos técnicas que mejoran
> la **recuperación** —búsqueda híbrida (vectorial + full-text con RRF) y reranking con
> cross-encoder— y, sobre todo, **medimos** si de verdad valen la pena en *nuestro*
> corpus (precisión@5 + latencia). El resultado es un ejemplo de manual de por qué en
> ingeniería **se mide antes de adoptar**.

---

## 0. De dónde venimos y qué añade esta sesión

En la sesión 9 vimos que en un RAG **la recuperación manda**: si el `retrieval` no trae
los presupuestos correctos, ni el mejor prompt ni el mejor modelo arreglan la
estimación. Así que esta sesión ataca justo esa etapa, con dos palancas:

1. **Búsqueda híbrida**: combinar la búsqueda **semántica** (embeddings, coseno — la de
   la sesión 8) con la **léxica** (full-text de Postgres, palabras clave exactas),
   fusionando ambos rankings.
2. **Reranking**: recuperar muchos candidatos (alto *recall*) y reordenarlos con un
   modelo caro y preciso (**cross-encoder**), quedándote con los mejores.

Y una tercera pata que es la verdadera lección: **medir** las dos con un *golden set* y
decidir con datos, no con fe.

> **Alcance (lo que pide el enunciado):** solo híbrida + reranking. NO query expansion,
> NI multi-index routing, NI filtrado por metadatos.

---

## 1. Búsqueda full-text (la mitad léxica)

La búsqueda vectorial captura **significado** ("banca móvil" ≈ "mobile banking"), pero
diluye los **términos exactos y raros**: siglas, nombres propios, IDs, tecnologías
(`OAuth 2.0`, `PSD2`, `pgvector`). Ahí brilla el full-text: casa la palabra literal.

En Postgres eso es una columna `tsvector`. La añadimos en la migración
[`0002_fulltext_tsvector.py`](../../alembic/versions/0002_fulltext_tsvector.py):

```sql
ALTER TABLE chunks
  ADD COLUMN content_tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
CREATE INDEX ix_chunks_content_tsv ON chunks USING gin (content_tsv);
```

Tres decisiones:

- **Columna GENERADA** (no un trigger ni rellenarla a mano): Postgres la recalcula sola
  cuando cambia `content`, así que nunca se desincroniza. Requiere que la expresión sea
  `IMMUTABLE`, y `to_tsvector('english', content)` con la config puesta como constante
  lo es.
- **Índice GIN**: es el índice pensado para `tsvector`; hace que el match `@@` sea rápido.
- **Config `english`, no `spanish`**: el enunciado usa español porque su dataset lo está;
  **nuestro corpus está en inglés** (`Project: ...`, `Component: ...`). La config debe
  casar con el idioma para que el *stemming* y las *stop-words* funcionen.

### El bug que casi hace inútil la híbrida: AND vs OR

La primera versión usaba `plainto_tsquery`, que une los términos con **AND**:
`'mobile' & 'banking' & 'oauth' & ...`. Una consulta larga en lenguaje natural solo
casaría con un chunk que contenga **todas** las palabras — en la práctica, **ninguno**,
y la búsqueda léxica devolvía **vacío** (lo detectamos midiendo: la híbrida daba
exactamente lo mismo que la vectorial). El arreglo es convertir la consulta a **OR**
(que casen los chunks con *cualquier* término), reutilizando el análisis léxico de
Postgres (ver `_or_tsquery` en [`repository.py`](../../app/embedding_pipeline/repository.py)).
Moraleja: **la medición cazó un bug que la lectura del código no**.

---

## 2. Búsqueda híbrida con Reciprocal Rank Fusion (RRF)

Tenemos dos listas ordenadas: la vectorial (por distancia coseno, menor = mejor) y la
léxica (por `ts_rank_cd`, mayor = mejor). **¿Cómo se combinan si viven en escalas
distintas e incomparables?** No se pueden sumar los scores. La respuesta es **RRF**:

```
RRF(doc) = Σ_listas  1 / (k + posición_en_esa_lista)      (posición 1-based, k=60)
```

RRF **tira los scores a la basura** y se queda solo con la **posición**. Un documento
que sale arriba en *cualquiera* de las dos búsquedas puntúa bien; si sale arriba en
*ambas*, mejor aún. Es robusto, no necesita calibrar nada, y la constante `k=60`
(convención de Cormack et al.) amortigua el peso de las primeras posiciones.

Implementado en [`hybrid.py`](../../app/embedding_pipeline/hybrid.py):
`reciprocal_rank_fusion()` es una función **pura** (se testea con listas a mano) y
`hybrid_search()` orquesta las dos consultas reales y las fusiona.

---

## 3. Reranking con cross-encoder (recall-then-rerank)

La recuperación (vectorial o híbrida) usa **bi-encoders**: embebe consulta y documento
por separado y compara sus vectores. Es rápido pero **grueso**. Un **cross-encoder**
mira consulta y documento **juntos** en una sola pasada del modelo y da un score de
relevancia mucho más fino — pero es **caro** (una inferencia por par), así que no puede
correr sobre toda la colección. Se usa en dos fases, el patrón **recall-then-rerank**:

```
1) recuperación amplia y barata   ->  top-N candidatos   (N grande)
2) reordenación fina y cara        ->  top-k final        (k pequeño)
```

En [`reranker.py`](../../app/embedding_pipeline/reranker.py), `CrossEncoderReranker`
envuelve `sentence_transformers.CrossEncoder` (modelo `ms-marco-MiniLM-L-6-v2`, inglés).
El modelo se carga **perezosamente** (se descarga en la primera llamada, no al importar)
y el *scorer* es **inyectable**, para poder testear la lógica de reordenación sin torch.

Todo es **activable sin tocar código**: por config (`RERANK_ENABLED`) o por petición
(`POST /search` acepta `mode: vector|hybrid` y `rerank: true|false`).

---

## 4. La medición: golden set, 4 configuraciones, precisión@5 + latencia

Las dos técnicas prometen mejorar la recuperación. **¿Lo hacen? ¿Compensa el coste?**
Para responder con datos montamos un experimento tipo *ablation* 2×2:

**Dos palancas independientes** → **4 configuraciones**:

| Config | Recuperación | Rerank | Pipeline |
|--------|--------------|--------|----------|
| **A** | Vectorial | No | embed → coseno → top-5 |
| **B** | Híbrida (RRF) | No | (vectorial + full-text) → RRF → top-5 |
| **C** | Vectorial | Sí | coseno → top-15 → cross-encoder → top-5 |
| **D** | Híbrida (RRF) | Sí | (vectorial + full-text) → RRF → top-15 → cross-encoder → top-5 |

**Golden set** ([`golden_set.py`](../../evals/retrieval/golden_set.py)): 5 consultas
—descripciones de proyectos a estimar— anotadas a mano con los presupuestos relevantes.
Elegidas para ejercitar distintos ejes: señal léxica exacta (Q3: `OAuth`/`PSD2`),
paráfrasis semántica (Q2: telemedicina), concepto ambiguo entre dominios (Q4: "tiempo
real"), concepto puente (Q5: "inventario").

**Métrica** ([`metrics.py`](../../evals/retrieval/metrics.py)): **precisión@5** =
relevantes entre los 5 primeros / 5. La relevancia se anota a nivel de **presupuesto**
(`budget_id`) y se propaga a sus chunks.

> **Nota de pool (importante):** el patrón recall-then-rerank recupera un pool ancho
> (el enunciado sugiere 50→5, pensado para un corpus grande). Nuestro corpus tiene **37
> chunks**: con pool=50 el recall devolvería *todo* y las configs C y D reordenarían el
> mismo conjunto (resultado idéntico), anulando la comparación. Por eso medimos con
> **pool=15** (< 37): así la etapa de recall filtra de verdad y vectorial-vs-híbrida
> alimentan candidatos distintos al reranker. Es una adaptación al tamaño del corpus, no
> un cambio de la técnica.

### Resultados reales

Ejecutado por [`evals/retrieval/run.py`](../../evals/retrieval/run.py) contra Postgres
real (37 chunks), embeddings reales de OpenAI y cross-encoder real
([REPORT.md](../../evals/retrieval/REPORT.md), [results.csv](../../evals/retrieval/results.csv)):

| Config | Descripción | Precisión@5 (media) | Latencia media (ms) |
|--------|-------------|--------------------:|--------------------:|
| **A** | vectorial / sin rerank | **0.920** | **1.7** |
| **B** | híbrida (RRF) / sin rerank | 0.800 | 3.1 |
| **C** | vectorial / rerank | **0.920** | 24.0 |
| **D** | híbrida (RRF) / rerank | **0.920** | 25.8 |

Precisión@5 por consulta:

| Config | Q1 | Q2 | Q3 | Q4 | Q5 |
|--------|---:|---:|---:|---:|---:|
| A | 1.00 | 1.00 | 0.60 | 1.00 | 1.00 |
| B | **0.60** | 1.00 | 0.60 | 1.00 | **0.80** |
| C | 1.00 | 1.00 | 0.60 | 1.00 | 1.00 |
| D | 1.00 | 1.00 | 0.60 | 1.00 | 1.00 |

*(Q3 = 0.60 es su **techo**: solo hay un presupuesto relevante con 3 chunks, luego el
máximo posible es 3/5. No es un fallo de las configs.)*

### Interpretación (esto es lo que importa)

1. **La vectorial sola (A) ya está en el techo del corpus (0.920).** Con 15 presupuestos
   bien separados semánticamente, los embeddings solos recuperan casi perfecto.
2. **La híbrida SIN rerank (B) *empeoró* la precisión (0.80 < 0.92).** El matching léxico
   por OR mete candidatos débilmente relacionados (Q1 y Q5 cayeron), y RRF los promueve.
   Es un resultado valioso: **añadir híbrida no es gratis; en un corpus pequeño y limpio
   donde el vector ya acierta, puede meter ruido.**
3. **El reranking rescata a la híbrida (D=0.92) y no mueve a la vectorial (C=0.92).** El
   cross-encoder re-puntúa los candidatos y hunde el ruido que la híbrida había subido.
   Hace su trabajo: **limpiar un conjunto de alto recall pero sucio.**
4. **El coste:** el rerank multiplica la latencia **~14×** (1.7 → 24 ms); la híbrida
   ~1.8× (1.7 → 3.1 ms).

### Conclusión

**En este corpus gana la configuración A (vectorial, sin rerank):** logra la máxima
precisión (0.92, el techo) a **1.7 ms**, mientras que C y D pagan **~24 ms por la misma
precisión**. El reranking **no aporta ninguna ganancia de relevancia aquí** —porque no
queda nada que ganar, la recuperación ya está saturada— así que **su latencia 14× no se
justifica**. La híbrida por sí sola es incluso contraproducente.

**¿Significa esto que híbrida y reranking son inútiles?** No — significa que **este
corpus es demasiado pequeño y limpio para necesitarlos**. La medición también muestra
*cuándo* empezarían a pagar: cuando el corpus crezca y se vuelva ruidoso, la recuperación
dejará de estar saturada; entonces la híbrida aportará *true positives* que el vector se
pierde, y el reranking será justo lo que necesitas para reordenar ese recall más ancho y
sucio (lo vimos en pequeño: D repara el daño de B). La decisión correcta hoy es **A, y
re-medir con este mismo `run.py` cuando el corpus crezca**. Eso es exactamente lo que el
ejercicio persigue: **medir antes de adoptar.**

---

## 5. Cómo ejecutarlo

```bash
# 1) Postgres (pgvector) arriba y migrado
docker compose up -d postgres
DATABASE_URL=postgresql+asyncpg://estimator:estimator@localhost:5433/estimator \
  uv run alembic upgrade head

# 2) (si la BBDD está vacía) ingerir los 15 presupuestos vía POST /embeddings/ingest
#    — ver query_examples.py de la sesión 08.

# 3) Lanzar la evaluación (embeddings reales + cross-encoder real)
DATABASE_URL=postgresql+asyncpg://estimator:estimator@localhost:5433/estimator \
  uv run python -m evals.retrieval.run
# -> escribe evals/retrieval/REPORT.md y results.csv

# 4) Probar los 4 modos por API, sin tocar código
#    POST /search  {"query":"...", "mode":"hybrid", "rerank":true}

# 5) Tests (los de BBDD se saltan solos si no hay Postgres)
uv run pytest -q
```

---

## 6. Nota honesta sobre el enfoque (Opción B)

El enunciado asume un **pipeline RAG completo** de la sesión 9 *en directo*
(reformular → recuperar → generar) y un wrapper de cross-encoder **ya provisto**, y
sugiere trabajar sobre un fork del repo del profesor. Nosotros hicimos la sesión 9 solo
como **diagnóstico** (no construimos ese pipeline). Aquí tomamos una **decisión
consciente**: hacerlo sobre **nuestro repo continuo**, midiendo sobre **nuestros datos**.

Consecuencias, dichas claras:
- Lo que la sesión 10 **mide es la calidad del *retrieval*** (precisión@5), y eso ya lo
  teníamos (pgvector + 37 chunks de la sesión 8). **No** necesitábamos la etapa de
  generación para el entregable, así que el experimento es completo y honesto.
- El wrapper del cross-encoder, que el enunciado da "ya construido", aquí lo
  **construimos nosotros** (es corto: `reranker.py`).
- Adaptamos a nuestro corpus **inglés** la config de full-text (`english`) y el modelo de
  reranking (cross-encoder inglés), y el **pool de recall** (15) al tamaño del corpus.

Es una desviación deliberada del enunciado, elegida por continuidad del proyecto; el
resultado es un experimento real sobre *nuestro* sistema, que es más defendible que medir
sobre datos ajenos.
