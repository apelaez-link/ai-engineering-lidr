# 🎓 Tutorial — Sesión 06: Stress test del CAG + fundamentos de data-driven AI

Abre el **Módulo 3 (RAG)**. La sesión tiene dos caras:

- **Ejercicio (pre-sesión, entregable):** *"Stress test del CAG — medir dónde rompe"*. Se
  **instrumenta** el estimador conversacional y se **mide** dónde se degrada antes de aceptar RAG
  como solución. El deliverable es un **reporte con números**, no código de producción.
- **Teoría (5 lecciones):** los **fundamentos de datos** del Módulo 3 (calidad, auditoría,
  extracción, limpieza, PII/GDPR). Deliberadamente **aún no tocan embeddings**.

> 🔑 El deliverable que pide el enunciado son **dos archivos**: `evals/stress/REPORT.md` y
> `evals/stress/results.csv`. Se suben al repo y se manda el link/PR por mail a **george@lidr.co**
> (no capturas, no chat).

---

## ⚠️ El GAP: este ejercicio asume features de la sesión-5-LIVE que nosotros no tenemos

El enunciado da por hecho un punto de partida que es el de la **sesión 5 en directo**:
summarizer acumulativo, **anclas (anchors)**, **tier dinámico**, **Actor-Critic-Boss**, y un
framework de evals con `golden_dataset` + `EstimationService.estimate_conversational()`.

**Nuestra base es `pre-session-05`** (el entregable pre-sesión), que **no** implementó esas
piezas del directo. Decisión tomada (igual que en sesiones anteriores: *construir sobre lo que
tenemos, no sobre lo del directo que no asistimos*):

1. **Construimos el harness de stress como un módulo autónomo** `evals/stress/` (igual que el
   profesor), que mide **lo que SÍ existe**: el endpoint conversacional (`POST
   /api/v1/sessions/{id}/estimate`), la memoria (`ProjectMetadata` + ventana deslizante
   `MAX_HISTORY_TURNS=6`), los adjuntos (Camino B) y la generación estructurada con Instructor.
2. **Mantenemos el contrato completo de 13 campos** de `turn_observed`, pero los que dependen de
   piezas ausentes se emiten con un **valor por defecto explícito y documentado**:

   | Campo | Valor | Motivo |
   |---|---|---|
   | `anchors_count` | `0` | No hay sistema de anclas |
   | `summary_chars` | `0` | No hay summarizer acumulativo |
   | `last_resolved_tier` | `None` | No hay tier dinámico |
   | `cache_hit_kind` | `"none"` | El endpoint conversacional usa Instructor directo, no integra los cachés |

   Así, el día que se implementen esas piezas, **basta rellenar estos campos** y el resto del
   pipeline de medición no cambia. El esquema del CSV y del REPORT es idéntico al de la versión
   "completa".

---

## Qué construimos (mapa de la entrega)

| Bloque | Qué | En el repo |
|---|---|---|
| 1 | Evento `turn_observed` (13 campos) + medición de latencia/tokens/coste | [`app/services/observation.py`](../../app/services/observation.py) + cambios en [`app/routers/sessions.py`](../../app/routers/sessions.py) |
| 2 | 3 perfiles multi-turno (crece / pivota / contradice) con fact-tracker | [`evals/stress/scenarios.py`](../../evals/stress/scenarios.py) |
| 3 | PDFs sintéticos calibrados (5/20/50/100 KB), deterministas | [`evals/stress/fixtures/build_pdfs.py`](../../evals/stress/fixtures/build_pdfs.py) |
| 4 | 3 métricas deterministas (Latency / Cost / MemoryDrift) | [`evals/stress/metrics.py`](../../evals/stress/metrics.py) + [`tests/test_stress_metrics.py`](../../tests/test_stress_metrics.py) |
| 5 | Runner CLI (in-process / `--http`, modo mock) + CSV + REPORT | [`evals/stress/run.py`](../../evals/stress/run.py), [`evals/stress/results.csv`](../../evals/stress/results.csv), [`evals/stress/REPORT.md`](../../evals/stress/REPORT.md) |

**96 tests verdes** (los 83 de la sesión 5 + 13 nuevos de stress).

### Las decisiones de diseño que defenderías en el directo

- **Por qué un evento agregado y no 5 logs sueltos** — parseo del CSV de una pasada, correlación
  trivial `messages_in_window` ↔ `cost_usd`, sin reconciliar timestamps.
- **`turn_index` propio, no `len(history.turns)`** — la ventana deslizante descarta pares
  antiguos, así que ese `len` se satura; usamos `Session.turn_count`, monótono.
- **Latencia con `perf_counter` solo alrededor de la generación** — reloj monótono de alta
  resolución, midiendo la parte cara (no el parseo de adjuntos ni los guardrails).
- **Métricas en `evals/stress/metrics.py` (no en `evals/metrics.py`)** — dependen del shape de
  `turn_observed`, no de `EstimationResult`. Justificado en el módulo y en el REPORT.
- **Determinismo > sofisticación en `MemoryDriftMetric`** — match exacto case-insensitive, nada de
  embeddings ni LLM-as-judge (lo pide el enunciado: ideal para CI y reproducibilidad).
- **El truncado a 2000 chars de `description` es EL hallazgo** — `EstimationRequest.description`
  tiene `max_length=2000`. Con adjuntos grandes el contenido enriquecido lo supera y se trunca:
  por eso medimos el tamaño REAL (`enriched_transcript_chars`) y el efectivo (`tokens_in`) por
  separado — **su divergencia es la señal de que el CAG se rompe silenciosamente.**

---

## 🚨 El REPORT/CSV entregados son SINTÉTICOS (modo mock)

`evals/stress/results.csv` (360 filas) y `evals/stress/REPORT.md` se generaron en **modo mock**:
el runner parchea las costuras que llamarían a litellm/OpenAI por funciones sintéticas, **sin
ninguna llamada real ni coste**. Sirven para validar el *instrumental* (esquema de columnas,
métricas, forma de las curvas), **no** para sacar conclusiones de rendimiento real. El REPORT lo
avisa en su primera línea.

> Los tokens y el coste **sí** se calculan offline con `litellm.token_counter` /
> `litellm.cost_per_token` (deterministas, sin red); solo la latencia es simulada.

### 👉 Cómo regenerar el deliverable REAL (con tu API key)

```bash
cd /Users/adrianpelaez/Documents/AIEngineering/ai-engineering-lidr-s06   # o tu checkout de pre-session-06

# 1) Servidor con una API key real en .env (OPENAI_API_KEY o ANTHROPIC_API_KEY)
uv run uvicorn app.main:app --reload

# 2) En otra terminal, runner en modo HTTP contra ese servidor:
uv run python -m evals.stress.run \
    --http http://localhost:8000 \
    --scenarios growing,pivot,contradiction \
    --attachment-sizes 0,5,20,50,100 \
    --repeats 3 \
    --output evals/stress/results.csv
```

Esto hará **decenas de llamadas reales al LLM** (coste real, modesto pero no nulo). Con el nuevo
`results.csv`, recalcula las tablas del REPORT (latencia real, coste real del modelo configurado).
**La estructura del REPORT no cambia; cambian los números.**

> Si solo quieres ver el harness funcionando sin coste: `uv run python -m evals.stress.run`
> (in-process, mock automático si no hay API key) regenera el CSV/REPORT sintéticos.

---

## Lectura del REPORT sintético (la forma de las curvas)

Aun siendo sintético, el REPORT ya enseña los **dos puntos de ruptura** que el directo (RAG)
viene a resolver:

1. **Adjuntos grandes → truncado silencioso.** `enriched_transcript_chars` crece de 16 K a 398 K,
   pero `tokens_in` se **congela en ~2 611** desde los 5 KB: el modelo deja de ver el 99% del
   adjunto y aun así devuelve 200 y una estimación con buena pinta. Sin la instrumentación, este
   fallo es invisible.
2. **Memoria conversacional → coste con techo + deriva.** El coste por turno sube linealmente
   hasta el turno 7 y se **aplana en el turno 8** cuando la ventana (`MAX_HISTORY_TURNS=6`)
   empieza a tirar lo antiguo: el coste deja de crecer **a cambio de olvidar**. En el escenario
   `contradiction` la memoria ya pierde el nombre del proyecto en el turno 2 (el extractor no lo
   fijó como hecho duradero).

Esos dos puntos son justo lo que reforzarían **anchors + summarizer + tier** (las piezas del GAP).

---

## Cómo ejecutarlo

```bash
uv sync                                              # instala (añade fpdf2)
uv run pytest -q                                     # 96 tests, sin API key (todo mockeado)
uv run python -m evals.stress.run --help             # ver opciones del runner
uv run python -m evals.stress.run                    # CSV/REPORT sintéticos (in-process, mock)
```

---

## Comparación con el repo del profesor (`session_06`)

Misma estructura de harness: `evals/stress/{run,scenarios,metrics}.py`, `fixtures/build_pdfs.py`,
`tests/test_stress_{metrics,runner}.py`, `REPORT.md` + `results.csv`. Diferencias por nuestra base:

- El profesor parte de la sesión-5-LIVE completa, así que sus `anchors_count`/`summary_chars`/
  `last_resolved_tier` llevan datos reales; los nuestros van a los defaults documentados (GAP).
- Su `turn_observed` se emite en `EstimationService.estimate_conversational()`; el nuestro, en el
  router `sessions.py` (no extrajimos un servicio de estimación en pre-session-05).
- Las 5 lecciones teóricas de la sesión 6 **no requieren código en el entregable** (el ejercicio
  es el stress test). Las recogemos fielmente en `material_curso/` porque preparan el Módulo 3.

---

## Material del curso (teoría fiel)

[00 intro](material_curso/00-intro.md) ·
[01 calidad del dato y arquitectura](material_curso/01-calidad-del-dato.md) ·
[02 auditoría e inventario](material_curso/02-auditoria-inventario.md) ·
[03 pipeline de extracción](material_curso/03-pipeline-extraccion.md) ·
[04 limpieza y validación](material_curso/04-limpieza-normalizacion.md) ·
[05 PII y GDPR](material_curso/05-pii-gdpr.md) ·
[✍️ EJERCICIO](material_curso/EJERCICIO.md).
