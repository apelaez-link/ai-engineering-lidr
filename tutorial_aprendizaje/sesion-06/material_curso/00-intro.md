# 00 — Fundamentos de data-driven AI (introducción)

> Material del curso LIDR · AI Engineering · Sesión 6 (Antonio Pérez). Abre el **Módulo 3 (RAG)**.

La sesión 5 cerró el módulo CAG: un estimador **conversacional** que inyecta en cada
turno `[summary] + anchors + ventana + ProjectMetadata + tier + transcript + adjuntos`.
Todo cabe en el contexto **por construcción**. Funciona mientras los proyectos son cortos
y los adjuntos modestos.

La sesión 6 hace dos cosas a la vez:

1. **El ejercicio (pre-sesión)** te obliga a **medir** dónde se rompe ese CAG: lo
   instrumentas, lo sometes a carga (multi-turno largo, adjuntos grandes, ráfagas) y
   produces un `REPORT.md` con un **baseline cuantitativo**. No se optimiza nada: se mide.
   *Ver [EJERCICIO.md](EJERCICIO.md).*
2. **Las 5 lecciones teóricas** abren el **Módulo 3 (RAG)** pero, deliberadamente, **no
   tocan embeddings ni bases vectoriales todavía**. Antes de vectorizar, hay que entender
   **los datos**: por qué el CAG se rompe, cómo decidir CAG vs RAG vs híbrido, y cómo
   construir un corpus que aguante una auditoría seria.

Las 5 lecciones forman una cadena acumulativa sobre el **Proyecto 2** (un RAG de estimación
que recibe transcripciones y devuelve estimaciones con histórico de presupuestos):

| # | Lección | Idea-ancla |
|---|---------|-----------|
| 1 | [Calidad del dato y decisiones de arquitectura](01-calidad-del-dato.md) | El techo del CAG son **4 restricciones** (ventana, coste, latencia, degradación). Árbol de decisión CAG/RAG/híbrido. |
| 2 | [Auditoría e inventario de datos](02-auditoria-inventario.md) | **Inventario antes de vectorizar**: censo + calidad por dimensiones + `data_catalog.yaml` versionado. |
| 3 | [Pipeline de extracción multi-formato](03-pipeline-extraccion.md) | El **`Document` canónico** como contrato. `loaders → parsers → normalizers`. |
| 4 | [Limpieza, normalización y validación](04-limpieza-normalizacion.md) | Contrato de **forma** (Pydantic) vs de **contenido** (Pandera). Reparar/cuarentena/descartar. |
| 5 | [PII, anonimización y GDPR](05-pii-gdpr.md) | **Filtración semántica** vía RAG. Presidio + pseudonimización reversible + derecho al olvido. |

> 🔑 **El hilo conductor del módulo:** *"vectorizar sobre datos sucios es construir sobre
> arena"*. Lo que construiste en el Módulo 2 (CAG) **no se tira**: se reposiciona como la
> capa de contexto estático de una arquitectura **RAG + CAG residual**.
