# ✍️ Ejercicio (pre-sesión): Stress test del CAG — "medir dónde rompe"

> Material del curso LIDR · AI Engineering · Sesión 6 (Antonio Pérez). Enunciado fiel del ejercicio.

## Guía del ejercicio

Hasta la sesión 5 construimos un CAG (Cache-Augmented Generation): cada turno inyecta
`[summary] + anchors + ventana_deslizante + ProjectMetadata + tier + transcript + texto_adjuntos`.
Todo cabe en el contexto **por construcción**. Funciona mientras los proyectos son cortos.

**Nunca lo hemos puesto a prueba en serio.** No sabemos a qué turno empieza a olvidar el nombre
del proyecto, ni cuánto cuesta el turno 10 frente al 1, ni a qué tamaño de adjunto la latencia
P95 supera el SLA. El módulo 3 (sesión 6 en directo) introduce RAG como respuesta; pero el alumno
tiene que **ver con sus propios datos** qué limitación existe antes de aceptar la solución.

Este ejercicio es ese trabajo: **instrumentas tu CAG, lo sometes a tres escenarios de carga,
produces un `REPORT.md`** con tres curvas y dos párrafos de lectura. Llegas al directo con un
**baseline cuantitativo**.

## Objetivos de aprendizaje

Al terminar deberías poder defender:

1. La diferencia entre **fallar duro** (el esquema rompe, el CI te avisa) y **degradar
   silenciosamente** (el recall baja del 90 al 60% sin ningún test rojo). Cuál es más peligroso.
2. Cómo **extender un framework de evals** sin reescribirlo (`MetricResult` + `run_all_metrics`).
3. Por qué los **presupuestos** (token/latency/cost budget) son **contratos de diseño**, no
   banderas a observar a posteriori. `LatencyBudgetMetric(budget_ms=4000)` convierte el SLA en test.
4. Las **tres curvas canónicas** de cualquier sistema basado en contexto: latencia vs tokens,
   coste acumulado vs turnos, recall de hechos vs longitud del historial.
5. Cuándo "el contexto está lleno" no es un error del LLM sino una **decisión arquitectónica**: el
   momento exacto en que CAG empieza a perder frente a RAG.

## Los 5 bloques (el deliverable es un reporte con números, no código de producción)

**Bloque 1 — Unificar la observación por turno.** Emitir un único evento `turn_observed` con 13
campos: `turn_index`, `session_id`, `enriched_transcript_chars`, `attachments_total_chars`,
`messages_in_window`, `anchors_count`, `summary_chars`, `tokens_in`, `tokens_out`, `cost_usd`,
`latency_ms`, `cache_hit_kind` (`none`/`exact`/`semantic`), `last_resolved_tier`. La mayoría ya
circula en logs sueltos; el trabajo es **agregarlos** justo antes del `return`.

**Bloque 2 — Escenario sintético multi-turno** (`evals/stress/scenarios.py`). Conversaciones de
N turnos (N ∈ {1,3,6,10,20}). Tres perfiles + un **fact-tracker** por turno:
- **Crece** — se añaden requisitos coherentes. ¿Sobrevive `project_name` al turno 20?
- **Pivota** — el turno 5 cambia el stack. ¿La metadata se actualiza o acumula ambas tecnologías?
- **Se contradice** — turno 3 dice 30k€, turno 8 dice 80k€. ¿Cuál se preserva / promueve a ancla / acaba en summary?

**Bloque 3 — Escenario de adjuntos grandes.** PDFs sintéticos calibrados: 0 / 5 / 20 / 50 / 100 KB
(cerca del cap `MAX_ATTACHMENT_CHARS=60.000`, midiendo cómo trunca). Misma estimación, el stress
está en el adjunto. Mide latencia, coste y recall del contenido del adjunto.

**Bloque 4 — Tres métricas nuevas.** Reusando `MetricResult` (name, score, passed, details):
- `LatencyBudgetMetric(budget_ms)` — 1.0 si `latency_ms ≤ budget_ms`.
- `CostBudgetMetric(budget_usd)` — 1.0 si `cost_usd ≤ budget_usd`.
- `MemoryDriftMetric(fact, where=["summary","anchors","metadata"])` — 1.0 si el fact del turno k
  aparece en el snapshot del turno N>k. **Determinismo > sofisticación**: match exacto
  case-insensitive, nada de embeddings ni LLM-as-judge.

**Bloque 5 — Runner + reporte.** `evals/stress/run.py` orquesta (escenarios × tamaños × repeticiones
× turnos), vuelca `results.csv` (una fila por turno + columnas de las métricas). Sobre el CSV se
escribe `REPORT.md`: tabla resumen (P50/P95 latencia, coste acumulado, hit rate cachés, recall
medio), las tres curvas (como tablas Markdown), y **dos párrafos** de "dónde empieza a romperse mi
CAG y por qué".

## Lo que NO entra

Implementar RAG (es el directo) · optimizar el CAG (el ejercicio mide, no optimiza) · comparar
proveedores · notebook Jupyter con matplotlib · persistir a Postgres/SQLite · LLM-as-judge para
`MemoryDriftMetric` · UI nueva. **No habrá rama `solutions/session-06`**: cada alumno produce un
reporte distinto; la lectura ejemplar se enseña en directo.

## Criterios de "hecho"

- Cada `POST /sessions/{id}/estimate` emite `turn_observed` con los 13 campos.
- `uv run python -m evals.stress.run --http http://localhost:8000` corre end-to-end y deja un CSV
  con ≥ 50 filas.
- `LatencyBudgetMetric`, `CostBudgetMetric`, `MemoryDriftMetric` con tests unitarios verdes.
- `REPORT.md` con tabla resumen, tres curvas y dos párrafos con **al menos una afirmación
  cuantitativa concreta** ("a partir del turno N=12 el recall del project_name cae bajo el 60%" /
  "el coste del turno 20 multiplica por X.X el del turno 1").
- Todo en el repo. **El reporte es el deliverable.**

## Entrega

> Debes entregar: **`evals/stress/REPORT.md`** y **`evals/stress/results.csv`**.
> Formato: subir los archivos al repositorio + compartir el link al repo o Pull Request por mail
> a **george@lidr.co**. NO se aceptan: capturas, documentos sueltos, mensajes por chat.
