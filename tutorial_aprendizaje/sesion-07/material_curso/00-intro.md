# 00 — Embeddings y representación vectorial (introducción)

> Material del curso LIDR · AI Engineering · Sesión 7 (Antonio Pérez). Segundo paso del **Módulo 3 (RAG)**.

La sesión 6 cerró con los presupuestos históricos **limpios, normalizados y validados** en JSON.
La sesión 7 da el primer paso hacia la **búsqueda semántica**: convertir esos JSON en **vectores**.

El objetivo del sistema final: cuando llegue un brief de cliente ("necesitamos un servicio de
autenticación con OAuth para una app móvil financiera"), encontrar automáticamente qué componentes
de presupuestos pasados son relevantes — **aunque el brief no comparta ni una palabra literal** con
los documentos. "Authentication service" debe encontrar "OAuth 2.0 backend", "JWT authorization
module", etc. Eso es lo que resuelven los embeddings.

Las 4 lecciones forman una cadena; la 4ª aterriza directamente en el ejercicio:

| # | Lección | Idea-ancla |
|---|---------|-----------|
| 1 | [Embeddings: del texto a la geometría semántica](01-embeddings-geometria.md) | Un embedding es un vector; textos similares → vectores cercanos. Coseno / dot / euclídea. |
| 2 | [Selección de modelos de embeddings](02-seleccion-modelos.md) | 5 ejes de decisión, MTEB no es oráculo, Matryoshka. Por qué **text-embedding-3-small**. |
| 3 | [Estrategias profesionales de chunking](03-estrategias-chunking.md) | 12 estrategias en 4 familias. El chunking mueve la calidad **tanto como el modelo**. |
| 4 | [Chunking del proyecto: JSON y transcripciones](04-chunking-proyecto.md) | Dos tipos de documento, dos chunkers. El **chunker estructural JSON** = el ejercicio. |

## El ejercicio (pre-sesión, entregable)

Un **pipeline mínimo end-to-end**: recibe presupuestos JSON → los parte en chunks respetando la
estructura → genera embeddings con OpenAI → devuelve los vectores por HTTP. Cierra con un `compare.py`
que mide similitud coseno entre parejas de textos (sanity check). *Ver [EJERCICIO.md](EJERCICIO.md).*

> 🔑 **Alcance deliberado:** NO se persiste en BBDD vectorial (eso es la **sesión 8** con pgvector),
> NO hay retrieval ni otras estrategias de chunking (eso es el directo). Solo el primer ladrillo:
> chunk → embed → vector en memoria.

## Lo que construimos (mapa)

`app/embedding_pipeline/`: `schemas.py` (Budget/Chunk/EmbeddedChunk/Ingest*), `chunker.py`
(`JSONStructuralChunker`), `embedder.py` (`OpenAIEmbedder`), `similarity.py` (coseno a mano),
`router.py` (`POST /embeddings/ingest`) + `scripts/compare.py` + `data/budgets_sample.json` (15
presupuestos, 37 componentes) + `SANITY_CHECK.md` (resultados reales de las 3 parejas).
