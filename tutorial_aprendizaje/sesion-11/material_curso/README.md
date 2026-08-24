# Material del curso — Sesión 11: RAG Avanzado (Generación y calidad)

Notas fieles de las **6 lecciones** de la sesión 11 (Módulo 4, RAG). Resúmenes didácticos en
mis palabras (no transcripciones), con la conexión a nuestra entrega.

Hilo conductor de la sesión: cerrar el RAG **por el lado del generador** y hacer que su
calidad sea **medible**. Cada lección deja abierto el problema que resuelve la siguiente:
preparar el contexto → sintetizar fuentes que se contradicen → citar de forma verificable →
detectar alucinaciones → mantener el índice sano → medir el conjunto con RAGAS. La última
apunta ya al **Módulo 5 (agentes)**: coordinar varios pasos de razonamiento especializados.

| # | Lección | ¿En el ejercicio? |
|---|---------|-------------------|
| [01](01-content-augmentation.md) | Content augmentation: preparar el contexto antes de generar | Contexto (mejora del baseline) |
| [02](02-sintesis-fuentes-contradictorias.md) | Síntesis de múltiples presupuestos que se contradicen | Contexto (evolución) |
| [03](03-citacion-verificable.md) | Citación y atribución verificable | ✅ **Parte 1** |
| [04](04-deteccion-alucinaciones.md) | Detección y mitigación de alucinaciones | ✅ (parcial: abstención + integridad) |
| [05](05-reindexacion-versionado-embeddings.md) | Reindexación y versionado de embeddings | Producción (fuera de alcance) |
| [06](06-evaluacion-ragas.md) | Evaluación de calidad con RAGAS | ✅ **Parte 2** |

> La guía de nuestra implementación + los resultados reales (tabla RAGAS + la "nota") están en
> [`../README.md`](../README.md).
