# Sesión 12 — Introducción a agentes de IA (catch-up)

> Rama `session-12/pre-work`. **Módulo 5: Orquestación de agentes.** Recopilación de la
> sesión que no pude atender en directo: el **ejercicio**, las **6 lecciones** y el
> **resumen del directo** (grabación). Deadline del ejercicio fue **dom 30 ago** (ya
> pasado); lo dejo estudiado y preparado para construirlo como catch-up. Impartió **Julián**.

---

## 0. La idea de la sesión en una frase

Un **agente no es magia**: es un **bucle** que llama a un LLM que **decide**, ejecuta
**tools** y **para** cuando ha terminado. Se construye **a mano, sin framework**, para ver
exactamente de qué está hecho (los frameworks —LangChain/LangGraph, S13— envuelven justo
esto). El agente entra como **capa de decisión POR ENCIMA del pipeline** de S9-S11, no lo
sustituye: las piezas del pipeline (retrieval, cálculo, validación) se **promueven a tools**.

## 1. El ejercicio (qué construir)

Un agente que, dada una transcripción de reunión: **descompone** el proyecto en componentes,
usa **2 tools** para actuar, **itera** en un bucle manual (razona → actúa → observa → repite)
hasta producir una estimación estructurada, y devuelve además una **traza** de su razonamiento.

- **`search_budgets(query, filters?)`** → envuelve tu **retrieval híbrido+rerank de S10** (no lo reimplementes).
- **`calculate_estimate(components[])`** → función **determinista** de Python (no llama al LLM).
- *(Opcional)* **`validate_estimate`** → guardrails de S4 sobre la estimación final.

**Stack del enunciado:** OpenAI **Responses API** (`client.responses.create`) con **gpt-5**,
`reasoning={"effort":"medium"}`. Todo el código **en inglés**. Material en la rama `session_12`
del profesor: `sample_transcript_simple/complex.txt`, `reference_retrieval.py` (stub), y
`calculate_estimate_skeleton.py`.

**El bucle (conducido a mano):** llamas a `responses.create` con system prompt + transcripción
+ tools → recorres `response.output` buscando items `function_call` → ejecutas la función con
sus `arguments` → devuelves un `function_call_output` con el **mismo `call_id`** → re-llamas
encadenando con `previous_response_id` → repites mientras haya `function_call`; sales cuando el
modelo da la respuesta final. **Condición de parada** (`MAX_STEPS`) obligatoria.

**Criterios de aceptación** (con `sample_transcript_complex.txt`): identifica **>1 componente**
y hace **>1 llamada a `search_budgets`**, llama a `calculate_estimate`, **termina solo**,
produce estimación estructurada coherente, y la **traza** muestra por paso razonamiento +
acción + observación.

**Entrega:** rama `session-12/pre-work` + PR + email a george@lidr.co (a Lía la traza). Deadline pasado.

**Coste:** depura el bucle con **gpt-5-mini + transcripción simple**; ejecuta la compleja con
**gpt-5 medium**. Objetivo: < un par de dólares.

## 2. Las 6 lecciones (resumen; detalle en `material_curso/`)

1. **[De pipeline a agente](material_curso/01-de-pipeline-a-agente.md)** — taxonomía **tarea → workflow → agente**; la única diferencia real es *quién elige el siguiente paso* (tú en el workflow, el modelo en el agente); el agente solo compra **orquestación adaptativa** (para problemas cuyo árbol de decisión no puedes pre-mapear), y se paga en latencia/coste/no-determinismo. Por defecto, pipeline.
2. **[Anatomía de un agente](material_curso/02-anatomia-de-un-agente.md)** — órganos del bucle: **razonamiento, planificación, acción, observación, handover** + **condición de parada** + **estado que crece**. La observación de calidad (y los errores como observación) gobierna la siguiente decisión.
3. **[Function calling en la práctica](material_curso/03-function-calling.md)** — el modelo **no ejecuta tu código**: pide, ejecutas tú. Anatomía de una tool (nombre/descripción/parámetros/`strict:true`). **Responses API = schema plano** (`type`/`name`/`parameters` al mismo nivel; NO anidado bajo `function` como en Chat Completions). `call_id`, `previous_response_id`, llamadas en paralelo (`asyncio.gather`).
4. **[El bucle agéntico paso a paso](material_curso/04-bucle-agentico.md)** — el agente entero en **~50 líneas**: `TOOL_REGISTRY` con `try/except`, bucle con `asyncio.gather`, traza, `MAX_STEPS`, `text_format=Estimate` (salida estructurada determinista aunque el camino no lo sea), endpoint FastAPI. **Es la implementación de referencia del ejercicio.**
5. **[Patrones de agentes y diseño de tools](material_curso/05-patrones-y-tools.md)** — ejes: un-paso/iterativo, reactivo/proactivo, plan-fijo/dinámico; **enrutar la forma por caso** (simple→pipeline, complejo→agente). Y la palanca clave: las **descripciones de tools son prompts que se iteran leyendo trazas**.
6. **[Cuánto cuesta un agente](material_curso/06-cuanto-cuesta.md)** — 4 fuentes de sobrecoste (más llamadas, **contexto que crece = dominante**, tokens de razonamiento, exploración); la cuenta ~5-6× vs pipeline; medir con un `CostLedger` desde `usage`; palancas: **enrutar, adelgazar contexto, acotar la cola (p95), ajustar modelo/razonamiento, cachear**.

## 3. El directo (resumen de la grabación)

Impartió **Julián**. Slides: `Sesión 12 - Introducción a agentes de IA.pptx`. Q&A + consejos:
- **Context/Loop/Graph engineering** se **solapan**, no son excluyentes; los grafos se ven en la **S13** (LangGraph).
- **Producción**: se ve más construir servicios agénticos con **LangChain/LangGraph + Python** integrados en el software, que grandes sandboxes de agentes. **Python** = recomendación fuerte, no requisito.
- **Aislar permisos de agentes**: contenedor independiente por agente, limitando permisos/recursos (enlaza con la orquestación de LangGraph).
- **Rosa (clave):** ¿siempre conviene pasar a agéntico? **No** — no metas IA por hype donde ya hay una solución determinista simple y eficaz; úsala cuando resuelva algo incómodo/difícil/costoso en tiempo humano. La decisión no siempre es técnica (cómo quieren interactuar los usuarios).
- **Consejos:** conceptos antes que implementación; agentes solo donde aporten; **validación humana en procesos sensibles**; diseño conservador para reducir alucinaciones; ni un agente que lo haga todo ni demasiados agentes; el bucle a mano es didáctico.

## 4. Conexión con tu Proyecto Final
Esto **es** la "capa de agentes" obligatoria del capstone (el copiloto municipal): un agente que
enruta entre `search_ordenanzas` (RAG S10), `consultar_incidencias` (SQL sobre IRIS) y
`estimar_resolucion` (tu estimador). El bucle a mano de la S12 es la base; **LangGraph (S13)** es
el framework para orquestarlo.

## 5. Estado y ejecución
- **Agente CONSTRUIDO** (Opción B, sobre nuestro repo), reutilizando el retrieval híbrido de
  S10 como tool. Código en [`app/agent/`](../../app/agent): `tools.py` (search_budgets +
  calculate_estimate + validate_estimate, schemas planos de la Responses API), `loop.py`
  (el bucle a mano con `client.responses.parse`, `function_call`/`function_call_output`,
  `call_id`, `previous_response_id`, `MAX_STEPS`, traza y coste), `router.py`
  (`POST /agent/estimate`) y `schemas.py` (`AgentEstimate` + `AgentRun`). Config nueva en
  `app/config.py` (`AGENT_MODEL`, `AGENT_MAX_STEPS`, `AGENT_SEARCH_K`, `AGENT_REASONING_EFFORT`).
- **Tests:** `tests/agent/` (9 tests, sin red ni BBDD; el bucle se prueba con un cliente
  OpenAI falso). Toda la suite en verde (162 passed, 2 skipped de BBDD).
- **Cómo ejecutarlo paso a paso:** ver [`EJECUCION.md`](EJECUCION.md).
- **Entrega:** rama `session-12/pre-work` (deadline del ejercicio ya pasó; se entrega tarde,
  suma al certificado por la vía de ejercicios).
