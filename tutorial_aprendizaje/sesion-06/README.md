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

## ✅ El REPORT/CSV entregados son DATOS REALES

`evals/stress/results.csv` (**355 filas**) y `evals/stress/REPORT.md` se generaron con **llamadas
reales** a `gpt-4o-mini` (2 por turno: generación + extractor de metadatos). Latencia real, coste
real (**$0.14 total** por las 355 conversaciones-turno). 5 turnos se saltaron por errores
transitorios de la API — el runner es **resiliente** (reintenta + salta, no aborta). El REPORT
detalla los parámetros en su cabecera.

> El runner también tiene **modo mock** (`uv run python -m evals.stress.run` sin API key), útil
> para validar el instrumental sin coste. No es lo entregado: el deliverable son datos reales.

### 👉 Cómo reproducirlo (con tu API key)

```bash
cd ~/Documents/AIEngineering/ai-engineering-lidr-s06   # o tu checkout de pre-session-06
# .env con OPENAI_API_KEY (o ANTHROPIC_API_KEY). in-process (un solo proceso, sin servidor):
uv run python -m evals.stress.run \
    --scenarios growing,pivot,contradiction \
    --attachment-sizes 0,5,20,50,100 --repeats 3 \
    --output evals/stress/results.csv
# equivalente contra servidor real: añade --http http://localhost:8000 con uvicorn levantado.
```

---

## Lectura del REPORT real (los hallazgos)

Los datos reales muestran **tres puntos de ruptura** (más nítidos que en mock, donde la latencia
era simulada):

1. **Latencia por encima del SLA desde el turno 1.** Solo el **37.7%** de los turnos entra en el
   presupuesto de 4 s (P50 global **5.1 s**, P95 **15.9 s**, pico 38.5 s), **incluso a 0 KB de
   adjunto** (46% en presupuesto). El problema es el modelo, no el tamaño del contexto.
2. **Adjuntos > 5 KB → truncado silencioso.** `enriched_transcript_chars` crece de 77 a **398 K**,
   pero `tokens_in` se **congela en ~2 760** desde los 5 KB: el modelo deja de ver el ~99% del
   adjunto y aun así devuelve 200. Como el adjunto se trunca, su tamaño **casi no mueve** la
   latencia (confirma que el cuello no es el contexto).
3. **Deriva de memoria en hechos contradictorios.** `growing`/`pivot` mantienen recall **1.000**;
   `contradiction` cae a **0.508**: el presupuesto `30k` fijado en el turno 3 **desaparece de la
   memoria en los turnos 4–7** porque no se promueve a `ProjectMetadata` y no hay summarizer/anclas.
   Además el coste por turno sube ×3.60 hasta el turno 7 y se aplana en el 8 (ventana deslizante).

El coste **no** es el cuello de botella *con este modelo* (100% dentro de 0.02 USD/turno). Los tres
puntos son justo lo que reforzarían las piezas del directo (streaming/modelo más rápido, summarizer,
anclas) y la razón de saltar a RAG cuando el corpus deja de caber con calidad.

---

## Cómo ejecutarlo

```bash
uv sync                                              # instala (añade fpdf2)
uv run pytest -q                                     # 96 tests, sin API key (todo mockeado)
uv run python -m evals.stress.run --help             # ver opciones del runner
uv run python -m evals.stress.run                    # in-process: real si hay .env con key, mock si no
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
