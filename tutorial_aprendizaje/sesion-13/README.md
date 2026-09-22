# Sesión 13 — Orquestación de agentes con LangGraph (catch-up)

> **Módulo 5.** Nota de estudio consolidada (compilada del **ejercicio completo** + índice de
> lecciones + conceptos; no es la lectura verbatim de las 6 lecciones — pídemela si la quieres a
> fondo). El salto de la S13: pasar del **bucle a mano** de la S12 a un **grafo explícito con
> LangGraph**, con estado tipado, persistencia y observabilidad.

## Idea central
El bucle agéntico de la S12 (razona→actúa→observa a mano) **se vuelve incómodo** en cuanto hay
varios pasos, ramas condicionales o hay que volver atrás. La S13 lo reexpresa como un **grafo de
estados (LangGraph)**: nodos = funciones, aristas = flujo, estado tipado compartido. **De puertas
afuera nada cambia**: el servicio IA sigue recibiendo transcripción y devolviendo estimación +
`status`; el grafo vive dentro.

## Las 6 lecciones (índice)
1. **Del bucle manual al grafo** — cuándo un framework compensa (el bucle a mano no escala con ramas/reintentos).
2. **LangGraph desde cero** — `StateGraph`, nodos, aristas, estado.
3. **Estado y persistencia** — **reducers** (`Annotated[list, operator.add]`), **checkpointers**, memoria.
4. **Ejecución paralela y enrutado condicional** — `Send` API para paralelizar, aristas condicionales.
5. **Manejo de errores y recuperación** en flujos complejos.
6. **Observabilidad** — **LangSmith** y **Logfire** para el servicio IA.

## El ejercicio (qué construir) — deadline real ~S13 (la fecha "14 jul" del post es un placeholder)
Reexpresar el flujo de estimación como un **grafo de LangGraph** con **5 nodos secuenciales**:
`START → extract_requirements → classify_components → search_budgets → generate_estimate → validate_and_consolidate → END`.

- **Nivel 1 (obligatorio):** estado tipado (`TypedDict`) con **≥1 reducer acumulador**
  (`Annotated[list[...], operator.add]`); los 5 nodos como **funciones puras** que devuelven
  actualizaciones parciales (reutilizan tu lógica S9-S12); cablear con aristas y `compile()`.
  El endpoint mantiene el contrato (transcripción → estimación + `status`).
- **Nivel 2 (obligatorio):** **checkpointer** `AsyncPostgresSaver` sobre **el mismo Postgres del
  proyecto** (crea sus propias tablas; convive con pgvector), con un **`thread_id` por ejecución**;
  instrumentar con **Logfire** → **traza completa con un span por nodo** sobre `sample_transcript_complex.txt`.
- **Nivel 3 (opcional):** primera **arista condicional** (`validate → needs_review` / `validated`).

**Fuera de alcance (se ve en el directo):** paralelizar `search_budgets` por componente (`Send`),
manejo de errores avanzado (reintentos/backoff/fallback/timeouts), HITL con `interrupt()`, y la
optimización a partir de la traza.

**Dependencias:** `uv add langgraph langgraph-checkpoint-postgres logfire`.

**Esqueleto de referencia** (lo trae el enunciado): `graph/state.py` (EstimationState TypedDict con
`budget_matches: Annotated[list, operator.add]`, `errors: Annotated[list, operator.add]`),
`graph/build.py` (`StateGraph(...).add_node(...).add_edge(...).compile(checkpointer=...)`),
`graph/nodes.py` (cada nodo `with logfire.span("node: ..."):` devuelve dict parcial), y el arranque
(`logfire.configure()` + `logfire.instrument_fastapi/asyncpg/httpx`, `await checkpointer.setup()`
una vez). Invocación: `await graph.ainvoke({"transcript": ...}, {"configurable": {"thread_id": id}})`.

## Conexión con tu Proyecto Final
LangGraph es **el framework con el que orquestar la capa de agentes** del copiloto municipal
(los nodos serían buscar_normativa / consultar_incidencias / estimar). Es el salto natural del
bucle a mano de la S12. Para el capstone, un grafo LangGraph con checkpointer + Logfire cubre de
golpe "capa de agentes" + parte de la observabilidad.

## Estado
Material de estudio (no construido). Ejercicio no entregado. Es una de las piezas que **absorbe el
Proyecto Final** si montamos ahí la capa de agentes con LangGraph.
