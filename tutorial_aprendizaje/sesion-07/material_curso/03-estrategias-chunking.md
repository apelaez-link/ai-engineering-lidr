# 03 — Estrategias profesionales de chunking

> Material del curso LIDR · AI Engineering · Sesión 7 (Antonio Pérez). (≈32 min) · El artículo central.

La pregunta con más impacto en la calidad de un RAG: **¿cómo partimos los documentos antes de
embeber?** Presupuesto entero → vector difuso que mezcla todo. Trozos diminutos → pierdes contexto.
Por carácter → rompes palabras. Este artículo es el **mapa del territorio**: 12 estrategias en 4
familias. Elegir la que **coincide con tu tipo de corpus** es lo que decide el éxito.

## Por qué el chunking domina la calidad

- **Vectara (NAACL 2025)**: la varianza por estrategia de chunking puede ser **tan grande como la de cambiar de modelo**.
- **Chroma (2025)**: LLM/Cluster semantic chunkers ~0.919/0.913 recall; recursive bien tuneado (400 tokens) 0.88–0.89. Diferencia mejor-peor: 9 puntos.
- **Vecta (feb 2026)**: recursive de 512 tokens **1º con 69% accuracy**; semantic chunking (más "sofisticado") 4º con 54%. **La sofisticación no garantiza mejor rendimiento**; lo garantiza la coincidencia estrategia↔corpus.

**Conclusión operativa: mide sobre tus datos antes de comprometer arquitectura.**

## Familia 1 — Mecánicas (parten sin entender el contenido)

- **Fixed-size** — N caracteres/tokens con overlap (10–20%). Baseline. Bien en corpus homogéneo (logs); mal en cualquier estructura interna.
- **Recursive character splitter** — jerarquía de separadores `["\n\n","\n",". "," ",""]`; parte por el más fuerte que quepa. **La más usada en producción y difícil de batir.** Default: 400–512 tokens, overlap 10–20%. Empieza SIEMPRE aquí.
- **Sentence-window** — indexa oraciones (precisas), devuelve una ventana ampliada al recuperar. Bien en manuales/papers/contratos.
- **Sliding window** — fixed-size con paso independiente del overlap. Texto continuo sin separadores.

## Familia 2 — Estructurales (explotan el formato del documento)

- **Document-based (Markdown/HTML/JSON)** — respeta headers/tags/jerarquía. Para JSON **no hay splitter genérico**: la unidad lógica depende del dominio (en un presupuesto = un componente) → **chunker custom** (justo lo del artículo 4 y el ejercicio). Microsoft Azure: añadir el header como metadata sube **+15–25 puntos** de accuracy de QA.
- **Hierarchical / parent-child** — indexa chunks pequeños (precisión), asociados a un padre grande (contexto). Es una **arquitectura de retrieval**, no solo chunking.

## Familia 3 — Semánticas (calculan dónde cambia el significado)

- **Semantic chunking** — embebe oraciones consecutivas, corta donde la similitud cae. Bien en multi-tema sin estructura. **Coste oculto:** embeber cada oración en ingesta (multiplica coste/latencia); ganancias sobre recursive a menudo marginales.
- **Cluster semantic** — agrupa oraciones similares aunque no sean consecutivas. Rompe la trazabilidad.
- **LLM-based / propositional** — un LLM extrae proposiciones autocontenidas. La más cara, a veces la mejor (Chroma: 0.919 recall). ROI explícito: para 1M docs son cientos/miles de $.

## Familia 4 — Avanzadas y contextuales (complementos, no alternativas)

- **Late chunking** (Jina, fin 2024) — embebe el documento entero primero, extrae chunks de la representación global. Requiere modelo de contexto largo + token-level embeddings.
- **Agentic chunking** — un agente decide la estrategia por sección. Corpus heterogéneo; el más caro.
- **Query-dependent** (AI21, 2026) — indexa varias resoluciones, elige en tiempo de consulta.
- **Contextual Retrieval (Anthropic, sep 2024)** — antes de embeber, un LLM añade un párrafo que **sitúa el chunk en el documento**. Anthropic: **−35% fallos de retrieval** (−49% con BM25, −67% con reranking). La técnica avanzada más madura; probablemente vale la pena si tu RAG ya funciona pero no afina. Con prompt caching, ~$1/1M tokens.

## Criterios honestos para elegir

1. **Empieza con `RecursiveCharacterTextSplitter`** (400–512 tokens, 10–20% overlap). Difícil de batir, barato. Cambia solo con evidencia medida.
2. **Si hay estructura explícita, úsala** (document-based + metadata). Mayor ROI conocido.
3. **Si los chunks pierden sentido al aislarse**, considera Contextual Retrieval.
4. **Semantic/LLM-based**: legítimos pero caros; justifícalos con datos.
5. **Parent-child**: es arquitectura; no lo metas si el pipeline aún no funciona plano.
6. **Late/agentic/query-dependent**: emergentes; no producción sin caso concreto. La novedad no es ventaja per se.
7. **El mejor chunking depende del tipo de documento.** Corpus heterogéneo → distintas estrategias por tipo. **Justo la situación del proyecto**: presupuestos JSON estructurados + transcripciones en texto plano. → artículo 4.
