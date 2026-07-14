# 🎓 Tutorial — Sesión 07: Embeddings y representación vectorial

Segundo paso del **Módulo 3 (RAG)**. Tras dejar los presupuestos limpios en la sesión 6, aquí damos
el primer paso hacia la **búsqueda semántica**: convertir esos JSON en **vectores**.

> 🔑 El ejercicio es **pre-sesión** (rama `pre-session-07`, enlace por mail a `george@lidr.co`). El
> directo parte de este pipeline para comparar otras estrategias de chunking.

## Qué construimos (el entregable)

Un **pipeline mínimo end-to-end**: presupuestos JSON → chunks estructurales → embeddings OpenAI →
vectores por HTTP, + un CLI de sanity check.

| Pieza | Qué | En el repo |
|-------|-----|-----------|
| Schemas | Budget/BudgetComponent/Chunk/EmbeddedChunk/Ingest* (Pydantic v2) | [`app/embedding_pipeline/schemas.py`](../../app/embedding_pipeline/schemas.py) |
| Chunker | `JSONStructuralChunker`: 1 componente = 1 chunk, header contextual, `chunk_id`, `token_count` (tiktoken) | [`chunker.py`](../../app/embedding_pipeline/chunker.py) |
| Embedder | `OpenAIEmbedder`: `text-embedding-3-small`, batches de 100, retry RateLimitError, coste | [`embedder.py`](../../app/embedding_pipeline/embedder.py) |
| Similitud | coseno / dot / euclídea **a mano** (sin numpy) | [`similarity.py`](../../app/embedding_pipeline/similarity.py) |
| Endpoint | `POST /embeddings/ingest` (chunk → embed → stats) | [`router.py`](../../app/embedding_pipeline/router.py) |
| CLI | `compare.py`: similitud coseno entre dos textos | [`scripts/compare.py`](../../scripts/compare.py) |
| Datos | 15 presupuestos, 37 componentes (4 sectores) | [`data/budgets_sample.json`](../../data/budgets_sample.json) |
| Sanity check | 3 parejas con **embeddings reales** | [`SANITY_CHECK.md`](../../app/embedding_pipeline/SANITY_CHECK.md) |

Parte de **`pre-session-06`** (incluye todo lo de las sesiones 03–06). **118 tests verdes** (96 previos + 22 nuevos).

## El pipeline (el orden importa)
```
IngestRequest(budgets) → JSONStructuralChunker.chunk() → [Chunk]
    → OpenAIEmbedder.embed_many() (batches, retry) → [EmbeddedChunk]
    → stats (total_budgets/chunks/tokens/cost) → IngestResponse
```

## Las decisiones que defenderías en el directo

- **Un componente = un chunk** (granularidad = unidad de negocio), no el presupuesto entero ni cada campo.
- **Header contextual del padre** dentro del texto embebido = versión estática y barata de *Contextual Retrieval* (contexto que ya está en el JSON, sin LLM). +15–25 pts de accuracy documentados por Microsoft Azure.
- **Metadata fuera del texto** (filtros SQL en la sesión 8) vs **texto** (pesa en la geometría). Regla: si cambia el significado para una consulta natural → texto; si es discreto y se filtra → metadata.
- **`chunk_id = {budget_id}::{component_id}`** para trazar/citar/invalidar.
- **Coseno a mano, sin numpy** (lo pide el enunciado); `similarity.py` es importable → testeable sin API.
- **SDK de OpenAI directo** para embeddings (no litellm): el ejercicio lo pide y necesitamos su `RateLimitError`. El chat sigue con litellm.
- **Batches de 100 + retry exponencial** (1s/2s/4s) para no serializar llamadas ni caerse por un rate limit transitorio.
- **Embedder inyectable** (`get_embedder` como dependencia FastAPI) → los tests lo sustituyen sin tocar la red.

## Cómo ejecutarlo

```bash
uv sync                                              # instala (añade tiktoken)
uv run pytest -q                                     # 118 tests, sin API key (todo mockeado)

# Endpoint (necesita OPENAI_API_KEY en .env):
uv run uvicorn app.main:app --reload                 # POST /embeddings/ingest en /docs

# CLI de similitud (dos formas, ambas del enunciado):
uv run python scripts/compare.py --text-a "OAuth 2.0 auth backend" --text-b "JWT authorization service"
docker compose exec servicio_ia python scripts/compare.py --text-a "..." --text-b "..."
```

Probar el endpoint con el sample:
```bash
curl -s -X POST http://localhost:8000/embeddings/ingest \
  -H "Content-Type: application/json" \
  -d "{\"budgets\": $(cat data/budgets_sample.json)}" | python -m json.tool | head
```

## Sanity check (datos reales)

`SANITY_CHECK.md` recoge las 3 parejas embebidas con la API real: **A** (cercanos) 0.596, **B** (no
relacionados) 0.192, **C** (genéricos) 0.541. La estructura es la correcta (A ≫ B), y el detalle
interesante — A justo bajo el 0.6 orientativo — ilustra la *maldición de la dimensionalidad* de la
lección 1: los umbrales absolutos engañan; hay que calibrarlos sobre el propio corpus.

## Comparación con el enunciado / repo del profesor

- Nuestra ruta del proyecto vive en la **raíz** (`app/embedding_pipeline/`), no bajo `servicio_ia/`.
- Rama **`pre-session-07`** (convención del repo continuo), no `session-07/pre-exercise`.
- Añadimos **tests mockeados** (22) aunque el enunciado no los exija — como en todas las sesiones.
- `numpy` ya estaba (cacheo semántico S04); **no** lo usamos aquí: coseno con stdlib, respetando el enunciado.

## Material del curso (teoría fiel)
[00 intro](material_curso/00-intro.md) ·
[01 embeddings y geometría](material_curso/01-embeddings-geometria.md) ·
[02 selección de modelos](material_curso/02-seleccion-modelos.md) ·
[03 estrategias de chunking](material_curso/03-estrategias-chunking.md) ·
[04 chunking del proyecto](material_curso/04-chunking-proyecto.md) ·
[✍️ EJERCICIO](material_curso/EJERCICIO.md).

## Siguiente (sesión 8)
Persistencia: **migración a pgvector + endpoint de búsqueda**. Los vectores que aquí generamos en
memoria pasarán a PostgreSQL, y la metadata de cada chunk alimentará filtros SQL combinados con la
búsqueda vectorial.
