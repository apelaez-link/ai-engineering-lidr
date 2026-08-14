"""Pipeline mínimo de embeddings y chunking (sesión 07).

Primer paso del Módulo 3 (RAG) hacia la búsqueda semántica: convertir los
presupuestos históricos (JSON limpio de la sesión 06) en vectores.

Piezas del módulo:
  - schemas.py  : modelos Pydantic (Budget/BudgetComponent/Chunk/EmbeddedChunk + Ingest*).
  - chunker.py  : JSONStructuralChunker (1 componente = 1 chunk, con header contextual).
  - embedder.py : OpenAIEmbedder (text-embedding-3-small, batching, retry, coste).
  - similarity.py: coseno / producto escalar / distancia euclídea, sin numpy.
  - router.py   : POST /embeddings/ingest.

Alcance deliberado del ejercicio pre-sesión: NO persiste en BBDD vectorial (eso es la
sesión 08 con pgvector), NO hay retrieval ni otras estrategias de chunking (directo).
"""
