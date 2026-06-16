# 🎓 Tutorial — Sesión 04: Productos IA avanzados

Esta carpeta explica la sesión 4 conectada al **código de tu repo**. La idea central:
**dejar de delegar el prompting al usuario**. Pasamos el estimador de un *chat* a un
**producto con formulario tipado** y sacamos el prompt del código a **templates Jinja2
versionados**.

> 🔑 El ejercicio de la sesión 4 es **pre-sesión**: se entrega ANTES del directo, en una
> rama `pre-session-04`, por email a `george@lidr.co` (≥2 días antes). Las partes de
> **JSON estructurado, guardrails y cacheo semántico** se hacen **en el directo**, no en el
> entregable (el enunciado avisa de que la solución del directo puede diferir).

## Las 5 capas del módulo y dónde están

| # | Capa | ¿Entregable o directo? | En tu repo |
|---|------|------------------------|-----------|
| 1 | Interfaz de producto (formulario, no chat) | **Entregable** ✅ | `streamlit_app.py` (st.form → POST httpx) |
| 2 | Prompts como artefactos (Jinja2 versionado) | **Entregable** ✅ | `app/prompts/loader.py` + `estimation/v1·v2/*.j2` |
| 3 | Datos estructurados (JSON Schema + Instructor) | Directo 🔜 | (reto — ver abajo) |
| 4 | Guardrails (5 capas, defense in depth) | Directo 🔜 | (reto) |
| 5 | Cacheo semántico (embeddings) | Directo 🔜 | (reto) |

## Qué construimos (el entregable, partes 1-4)

**Parte 1 — Schemas + formulario** (`app/schemas.py`): enums `ProjectType`/`DetailLevel`/`OutputFormat`,
`EstimationRequest` (description 20-2000 + 3 parámetros) y `EstimationResponse` (text + prompt_version
+ metadatos de observabilidad). El `streamlit_app.py` ya **no es un chat**: es un `st.form` que arma el
`EstimationRequest` y hace `POST /api/v1/estimate` con `httpx`. Streamlit es **solo presentación**; la
lógica vive en la API. (Esto resuelve la "duda de topología" de la sesión 3: el enunciado confirma que
Streamlit consume el API.)

**Parte 2 — Prompts versionados** (`app/prompts/`): `loader.py` con `render_estimation_prompt(request,
version="v1")`. Jinja2 con `StrictUndefined` (variable ausente → error claro, no vacío silencioso),
`trim_blocks`/`lstrip_blocks`. Los `.j2` usan **XML tags** y bloques condicionales por `output_format`
y `detail_level`, e incluyen `examples.j2` con `{% include %}`. Hay un `v2/` (bonus) para demostrar el
versionado.

**Parte 3 — Refactor del endpoint** (`app/routers/estimations.py` + `app/services/llm_service.py`):
`POST /estimate` acepta el `EstimationRequest`, renderiza `(system, user)`, llama al **wrapper de la
sesión 03** con los roles separados, y devuelve `EstimationResponse`. Acepta `?prompt_version=v2` (bonus).

**Parte 4 — Tests del template** (`tests/prompts/test_estimation_v1.py`): verifican que el render
contiene la descripción, que `phases_table` mete la keyword del formato y `narrative` no, y que
`detailed` añade la instrucción de asunciones. Corren en milisegundos, sin API.

**Bonus implementados:** `v2/`, `?prompt_version`, campo `reference_projects` (con `{% for %}` en el
template) y logging del prompt renderizado con structlog (versión + hash).

## Cómo ejecutarlo

```bash
# 1) Backend (API)
uv run uvicorn app.main:app --reload          # http://localhost:8000/docs

# 2) Frontend (formulario) — en otra terminal
uv run streamlit run streamlit_app.py         # http://localhost:8501

# 3) Tests (sin API key)
uv run pytest -q                              # 35 tests verdes
```

## Comparación con el repo del profesor (`LIDR-academy/ai-engineering`)

Su rama `session_4` (pre-sesión) tiene **la misma estructura** que nuestro entregable:
`app/prompts/estimation/v1/{system,user,examples}.j2` + `loader.py`, schemas, formulario en
`streamlit_app.py`. Diferencias (ninguna es "más correcta", son opciones):

| | Profesor | Nosotros |
|---|---|---|
| Schemas | paquete `app/schemas/estimation.py` | módulo `app/schemas.py` |
| Inyección deps | `app/dependencies.py` (FastAPI DI) | sin módulo de DI |
| Tests | `test_prompts.py` + `test_schemas.py` | `tests/prompts/test_estimation_v1.py` |
| Observabilidad en respuesta | minimal | añadimos metadatos (model, cache_hit, coste…) |

Su rama `session_4_live` añade lo del directo: `app/guardrails/{input,output}.py`,
`app/cache/semantic.py`, `app/services/estimation.py` (structured outputs) — exactamente los 3 temas reservados.

## Dudas para el profesor
1. ¿La rama de entrega debe llamarse `pre-session-04` exactamente? (su repo usa `session_4`.)
2. ¿Schemas como paquete (`schemas/estimation.py`) o módulo? ¿Esperáis `app/dependencies.py`?
3. ¿El `EstimationResponse` del entregable debe ser minimal (text + prompt_version) o se valoran metadatos extra?

## Retos (los 3 temas del directo, para implementar después)
1. **Datos estructurados** — `EstimationResult` (Pydantic con `phases`, `model_validator` de coherencia) + **Instructor** (`response_model=`). Cambia el contrato a salida tipada.
2. **Guardrails** — `validate_input` (Moderation + patrones de injection) con política *exception*; bloque `<scope>` en `system.j2` con política *filter*; `model_validator` de confianza baja con *fix-retry*.
3. **Cacheo semántico** — `redisvl.SemanticCache` con **cache key compuesta** (bucket determinista + embedding), guardrails ANTES del cache, escritura DESPUÉS de validar.

> Si quieres, los hacemos en una rama aparte (estilo `session_4_live`) para no contaminar la entrega
> `pre-session-04`, igual que en la sesión 3 hicimos los retos tras la entrega.

## Material del curso (teoría fiel)
En [`material_curso/`](material_curso/): [00 intro](material_curso/00-intro.md) ·
[01 interfaz de producto](material_curso/01-interfaz-de-producto.md) ·
[02 plantillas de prompts](material_curso/02-plantillas-de-prompts.md) ·
[03 datos estructurados](material_curso/03-datos-estructurados.md) ·
[04 guardrails](material_curso/04-guardrails.md) ·
[05 cacheo semántico](material_curso/05-cacheo-semantico.md) ·
[EJERCICIO](material_curso/EJERCICIO.md).
