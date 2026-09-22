# Sesión 13 — Cómo ejecutarlo paso a paso (y la S12 seguida)

Esta rama (`session-13/pre-work`) parte de `session-12/pre-work`, así que **contiene también
el agente de la S12**. Puedes ejecutar **las dos sesiones desde este mismo worktree**
(`ai-engineering-lidr-s13`): el agente a mano (`POST /agent/estimate`) y el grafo de
LangGraph (`POST /graph/estimate`).

El código de la S13 vive en [`app/graph/`](../../app/graph): `state.py` (estado tipado +
reducer), `deps.py`, `build.py` (los 5 nodos + cableado + arista condicional),
`observability.py` (Logfire) y `router.py` (el endpoint).

> Teoría en [`README.md`](README.md). Ejecuta desde **este** directorio
> (`ai-engineering-lidr-s13`), no desde el de la S12.

---

## 0. Requisitos

- **`.env` con `OPENAI_API_KEY`** en este worktree. Si lo tienes en el checkout principal,
  cópialo: `cp ../ai-engineering-lidr/.env .` (ajusta la ruta a donde lo tengas). El `.env`
  está gitignoreado, no se versiona.
- **Docker** para Postgres. El grafo usa el **mismo Postgres** del proyecto (localhost:5433):
  pgvector para la búsqueda y, además, el **checkpointer** crea SUS tablas ahí.
- Las **dependencias de LangGraph ya están instaladas** en este worktree (`uv add langgraph
  langgraph-checkpoint-postgres logfire psycopg[binary,pool]` ya ejecutado). Si algo falla,
  `uv sync`.
- Los nodos LLM del grafo usan **nuestra stack** (litellm + Instructor + gpt-4o-mini): **no
  necesitas gpt-5** para la S13 (a diferencia del agente de la S12, donde es opcional).

## 1. Tests primero (sin red ni BBDD)

```bash
uv run pytest tests/graph tests/agent -q
```

Deberías ver **14 passed** (5 del grafo + 9 del agente). Los del grafo parchean los pasos
LLM y la búsqueda, y ejecutan el grafo entero comprobando el reducer y la arista condicional.

## 2. Levanta Postgres, migra e ingesta (si no lo hiciste ya en la S12)

El volumen de Docker es **compartido**: si ya ingestaste los presupuestos al ejecutar la
S12, la base sigue poblada y puedes **saltarte la ingesta**. Si empiezas de cero:

```bash
docker compose up -d postgres
DATABASE_URL=postgresql+asyncpg://estimator:estimator@localhost:5433/estimator \
  uv run alembic upgrade head
```

## 3. Arranca la API desde ESTE worktree

```bash
uv run uvicorn app.main:app --reload
```

En otra terminal, ingesta los datos si hace falta (idempotente):

```bash
uv run python scripts/ingest_sample_budgets.py
```

## 4. Ejecuta las dos, seguidas

**S12 — el agente a mano** (bucle sobre la Responses API):

```bash
curl -s -X POST http://localhost:8000/agent/estimate \
  -H "Content-Type: application/json" \
  -d "$(jq -Rs '{transcript: ., model: "gpt-4o"}' examples/transcripts/01_clear.txt)" | jq .
```
(usa `"model":"gpt-5"` si tu cuenta tiene acceso; ver la EJECUCION de la S12).

**S13 — el grafo de LangGraph**:

```bash
curl -s -X POST http://localhost:8000/graph/estimate \
  -H "Content-Type: application/json" \
  -d "$(jq -Rs '{transcript: .}' examples/transcripts/01_clear.txt)" | jq .
```

La primera llamada al grafo crea las tablas del checkpointer en Postgres (`setup()`), así
que puede tardar un pelín más.

## 5. Lee la respuesta del grafo

`GraphEstimateResponse` trae:

- **`components`**: en qué componentes descompuso el proyecto (nodo `classify_components`).
- **`n_budget_matches`**: cuánta evidencia acumuló `search_budgets` — este número sale del
  **reducer** `operator.add` (cada componente aportó sus matches sin pisar a los demás).
- **`estimate`**: la estimación citada (la genera el nodo `generate_estimate`, que reusa el
  generador de S11).
- **`status`**: `validated` o `needs_review` — lo decide la **arista condicional** (Nivel 3)
  según la verificación de citaciones.
- **`citation_report`**: el informe de citaciones (grounded/dangling/insufficient).
- **`thread_id`** y **`checkpointer`** (`postgres`): el estado quedó **persistido** bajo ese
  thread_id.

## 6. Prueba la persistencia (checkpointer)

Vuelve a llamar pasando el **mismo `thread_id`** que te devolvió:

```bash
curl -s -X POST http://localhost:8000/graph/estimate \
  -H "Content-Type: application/json" \
  -d "$(jq -Rs --arg tid "graph-XXXX" '{transcript: ., thread_id: $tid}' examples/transcripts/01_clear.txt)" | jq .
```

Puedes inspeccionar las tablas del checkpointer en Postgres:

```bash
docker exec -it estimador-postgres psql -U estimator -d estimator -c "\dt" | grep -i checkpoint
```

Verás tablas `checkpoints`, `checkpoint_writes`, etc. Ésta es la base sobre la que la S14
montará la **pausa y reanudación humana** (`interrupt()`): el estado vive en Postgres, así
que un grafo interrumpido se puede retomar.

## 7. Observabilidad con Logfire (opcional)

Sin token, Logfire corre en local (los spans se crean pero no se exportan). Si quieres ver
el árbol de spans por nodo en la nube de Logfire, crea un proyecto gratis y exporta
`LOGFIRE_TOKEN=...` antes de arrancar la API. Cada nodo abre un span `node: <nombre>`.

## 8. Nivel 3 — ver el enrutado a needs_review

`status: needs_review` aparece cuando la verificación detecta citaciones colgantes o la
estimación no tiene horas fundamentadas. Con datos ingestados y una transcripción del
dominio (banca), lo normal es `validated`; para forzar el otro camino, prueba una
transcripción de un dominio SIN presupuestos históricos (p.ej. algo muy distinto) y observa
cómo la arista condicional te lleva por `needs_review`.

---

## Qué mapea con qué

| Nodo del grafo | Reutiliza |
|---|---|
| `extract_requirements` | LLM (Instructor) sobre la transcripción |
| `classify_components` | LLM (Instructor): agrupa en componentes con su query |
| `search_budgets` | la **búsqueda híbrida RRF de S10** (`hybrid_search`) |
| `generate_estimate` | el **generador citado de S11** (`generate_estimate`) |
| `validate_and_consolidate` | la **verificación de citaciones de S11** (`verify_citations`) |
