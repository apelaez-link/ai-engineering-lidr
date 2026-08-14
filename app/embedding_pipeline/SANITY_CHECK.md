# SANITY_CHECK — embeddings pipeline (sesión 07)

Sanity check del pipeline de embeddings: tres parejas de textos embebidas con
`text-embedding-3-small` (llamadas **reales** a la API) y su similitud coseno,
calculada con `scripts/compare.py`. No es una validación formal de calidad de
retrieval (eso llega en la sesión 11 con recall@k / NDCG): es el mínimo aceptable que
demuestra que el pipeline funciona end-to-end y que los embeddings **discriminan**
entre textos cercanos y lejanos.

Reproducir: `uv run python scripts/compare.py --text-a "..." --text-b "..."` (necesita
`OPENAI_API_KEY` en el `.env`). Modelo: `text-embedding-3-small`, 1536 dimensiones.

## Resultados

| Pareja | Tipo | Similitud coseno | Expectativa |
|--------|------|-----------------:|-------------|
| A | Semánticamente cercanos (distinto vocabulario) | **0.5957** | alta (> 0.6 orientativo) |
| B | No relacionados | **0.1920** | baja (< 0.4 orientativo) |
| C | Genéricos / ambiguos | **0.5408** | sin expectativa fija |

Textos:

- **A1** — "OAuth 2.0 authentication backend with JWT tokens for fintech mobile app"
- **A2** — "Authorization service using JSON Web Tokens for a banking application"
- **B1** — "OAuth 2.0 authentication backend with JWT tokens for fintech mobile app"
- **B2** — "Database migration from MySQL to PostgreSQL with zero downtime"
- **C1** — "Backend services"
- **C2** — "API development"

## Comentario

Lo importante es la **estructura**, no los valores absolutos, y la estructura es la
correcta: A (0.596) > C (0.541) ≫ B (0.192). El modelo separa con holgura lo cercano de
lo lejano — la pareja no relacionada cae a 0.19 mientras la cercana queda a 0.60 —, así
que el pipeline discrimina razonablemente y podemos construir búsqueda semántica encima.

Lo que llama la atención (y es buen material para el directo): la **pareja A se queda
justo por debajo del 0.6 orientativo** (0.5957), aun siendo prácticamente el mismo
concepto con otras palabras. Encaja con lo que avisaba la lección 1 sobre la *maldición
de la dimensionalidad*: en espacios de muchas dimensiones los umbrales absolutos engañan,
y un "0.6 = muy similar" universal no existe. El umbral hay que calibrarlo sobre el propio
corpus. Segundo detalle: la **pareja C genérica sale casi tan alta (0.54) como la cercana
A (0.60)**; dos términos vagos como "Backend services" y "API development" viven cerca en
el espacio porque comparten un campo semántico amplio y poco específico. La lectura
práctica: en retrieval real convendrá enriquecer los chunks con contexto (el header
contextual del chunker ya va en esa dirección) para que las consultas específicas no
compitan con ruido genérico.
