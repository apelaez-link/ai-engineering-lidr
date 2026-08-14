# 02 — Selección de modelos de embeddings: trade-offs en producción

> Material del curso LIDR · AI Engineering · Sesión 7 (Antonio Pérez). (≈28 min)

La decisión que más mueve el dial de calidad: **qué modelo** usas para vectorizar. No hay respuesta
universal. Para llegar al directo con la decisión tomada y argumentada, no copiada de un blog.

## El panorama (mayo 2026)

**Comerciales (API):**
- **OpenAI `text-embedding-3-small`** — 1536 dims (Matryoshka hasta 256), **$0.02/1M tokens**, MTEB ~62. El caballo de batalla pragmático.
- **OpenAI `text-embedding-3-large`** — 3072 dims, $0.13/1M (6.5× más caro). Mejor calidad; justificado en dominios complejos y volumen bajo.
- **Cohere embed-v3** — fuerte en multilingüe (100+ idiomas), reranking integrado, $0.10/1M.
- **Voyage voyage-3-large** — optimizado para retrieval, lidera benchmarks retrieval-focused.

**Open source (self-hosted):**
- **BAAI/bge-m3** — multilingüe robusto, 1024 dims, MIT, modos dense/sparse/multi-vector. Requiere GPU.
- **sentence-transformers/all-MiniLM-L6-v2** — 384 dims, Apache 2.0, inglés, corre en CPU, MTEB ~56. El "small fast cheap".

> Precios/scores válidos a mayo 2026; los proveedores recortan precios cada pocos meses. Verifica.

## MTEB no es lo que parece

El **Massive Text Embeddings Benchmark** es la referencia de facto, pero tres cosas que **no** te dice:
1. Mide rendimiento **promedio en datasets públicos generalistas**. Tu dominio no es genérico: un modelo con 65 en MTEB puede sacar 40 en tu corpus específico.
2. Se ha vuelto **objetivo de optimización**: muchos modelos están afinados para subir en MTEB, no para producir mejor retrieval real (cuando una métrica es target, deja de ser buena métrica).
3. Investigación reciente (Vectara, NAACL 2025): **la variación por estrategia de chunking puede ser tan grande como la variación entre modelos**. Optimizar el chunker rinde más que obsesionarse con 1-2 puntos de MTEB.

**Uso honesto de MTEB:** filtro grueso para descartar modelos débiles. **Elección correcta:** benchmark sobre **tus propios datos** con tus consultas reales.

## Matryoshka (MRL)

El modelo se entrena para producir embeddings buenos a **varias dimensionalidades anidadas** (256,
512, 1024…). Las **primeras dimensiones cargan más información**, así que puedes **truncar** el
vector conservando la mayor parte de la calidad. OpenAI: `text-embedding-3-large` truncado a 256d
supera al viejo `ada-002` completo a 1536d.

- **Vía API** (correcto): pasar `dimensions=256` en la llamada → devuelve el vector truncado y **renormalizado**.
- **Truncado manual**: `vec[:256]` pierde la norma unitaria → hay que **renormalizar a mano** (`x/||x||`), o el coseno downstream se rompe.

¿Cuándo compensa? Con **millones de vectores** donde storage/latencia importan. Para los ~37 chunks del proyecto, la diferencia 1536 vs 256 son megabytes: no es prioridad. Se deja como palanca futura.

## Cinco ejes de decisión

1. **Dimensionalidad** — más dims = más capacidad pero más bytes/latencia. Irrelevante en proyectos pequeños; decisivo con cientos de millones de vectores.
2. **Idioma del corpus** — inglés puro → English-only rápidos. Mezcla/no-anglosajón → multilingüe obligatorio.
3. **Dominio** — un modelo de prosa general puede ser mediocre en jerga técnica. No hay modelo especializado en "presupuestos de software" → generalista + validar sobre datos.
4. **Hosting y coste** — API (cero infra, coste/token, datos salen) vs self-hosted (cero coste/token, GPU, datos no salen). <20M tokens/mes → API casi siempre más barata.
5. **Licencia** — propietaria (OpenAI/Cohere/Voyage) vs permisiva auto-hosteable (bge-m3 MIT, MiniLM Apache). Banca/sanidad/defensa con "los datos no salen" → solo self-hosted.

Identifica **qué eje pesa más** en tu contexto y la decisión se simplifica.

## La decisión del proyecto: `text-embedding-3-small` (1536d)

- **Dimensionalidad**: 1536 es excesivo para ~37 chunks, pero el storage extra es despreciable. Default simple; Matryoshka queda como palanca.
- **Idioma**: descripciones en inglés, briefs futuros probablemente en español → multilingüe decente. Suficiente (no el mejor, que sería bge-m3/Cohere).
- **Dominio**: ningún especializado; generalista validado sobre datos.
- **Coste**: API ya configurada desde S01, cero fricción. Ingestar los 15 presupuestos ≈ 15.000 tokens ≈ **$0.0003**. Despreciable.
- **Licencia**: propietaria, pero proyecto académico sin datos sensibles. Aceptable.

**Por qué no las alternativas:** `3-large` (6.5× más caro por +2 MTEB, no se justifica al volumen);
`bge-m3` (mejor multilingüe pero añade servidor de inferencia/GPU sin valor pedagógico);
`voyage-3-large` (otro proveedor/API key/billing); `MiniLM` (inferior en multilingüe, se usa en el
directo como contraste). La elección es "**mejor balance pedagogía/calidad/coste/operación**", no
"el mejor modelo posible". Si cambia el contexto (millones de vectores, datos sanitarios), cambia.

> Sobre coste a escala: la **Batch API de OpenAI** aplica **50% de descuento** a cambio de
> procesamiento asíncrono (hasta 24 h). Relevante cuando los volúmenes crecen.
