# Sesión 14 — Cómo ejecutarlo paso a paso (S12 + S13 + S14 seguidas)

Esta rama (`session-14/pre-work`) parte de `session-13/pre-work`, así que este worktree
(`ai-engineering-lidr-s14`) contiene **las tres sesiones**: el agente a mano (S12), el
grafo lineal (S13) y el equipo multi-agente con supervisor + HITL (S14).

El código de la S14 vive en [`app/multiagent/`](../../app/multiagent): `state.py`,
`privileges.py` (privilegio mínimo + auditoría), `build.py` (supervisor + 4 workers +
`human_review`) y `router.py` (arranque + reanudación).

> Teoría en [`README.md`](README.md). Ejecuta desde **este** directorio.

---

## 0. Requisitos (igual que S13)

- `.env` con `OPENAI_API_KEY` en este worktree (`cp ../ai-engineering-lidr/.env .`).
- Docker (Postgres en localhost:5433; el checkpointer y pgvector viven ahí).
- Deps ya instaladas (langgraph/psycopg/logfire). Si acaso, `uv sync`.
- Los agentes usan nuestra stack (litellm + gpt-4o-mini): **no necesitas gpt-5**.

## 1. Tests (sin red ni BBDD)

```bash
uv run pytest tests/multiagent tests/graph tests/agent -q
```

Deberías ver **20 passed** (6 multi-agente + 5 grafo + 9 agente). El test estrella del
equipo comprueba la **pausa humana** (`interrupt`) y la **reanudación** (`resume`).

## 2. Postgres + migración + API + ingesta (salta lo que ya hicieras)

```bash
docker compose up -d postgres
DATABASE_URL=postgresql+asyncpg://estimator:estimator@localhost:5433/estimator \
  uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```
En otra terminal (si la base está vacía):
```bash
uv run python scripts/ingest_sample_budgets.py
```

## 3. Las tres, seguidas

**S12 — agente a mano:**
```bash
curl -s -X POST http://localhost:8000/agent/estimate -H "Content-Type: application/json" \
  -d "$(jq -Rs '{transcript: ., model: "gpt-4o"}' examples/transcripts/01_clear.txt)" | jq .
```

**S13 — grafo lineal:**
```bash
curl -s -X POST http://localhost:8000/graph/estimate -H "Content-Type: application/json" \
  -d "$(jq -Rs '{transcript: .}' examples/transcripts/01_clear.txt)" | jq .
```

**S14 — equipo multi-agente (arranque):**
```bash
curl -s -X POST http://localhost:8000/multiagent/estimate -H "Content-Type: application/json" \
  -d "$(jq -Rs '{transcript: .}' examples/transcripts/01_clear.txt)" | jq .
```

## 4. El human-in-the-loop (lo nuevo de la S14)

La transcripción de banca ronda las **480h**, por encima del umbral de auto-aprobación
(300h por defecto), así que el equipo **para en revisión humana**. La respuesta traerá:

```json
{
  "thread_id": "team-XXXX",
  "awaiting_human_review": true,
  "interrupt": { "reason": "estimate above auto-approval threshold", "total_hours": 480, ... },
  "status": "validated",
  "audit": [ ... quién hizo qué ... ]
}
```

Fíjate en `audit`: verás al **supervisor** enrutando y a cada **worker** actuando con su
tool (búsqueda, cálculo, validación) — la traza de auditoría del Nivel 3.

Ahora **decides como humano** y reanudas con ese `thread_id` (aprobar o rechazar):

```bash
# aprobar (sustituye team-XXXX por el thread_id que te devolvió)
curl -s -X POST http://localhost:8000/multiagent/resume/team-XXXX \
  -H "Content-Type: application/json" -d '{"decision":"approve"}' | jq .
```

La respuesta tras reanudar tendrá `status: "approved"` (o `"rejected"` si mandas
`{"decision":"reject"}`) y `awaiting_human_review: false`. El grafo continuó **exactamente
donde se había parado**, porque su estado estaba persistido en el checkpointer (Postgres).

## 5. Ver el privilegio mínimo en acción

El privilegio mínimo no es un `if` escondido: está declarado en
[`app/multiagent/privileges.py`](../../app/multiagent/privileges.py) y se comprueba con
`enforce_privilege` ANTES de usar cada tool. Compruébalo:

```bash
uv run python -c "from app.multiagent.privileges import enforce_privilege; enforce_privilege('budget_searcher','calculate_estimate')"
```

Lanza `PrivilegeError`: el buscador **no puede** calcular. En los logs de auditoría verás
la línea `agent_action agent=budget_searcher tool=calculate_estimate allowed=False`.

## 6. Experimenta

- Sube el umbral (`MULTIAGENT_REVIEW_THRESHOLD_HOURS=1000` en el `.env`) y verás que la
  misma estimación se **auto-aprueba** sin pasar por revisión humana.
- Rechaza (`{"decision":"reject"}`) y observa `status: "rejected"`.
- Reutiliza un `thread_id` ya cerrado y mira cómo el checkpointer conserva su historial.

---

## Los agentes y su privilegio (resumen)

| Agente | Tool concedida | No puede |
|---|---|---|
| `supervisor` | ninguna (solo enruta) | ejecutar lógica de negocio |
| `requirements_extractor` | ninguna (solo LLM) | tocar presupuestos/estimaciones |
| `budget_searcher` | `search_budgets` | calcular ni validar |
| `estimate_generator` | `calculate_estimate` | buscar ni validar |
| `coherence_validator` | `validate_estimate` | buscar ni calcular |
