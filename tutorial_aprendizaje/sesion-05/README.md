# 🎓 Tutorial — Sesión 05: Funcionalidades avanzadas

Cierra el módulo CAG. El estimator pasa de **transaccional** (una transcripción → una estimación)
a **conversacional con memoria + contexto enriquecido**, y se le añade disciplina de **evaluación**.

> 🔑 El ejercicio es **pre-sesión** (rama `pre-session-05`, enlace a Lia/`george@lidr.co`). Las piezas
> avanzadas (anclas, tier dinámico, **Actor-Critic-Boss**) se construyen **en el directo**.

## Los 5 pilares y dónde están

| # | Pilar | ¿Entregable o directo? | En tu repo |
|---|-------|------------------------|-----------|
| 1 | Contexto dinámico (adjuntos) | **Entregable** ✅ | `app/attachments/extractor.py` (Camino B) |
| 2 | Memoria ≠ historial | **Entregable** ✅ | `app/sessions/{models,store,metadata_extractor}.py` |
| 3 | Prompts adaptativos (tier) | Teoría / opcional | (material_curso 03) |
| 4 | Testing y evaluación (golden dataset) | Teoría | (material_curso 04) |
| 5 | Actor-Critic-Boss | Directo 🔜 | (reto) |

## Qué construimos (el entregable)

- **`app/sessions/`** — `Session` + `ConversationHistory` (ventana deslizante, `MAX_TURNS=6`, preserva el system, `to_messages_list()`) + `ProjectMetadata` (Pydantic), en un **store en memoria** (`store.py`, dict + uuid4). `metadata_extractor.py` actualiza los hechos con **Instructor** tras cada turno.
- **`app/attachments/extractor.py`** — **Camino B**: extracción local con `pypdf` (PDF) + `python-docx` (Word), concatenada con separadores `--- attachment: <file> ---`.
- **`app/routers/sessions.py`** — `POST /sessions` (uuid) y `POST /sessions/{id}/estimate` (**multipart**: transcript + attachments), registrado en `main.py` bajo `/api/v1`.
- **Inyección de `<project_metadata>`** en `estimation/v1·v2/system.j2` + prompt en `prompts/metadata_extraction/v1/`.
- **Cliente Streamlit conversacional** — crea sesión al cargar, uploader de ficheros, panel de `project_metadata`, botón "Nueva conversación".
- **Tests** — ventana (8 turnos ≤ límite), adjuntos (mock parsers), metadata (mock Instructor), endpoints (multipart, 404).

Parte de **`session-04-live`** (que ya tiene structured outputs + guardrails + cacheo semántico).

## El pipeline del endpoint multi-turno (el orden importa)
```
validate_input (guardrail entrada) → cache (semántico) → render prompt (project_metadata + historial)
→ generar estructurado (Instructor) → validate_output → actualizar historial + project_metadata → responder
```

## Cómo ejecutarlo
```bash
uv run uvicorn app.main:app --reload        # API → /docs (POST /sessions, /sessions/{id}/estimate)
uv run streamlit run streamlit_app.py       # UI conversacional → :8501
uv run pytest -q                            # tests (sin API key)
```

## Comparación con el repo del profesor (`session_5`)
Misma estructura: `app/sessions/{models,store,metadata_extractor}.py`, `app/routers/sessions.py`,
`app/attachments/extractor.py`, `app/prompts/metadata_extraction/v1/`. Su rama `session_05_live`
añade lo del directo (anclas, tier dinámico, Actor-Critic-Boss).

## 💡 Aviso del directo aplicado a nuestro código
En el Q&A, **el extractor de metadatos alucinaba tecnologías inexistentes**. Solución: en el prompt
del extractor, **ejemplo exacto del formato** + constraint *"nunca nombres una tecnología que no haya
aparecido en la transcripción"*. Lo aplicamos en `prompts/metadata_extraction/v1/system.j2`.

## Retos (temas del directo, para implementar después)
1. **Memoria con anclas** — patrones fijos (NDA, deadline, presupuesto) que nunca se descartan del resumen.
2. **Tier dinámico** — inferir el perfil del tono de la conversación (vs estático en BBDD).
3. **Actor-Critic-Boss** — actor genera → critic da feedback estructurado → boss decide (máx. iteraciones), solo en el camino crítico (estimación final).
4. **Golden dataset + DeepEval** — 3 familias de tests (hard/soft/LLM-as-judge) sobre casos curados.

## Material del curso (teoría fiel)
[00 intro](material_curso/00-intro.md) · [01 contexto dinámico](material_curso/01-contexto-dinamico.md) ·
[02 memoria vs historial](material_curso/02-memoria-vs-historial.md) · [03 patrón tier](material_curso/03-patron-tier.md) ·
[04 testing y evaluación](material_curso/04-testing-y-evaluacion.md) · [05 Actor-Critic-Boss](material_curso/05-actor-critic-boss.md) ·
[EJERCICIO](material_curso/EJERCICIO.md) · [🎥 Q&A y consejos del directo](material_curso/DIRECTO-qa-y-consejos.md).
