# ✍️ Ejercicio — Del chat a la interfaz de producto

> Material del curso LIDR · AI Engineering · Sesión 4 (Antonio Pérez). Recuperado de la plataforma.
> **Ejercicio PRE-sesión** (se hace antes del directo).

## Problema de partida
El estimator de la sesión 03 es funcional pero tiene dos problemas de la misma raíz: **el prompting está en manos del usuario** y **el prompt vive como un string en el código**. Antes del directo corregimos ambos: el frontend pasa de chat a **formulario tipado** y el prompt sale del código a **templates Jinja2 versionados**.

## Punto de partida (final de la sesión 03)
- Servicio FastAPI con wrapper de proveedores (OpenAI/Anthropic).
- Cliente Streamlit con chat (textarea + botón).
- Cache exact-match, streaming, observabilidad con structlog.
- Prompt de estimación como f-string dentro del endpoint/wrapper.

## Tareas

### Parte 1 — Schemas y formulario
En `app/schemas.py` (Pydantic v2): enums `ProjectType` (mobile_app, web_saas, internal_tool, data_pipeline), `DetailLevel` (summary, medium, detailed), `OutputFormat` (phases_table, line_items, narrative); `EstimationRequest` (description min 20/max 2000, project_type, detail_level, output_format); `EstimationResponse` (text, prompt_version).
En Streamlit: sustituir el chat por un `st.form` que produce un `EstimationRequest` y hace `POST /estimate`. Requisitos: API key no hardcodeada; el system prompt es el del backend.

### Parte 2 — Estructura de prompts + loader
```
app/prompts/
├── loader.py
└── estimation/v1/{system.j2, user.j2, examples.j2}
```
- `system.j2`: rol, instrucciones, bloque condicional según `output_format`, bloque condicional según `detail_level`, `{% include %}` de examples.j2.
- `user.j2`: envuelve la descripción del usuario.
- `examples.j2`: 2-3 ejemplos few-shot inventados.
- `loader.py`: `render_estimation_prompt(request, version="v1") -> (system, user)`. Jinja2 `Environment` con `StrictUndefined`, `trim_blocks=True`, `lstrip_blocks=True`. La firma permite cambiar de versión sin tocar el resto.

### Parte 3 — Refactor del endpoint
`POST /estimate` acepta `EstimationRequest`, llama a `render_estimation_prompt(request)`, llama al modelo con `role: system` y `role: user` **separados**, y devuelve `EstimationResponse(text, prompt_version="v1")`. Mantén el wrapper de la sesión 03.

### Parte 4 — Test del template
En `tests/prompts/test_estimation_v1.py`, ≥3 tests: (a) el render incluye literalmente `description` dentro de `<project_description>`; (b) con `output_format=phases_table` el system contiene la keyword del formato y con `narrative` no; (c) con `detail_level=detailed` aparece la instrucción de asunciones por fase y con `summary` no. Milisegundos, sin APIs.

## Bonus opcional
- **Versionado real:** crea `v2/` y acepta `?prompt_version=v2` como query param.
- **Contexto de proyectos similares:** campo opcional `reference_projects: list[ReferenceProject] | None` recorrido con `{% for %}`.
- **Logging del prompt renderizado:** structlog en el loader con versión + hash del contenido.

## Lo que NO entra (reservado para el directo)
- Forzar JSON estructurado en la salida (sigue siendo texto libre).
- Validación del output con guardrails.
- Cacheo semántico (el exact-match de la sesión 03 sigue).
> Aviso del enunciado: si los implementas por tu cuenta, la solución del directo puede diferir y tendrás que reconciliar.

## Entregable
- Rama **`pre-session-04`** con todos los cambios.
- README actualizado (cómo se levanta y cómo se ejecutan los tests).
- Captura/GIF de la interfaz (opcional).
- **Enviar el enlace a la rama a `george@lidr.co`** con **≥2 días de antelación** al directo. Las entregas posteriores no entran en la revisión grupal.
