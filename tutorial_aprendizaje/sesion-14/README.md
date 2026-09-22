# Sesión 14 — Sistemas multi-agente con LangGraph (catch-up)

> **Módulo 5.** Nota de estudio consolidada (compilada del **ejercicio completo** + índice de
> lecciones + conceptos). El salto de la S14: pasar de **un grafo** (S13) a **varios agentes
> coordinados** con **privilegio mínimo** y una **persona humana en el bucle** para las acciones
> de riesgo.

## Idea central
Un solo agente con muchas tools acaba siendo confuso e inseguro. La S14 lo parte en **agentes
especializados** coordinados por un **supervisor** que solo enruta. Dos principios de producción:
**least-privilege** (cada worker recibe *solo* las tools que su rol necesita) y **human-in-the-loop**
(las acciones irreversibles/caras se **pausan** y esperan aprobación humana antes de ejecutarse).
Se construye **a mano** con `StateGraph` + `Command`, no con `create_supervisor` — para entender el
mecanismo, igual que la S12 construía el bucle a mano.

## Las 6 lecciones (índice)
1. **De un agente a un equipo** — cuándo dividir (roles claros, tools que no deben mezclarse).
2. **Supervisor y workers** — el patrón; supervisor enruta, workers ejecutan.
3. **Privilegio mínimo** — cada agente ve solo sus tools; por qué es seguridad, no estética.
4. **Human-in-the-loop con `interrupt()`** — pausar el grafo, persistir estado, reanudar.
5. **Validación de acciones y auditoría** — comprobar permisos + registrar quién/qué/por qué.
6. **Coordinación y estado compartido** — `Command(goto=..., update=...)`, evitar bucles infinitos.

## El ejercicio (qué construir) — deadline real domingo 13 sept
Convertir el grafo lineal de la S13 en un **equipo supervisor/workers** con privilegio mínimo y HITL.

**Agentes y su privilegio (tabla del enunciado):**
| Agente | Tools que recibe | No puede |
|---|---|---|
| `supervisor` | ninguna (solo enruta) | ejecutar lógica de negocio |
| `requirements_extractor` | ninguna tool de negocio | tocar presupuestos/estimaciones |
| `budget_searcher` | `search_budgets` | calcular ni validar |
| `estimate_generator` | `calculate_estimate` | buscar ni validar |
| `coherence_validator` | `validate_estimate` | buscar ni calcular |

- **Nivel 1 (obligatorio):** supervisor + los 4 workers con `StateGraph` + `Command`; cada worker
  recibe **solo su tool** (least-privilege real, no un `if` interno); el supervisor decide el
  siguiente agente y termina cuando la estimación está validada. Mantener el contrato del endpoint.
- **Nivel 2 (obligatorio):** **human-in-the-loop** — cuando la estimación supera un umbral (coste/riesgo),
  el grafo llama a **`interrupt()`**, deja `status="awaiting_human_review"` y **persiste** (checkpointer
  S13). Un **endpoint de resume** reanuda con la decisión humana (aprobar/rechazar/editar) vía `thread_id`.
- **Nivel 3 (opcional):** **validación de acciones** (comprobar que el agente que pide una acción tiene
  el privilegio para ella) + **auditoría** con `structlog` (quién pidió qué, qué se aprobó, qué se ejecutó).

**Fuera de alcance:** memoria compartida sofisticada entre agentes, más de un punto de HITL,
reintentos entre agentes.

**Esqueleto de referencia** (del enunciado): `graph/agents.py` (un builder por worker que **cierra
sobre su lista de tools**, p. ej. `make_budget_searcher(tools=[search_budgets])`), `graph/supervisor.py`
(nodo que devuelve `Command(goto="budget_searcher" | ... | END)`), el gate HITL
(`value = interrupt({"estimate": ..., "reason": "coste > umbral"})`), y el endpoint
`POST /resume/{thread_id}` que hace `graph.ainvoke(Command(resume=decision), config)`.

## Conexión con tu Proyecto Final
Es **directamente** el patrón del copiloto municipal: workers `buscar_normativa` /
`consultar_incidencias` / `redactar_respuesta`, un supervisor que enruta, **privilegio mínimo** (el
que redacta no consulta la BBDD y viceversa) y **HITL obligatorio** antes de cualquier acción con
efecto (abrir incidencia, notificar) — que en un servicio público es un requisito, no un extra.
La auditoría con `structlog` es justo lo que un ayuntamiento exige para trazabilidad.

## Estado y ejecución
- **Sistema multi-agente CONSTRUIDO** (Opción B), rama `session-14/pre-work` (parte de
  `session-13/pre-work`, así que incluye S12 + S13 + S14). Código en
  [`app/multiagent/`](../../app/multiagent):
  - `privileges.py` — `AGENT_PRIVILEGES` (cada agente, sus tools) + `enforce_privilege`
    (comprobación real, no un `if` interno; lanza `PrivilegeError`) + auditoría structlog. **Niveles 1 y 3.**
  - `build.py` — el **supervisor** (solo enruta, `Command(goto=...)`), los **4 workers**
    con privilegio mínimo (cada uno usa SOLO su tool, `Command(goto="supervisor", ...)`) y
    el nodo **`human_review`** con `interrupt()`. Construido a mano con `StateGraph` +
    `Command` (NO `create_supervisor`). **Niveles 1 y 2.**
  - `router.py` — `POST /multiagent/estimate` (arranque) y `POST /multiagent/resume/{thread_id}`
    (reanudación), ambos con checkpointer AsyncPostgresSaver. **Nivel 2.**
  - `state.py` — `MultiAgentState` con reducers acumuladores (`budget_matches`, `errors`, `audit`).
- Config nueva: `MULTIAGENT_REVIEW_THRESHOLD_HOURS` (umbral de horas para exigir revisión humana).
- **Tests:** `tests/multiagent/` (6; privilegios + un run completo que PARA en revisión humana
  con MemorySaver y REANUDA con approve). Suite total: 173 passed, 2 skipped.
- Reutiliza los pasos LLM de S13, la búsqueda de S10, el generador de S11 y las tools de S12.
- **Cómo ejecutarlo (S12+S13+S14 seguidas):** ver [`EJECUCION.md`](EJECUCION.md).
- **Entrega:** rama `session-14/pre-work` (deadline pasado; suma al certificado por la vía de
  ejercicios). **Pieza central del Proyecto Final** (copiloto multi-agente con revisión humana).
