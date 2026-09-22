# Sesión 12 — Cómo ejecutarlo paso a paso

Guía para **correr el agente** que construimos (Opción B, sobre nuestro repo) y **entender
qué hace en cada paso**. El código vive en [`app/agent/`](../../app/agent): `tools.py`
(las tools), `loop.py` (el bucle a mano sobre la Responses API), `router.py` (el endpoint)
y `schemas.py` (la salida estructurada + la traza).

> Repasa la teoría en [`README.md`](README.md) y [`material_curso/`](material_curso) antes o
> después de ejecutar — sobre todo la lección 4 (el bucle) y la 3 (function calling).

---

## 0. Requisitos previos

- **`OPENAI_API_KEY`** en tu `.env` (la Responses API es de OpenAI; se usa el SDK directo).
- **Docker** para levantar Postgres (igual que en S8/S10).
- **Acceso a gpt-5** (el enunciado lo pide). **Si tu cuenta no tiene gpt-5**, no pasa nada:
  el bucle funciona igual con `gpt-4o` — el código detecta que no es modelo de razonamiento
  y omite el parámetro `reasoning`. Verás cómo cambiarlo en el paso 4.

## 1. Tests primero (sin red ni BBDD)

Los tests del bucle usan un cliente de OpenAI **falso** (respuestas guionizadas), así que
no gastan tokens ni necesitan Postgres. Empieza validando que todo está en verde:

```bash
uv run pytest tests/agent -q
```

Deberías ver **9 passed**. Esto ya te demuestra la mecánica: `function_call` → ejecutas la
tool → devuelves `function_call_output` con el mismo `call_id` → encadenas con
`previous_response_id` → terminas en la salida estructurada.

## 2. Levanta Postgres e ingesta los presupuestos

El agente necesita datos históricos para su tool `search_budgets` (envuelve el retrieval
de S10). Levanta la BBDD, aplica migraciones e ingesta los 15 presupuestos de ejemplo:

```bash
# a) Postgres + pgvector (se publica en localhost:5433, ver docker-compose.yml)
docker compose up -d postgres

# b) Migraciones (crea extensión + tablas documents/chunks + columna tsvector + índices)
DATABASE_URL=postgresql+asyncpg://estimator:estimator@localhost:5433/estimator \
  uv run alembic upgrade head
```

## 3. Arranca la API

```bash
uv run uvicorn app.main:app --reload
```

Déjala corriendo en esta terminal. En **otra** terminal, ingesta los datos (idempotente:
puedes re-ejecutarlo sin duplicar):

```bash
uv run python scripts/ingest_sample_budgets.py
```

Deberías ver `✓ BUD-...: chunks=N` para los 15 (o `= ... ya estaba ingestado` si repites).

## 4. Ejecuta el agente sobre una transcripción

Usamos una transcripción real del repo: [`examples/transcripts/01_clear.txt`](../../examples/transcripts/01_clear.txt)
(proyecto de banca móvil con **varios componentes**: OAuth, PSD2, ledger). Es el caso que
cumple los criterios de aceptación (>1 componente, >1 búsqueda).

```bash
# Manda la transcripción al agente. jq solo para leer bonito (opcional).
curl -s -X POST http://localhost:8000/agent/estimate \
  -H "Content-Type: application/json" \
  -d "$(jq -Rs '{transcript: .}' examples/transcripts/01_clear.txt)" | jq .
```

**¿No tienes acceso a gpt-5?** Añade el modelo al body (o pon `AGENT_MODEL=gpt-4o` en el `.env`):

```bash
curl -s -X POST http://localhost:8000/agent/estimate \
  -H "Content-Type: application/json" \
  -d "$(jq -Rs '{transcript: ., model: "gpt-4o"}' examples/transcripts/01_clear.txt)" | jq .
```

**Para depurar barato** mientras trasteas, usa `"model": "gpt-5-mini"` (o `gpt-4o-mini`) y
la transcripción simple. La compleja con `gpt-5 medium` la dejas para la ejecución "de verdad".

## 5. Lee la respuesta: estimación + TRAZA + coste

La respuesta (`AgentRun`) tiene tres partes. Fíjate en cada una:

- **`estimate`**: la estimación estructurada final — `line_items` (componente, horas,
  rationale), `total_hours`, `summary`. Es determinista en forma (el modelo la rellenó por
  `text_format`), aunque el camino para llegar no lo fuera.
- **`trace`**: **lo importante para aprender**. Un elemento por paso del bucle, con:
  - `reasoning`: lo que el modelo "dijo" en ese paso.
  - `tool_calls`: qué tool pidió, con qué `arguments`, y la `observation` que le devolviste.
  Verás cómo **descompone** el proyecto y llama a `search_budgets` **una vez por componente**,
  luego `calculate_estimate` para cuadrar el total, y por fin la respuesta.
- **`cost`**: `steps` (vueltas), `input_tokens`, `output_tokens`, `reasoning_tokens`,
  `total_tokens`. Aquí *ves* la lección 6: el input crece vuelta a vuelta (el contexto se
  arrastra) y ése es el grueso del coste.
- **`stopped_reason`**: `final_answer` (terminó solo) o `max_steps` (tocó el tope).

## 6. Criterios de aceptación (qué debe pasar)

Con `01_clear.txt` y un modelo capaz, comprueba que el agente:

1. Identifica **más de un componente** (auth, PSD2, ledger…).
2. Llama a **`search_budgets` más de una vez** (una por componente) — míralo en la traza.
3. Llama a **`calculate_estimate`** para totalizar.
4. **Termina solo** (`stopped_reason: final_answer`), sin agotar `MAX_STEPS`.
5. Produce una **estimación estructurada coherente** (el total cuadra con las líneas).
6. La **traza** muestra, por paso, razonamiento + acción + observación.

## 7. Experimenta (opcional, para afianzar)

- Prueba la transcripción **ambigua/dura** [`03_hard.txt`](../../examples/transcripts/03_hard.txt)
  (clínica: agenda, FHIR, videoconsulta). Verás al agente lidiar con un alcance abierto.
- Baja `max_steps` en el body (p.ej. `"max_steps": 2`) y observa el cierre forzado
  (`stopped_reason: max_steps_forced_final`).
- Lee la traza y pregúntate: ¿las descripciones de las tools guiaron bien al modelo? Ésa es
  la palanca de la lección 5 — se itera el **texto** de la descripción, no el modelo.

---

## Nota sobre coste

Una ejecución con la transcripción compleja y `gpt-5 medium` cuesta **céntimos**. Depura con
`gpt-5-mini`/`gpt-4o-mini` + transcripción simple, y reserva `gpt-5` para la corrida final.
El objetivo del enunciado: mantenerlo por debajo de un par de dólares.
