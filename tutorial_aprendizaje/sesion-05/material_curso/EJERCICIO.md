# ✍️ Ejercicio — Memoria conversacional y contexto enriquecido

> Material del curso LIDR · AI Engineering · Sesión 5 (Antonio Pérez). **Ejercicio PRE-sesión.**

Convierte el estimator de **transaccional** (una transcripción → una estimación) a **conversacional con memoria + adjuntos**: una conversación iterativa donde el cliente refina el alcance, añade info, sube documentos, y el sistema **recuerda** sobre qué proyecto se habla.

## Punto de partida (final de sesión 04)
Servicio FastAPI con wrapper + caching + streaming + observabilidad; endpoint con parámetros tipados (formulario) + transcripción que devuelve **estimación estructurada validada por schema Pydantic**; templates Jinja2 versionados; **guardrails** sobre la salida; cliente Streamlit con formulario.

## Lo que ENTRA en el ejercicio
1. **Sesión con identificador** — `POST /sessions` crea una sesión vacía y devuelve `session_id`.
2. **Memoria conversacional con ventana deslizante** — el servicio mantiene en memoria del proceso (un dict, sin BBDD) el historial por `session_id`, conservando los últimos N turnos.
3. **`project_metadata` separado del historial** — un dict/Pydantic por sesión con los hechos del proyecto (nombre, equipo asumido, tecnologías, alcance acordado). Se inyecta en el system prompt en cada turno; vive aparte del historial.
4. **Endpoint multi-turno** — `POST /sessions/{session_id}/estimate` acepta transcripción + lista opcional de adjuntos; historial y `project_metadata` se actualizan automáticamente.
5. **Adjuntos** (PDF/Word) en `multipart/form-data`. Eliges UN camino:
   - **Camino A (multimodal directo):** subir el PDF al LLM con la Files API (OpenAI/Anthropic). Menos código, acoplado al proveedor.
   - **Camino B (extracción local):** extraer texto con `pypdf`/`PyMuPDF` (PDF) y `python-docx` (Word), y enviar el texto. Más control, independiente del proveedor, prepara el terreno para RAG (módulo 3).

## Pasos guiados
1. **Modelar el estado** — módulo `sessions` con `ConversationHistory` (ventana deslizante; descarta los más antiguos preservando el system) y `ProjectMetadata` (Pydantic: project_name, assumed_team_size, mentioned_technologies, agreed_scope), dentro de una clase `Session` indexada por `session_id` en un dict en memoria.
2. **`POST /sessions`** → `{"session_id": "<uuid4>"}`.
3. **Adjuntos** en `POST /sessions/{id}/estimate` (multipart: `transcript: str`, `attachments: list[UploadFile]`).
4. **Inyección de `project_metadata`** en el template (bloque `<project_metadata>`, vacío en la 1ª llamada) y **actualización** tras cada respuesta: heurística (regex) **o** extractor LLM (2ª llamada → JSON). Justifica la elección en el README.
5. **Ventana deslizante** en `ConversationHistory`: system invariante; `MAX_TURNS=6` (un turno = par user+assistant); descarta los pares antiguos; `to_messages_list()` devuelve el array listo con el system regenerado desde `project_metadata`.
6. **Cliente** — crear sesión al cargar (guardar `session_id` en `session_state`), campo de transcripción + selector múltiple de ficheros, panel con `project_metadata`, botón "Nueva conversación".
7. **Tests** (pytest + httpx): (a) dos peticiones enlazadas → `project_metadata` se actualiza; (b) un PDF adjunto influye en la estimación; (c) 8 turnos → el historial efectivo nunca supera `MAX_TURNS`.

## Lo que NO entra (se hace en el directo)
Resumen acumulativo / híbrido con **anclas**; **tier dinámico** derivado de contexto en runtime; persistencia entre reinicios; búsqueda web / function calling a BBDD; cualquier pieza de **Actor-Critic-Boss**.

## Criterios de "hecho"
`POST /sessions` devuelve `session_id`; `POST /sessions/{id}/estimate` acepta multipart y devuelve estimación que respeta el schema; tras varios turnos el LLM no "olvida" el proyecto; `project_metadata` se actualiza visiblemente; el historial respeta la ventana; README breve (camino de adjuntos elegido + cómo extraes metadata); tests del paso 7 pasan.

## Entregable
Rama **`pre-session-05`** + README + (opcional) captura/GIF de ≥3 turnos con el panel de metadata. **Enviar el enlace a Lia por WhatsApp o a `george@lidr.co`, ≥2 días antes del directo.**

> En nuestro repo: implementado en `pre-session-05` con **Camino B** + **extractor Instructor**. (El directo ya pasó; esto sirve para ponerse al día y llegar bien a la sesión 6.)
