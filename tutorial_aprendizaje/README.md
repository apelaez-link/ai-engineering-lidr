# 🎓 Tutorial de aprendizaje — Sesión 03: Patrones de diseño para wrappers de modelos

Esta carpeta es una **herramienta de estudio sobre tu propio proyecto**. Cada lección
explica una capa que añadimos en la sesión 03, con el *porqué* de cada decisión y un
**reto práctico** al final para que toques el código y veas el efecto.

> **De prototipo a producto.** En la sesión 02 dejaste un endpoint CAG que *responde*.
> En la 03 te centras en *cómo* responde: cómo cambia de proveedor sin tocar lógica,
> cómo evita repetir trabajo (caché), cómo se muestra en tiempo real (streaming) y
> cómo se observa (trazabilidad). Son patrones reutilizables en cualquier proyecto con LLMs.

## Cómo usar este tutorial

1. Ten algo corriendo en otra terminal para probar sobre la marcha:
   ```bash
   uv run uvicorn app.main:app --reload      # API en /docs
   uv run streamlit run streamlit_app.py     # interfaz de chat
   ```
2. Lee las lecciones **en orden**: van de la experiencia de usuario (interfaz) hacia
   dentro (wrapper, caché, observabilidad).
3. En cada reto: intenta resolverlo tú primero.
4. Tras cada cambio, recarga `/docs`, la app Streamlit, o corre `uv run pytest`.

## Índice

| # | Lección | Qué aprendes | Código |
|---|---------|--------------|--------|
| 00 | [De prototipo a producto](00-de-prototipo-a-producto.md) | El salto de la sesión 02 a la 03 y la arquitectura en capas | `app/main.py` |
| 01 | [Interfaces conversacionales](01-interfaces-conversacionales.md) | Streamlit vs Gradio vs Chainlit; el modelo de re-ejecución | `streamlit_app.py` |
| 02 | [Abstracción de proveedores y fallback](02-abstraccion-y-fallback.md) | LiteLLM, el "ORM de los LLMs", y rotación por errores | `app/services/llm_wrapper.py` |
| 03 | [Cacheo inteligente](03-cacheo-inteligente.md) | Exact-match, clave determinista, TTL, invalidación | `app/cache/llm_cache.py` |
| 04 | [Streaming y respuestas largas](04-streaming.md) | StreamingResponse vs SSE vs WebSockets; `st.write_stream` | router `/estimate/stream` |
| 05 | [Observabilidad y trazabilidad](05-observabilidad.md) | structlog, logs como datos, qué medir en cada llamada | `app/logging_config.py` |
| 06 | [Retos extra (vs repo del profesor)](06-retos-extra.md) | Evaluación estructural, demo SSE HTML, Redis con Docker, fakeredis | `app/services/evaluation.py` |

## Material del curso (teoría)

Los textos teóricos del curso LIDR (Sesión 3) viven en [`material_curso/`](material_curso/),
recuperados de la plataforma. Las lecciones los referencian con bloques
**📚 Concepto del curso** para conectar la teoría con tu código.

| Doc | Contenido |
|---|---|
| [00 — De prototipo a producto](material_curso/00-de-prototipo-a-producto.md) | Introducción y objetivos de la sesión |
| [01 — Interfaces conversacionales](material_curso/01-interfaces-conversacionales.md) | Streamlit / Gradio / Chainlit y cuándo usar cada uno |
| [02 — Abstracción y fallback](material_curso/02-abstraccion-y-fallback.md) | El problema del acoplamiento, LiteLLM, estrategias de fallback |
| [03 — Cacheo inteligente](material_curso/03-cacheo-inteligente.md) | Exact-match, semántico, multi-nivel, invalidación, métricas |
| [04 — Streaming](material_curso/04-streaming.md) | Chunked, SSE, WebSockets, streaming por proveedor |
| [05 — Observabilidad](material_curso/05-observabilidad.md) | Structured logging, structlog, herramientas (Logfire, Langfuse) |
| [EJERCICIO](material_curso/EJERCICIO.md) | Enunciado del ejercicio entregable (Streamlit) |
