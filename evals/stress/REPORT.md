# Stress test del CAG — "medir dónde rompe" (sesión 06)

> ## DATOS REALES (llamadas reales al LLM)
>
> Este informe se ha generado con **llamadas reales** al modelo **`gpt-4o-mini`** (proveedor
> OpenAI, resuelto por `provider_fallback_order`), no en modo mock. Cada turno hace 2 llamadas
> reales (generación estructurada con Instructor + extractor de metadatos), por lo que la
> **latencia es real** y el **coste es real** (calculado con `litellm.cost_per_token`).
>
> - **Ejecución:** runner in-process (`TestClient`) con `.env` y API key reales — la latencia se
>   mide con `perf_counter` **dentro del router**, así que es idéntica a la de `--http`.
> - **Muestra:** 3 escenarios × 5 tamaños de adjunto (0/5/20/50/100 KB) × 3 repeticiones × 8 turnos
>   = 360 turnos teóricos; **355 filas** reales (5 turnos se saltaron tras agotar reintentos por
>   errores transitorios de la API — el runner es resiliente y **no aborta** por ellos).
> - **Coste real total de esta ejecución:** **$0.1408 USD**.
> - **Presupuestos evaluados:** latencia ≤ 4000 ms/turno, coste ≤ 0.02 USD/turno.
>
> ### Cómo reproducirlo
>
> ```bash
> # 1) .env con OPENAI_API_KEY (o ANTHROPIC_API_KEY) en el worktree.
> # 2a) in-process (lo usado aquí; un solo proceso, sin servidor):
> uv run python -m evals.stress.run \
>     --scenarios growing,pivot,contradiction \
>     --attachment-sizes 0,5,20,50,100 --repeats 3 \
>     --output evals/stress/results.csv
> # 2b) o contra un servidor real por HTTP (mismos números, la latencia se mide server-side):
> uv run uvicorn app.main:app --reload            # en otra terminal
> uv run python -m evals.stress.run --http http://localhost:8000 \
>     --scenarios growing,pivot,contradiction \
>     --attachment-sizes 0,5,20,50,100 --repeats 3 --output evals/stress/results.csv
> ```

---

## Adaptación a nuestra base (GAP respecto al enunciado del directo)

El enunciado original asume piezas que en **pre-session-05 no existen** (eran del
DIRECTO de la sesión 5, no implementado): **anclas (anchors)**, **summarizer
acumulativo**, **tier dinámico** y **Actor-Critic-Boss**, además del framework de evals
con `golden_dataset`. Por tanto:

- El harness mide **lo que SÍ existe**: el endpoint conversacional con memoria
  (`ProjectMetadata` + ventana deslizante `MAX_HISTORY_TURNS=6`), adjuntos, generación
  estructurada y cachés.
- Los campos de `turn_observed` que dependen de piezas ausentes se emiten con un valor
  por defecto **explícito y documentado**:
  - `anchors_count = 0` (no hay sistema de anclas),
  - `summary_chars = 0` (no hay summarizer acumulativo),
  - `last_resolved_tier = None` (no hay tier dinámico).
- `cache_hit_kind = "none"` en todas las filas: el flujo conversacional usa Instructor
  directamente y **no integra** los cachés exact/semantic, así que el *hit rate* de
  cachés es **0.00** por construcción (no es un fallo, es el alcance actual).
- `MemoryDriftMetric` busca el `fact` en `["summary","anchors","metadata","history"]`;
  como summary/anchors están vacíos (GAP), la deriva se mide sobre el `ProjectMetadata`
  acumulado y el texto del historial.

---

## 1) Tabla resumen

| Escenario | P50 latencia (ms) | P95 latencia (ms) | Coste acumulado (USD) | Hit rate cachés | Recall medio fact-tracker |
|---|---|---|---|---|---|
| growing | 4490.3 | 15455.5 | 0.046938 | 0.00 | 1.000 |
| pivot | 4250.5 | 14729.7 | 0.047110 | 0.00 | 1.000 |
| contradiction | 7821.5 | 16514.7 | 0.046797 | 0.00 | 0.508 |
| **Global** | **5135.1** | **15917.5** | **0.140844** | **0.00** | **0.837** |

- **Latencia**: P50 global **5.1 s**, P95 global **15.9 s** (máximo observado **38.5 s**). Muy por
  encima del presupuesto de 4 s: **solo el 37.7% de los turnos** entra en presupuesto de latencia.
- **Coste**: ~0.047 USD por escenario (120 turnos c/u en la muestra); **$0.1408 total**. **Ningún
  turno** supera el presupuesto de 0.02 USD/turno (100% dentro) — con `gpt-4o-mini` el coste no es
  el cuello de botella.
- **Hit rate cachés = 0.00**: esperado por el GAP (el endpoint conversacional no cachea).
- **Recall del fact-tracker**: `growing` y `pivot` = **1.000** (memoria perfecta); `contradiction`
  se hunde a **0.508** — la memoria pierde el presupuesto declarado. Global 0.837.

---

## 2) Las tres curvas

### Curva A — Latencia vs `tokens_in` (binned por tamaño de adjunto)

| Tamaño adjunto (KB) | Media `enriched_transcript_chars` | Media `tokens_in` | P50 latencia (ms) | P95 latencia (ms) | % dentro de presupuesto |
|---|---|---|---|---|---|
| 0 | 77 | 948 | 4275.4 | 15351.5 | 46% |
| 5 | 16 167 | 2 760 | 7697.2 | 16110.2 | 33% |
| 20 | 77 270 | 2 775 | 6001.9 | 15108.8 | 35% |
| 50 | 197 690 | 2 763 | 4538.6 | 14831.0 | 46% |
| 100 | 397 945 | 2 757 | 5811.2 | 16215.5 | 30% |

**Lectura clave (el hallazgo más importante del ejercicio):** `enriched_transcript_chars`
(el tamaño REAL que entra por la puerta) crece de 77 a **397 945** caracteres (×5000), pero
`tokens_in` se **estanca en ~2 760** a partir de 5 KB. **El modelo deja de ver el contexto
extra**: la causa es el límite de 2000 caracteres de `EstimationRequest.description`, que
**trunca** el contenido enriquecido antes de componer el prompt. La divergencia
`enriched_transcript_chars` ↔ `tokens_in` es la señal de que el CAG se ha roto en silencio.
Consecuencia colateral en los datos: como el adjunto se trunca, **el tamaño del adjunto casi no
mueve la latencia** (el % dentro de presupuesto no cae monótonamente: 46%→33%→35%→46%→30%); la
latencia la domina la variabilidad propia del LLM (y los arranques en frío), no el contexto —
porque el contexto, de hecho, nunca crece más allá del tope.

### Curva B — Coste acumulado vs `turn_index` (escenario `growing`, media sobre tamaños/repeticiones)

| Turno | Coste medio del turno (USD) | Coste acumulado (USD) |
|---|---|---|
| 1 | 0.000169 | 0.000169 |
| 2 | 0.000238 | 0.000407 |
| 3 | 0.000306 | 0.000713 |
| 4 | 0.000372 | 0.001085 |
| 5 | 0.000441 | 0.001526 |
| 6 | 0.000512 | 0.002038 |
| 7 | 0.000606 | 0.002643 |
| 8 | 0.000607 | 0.003251 |

**Lectura:** el coste por turno **sube monótonamente** del turno 1 al 7 (de 0.000169 a
0.000606 USD) porque cada turno reenvía un historial más largo (más memoria = más tokens de
entrada). El **turno 8 se aplana** (0.000607 ≈ 0.000606): la **ventana deslizante**
(`MAX_HISTORY_TURNS = 6`) ha empezado a descartar los pares más antiguos, así que el contexto
deja de crecer. El "impuesto de memoria" del CAG tiene techo gracias a la ventana — a costa de
**olvidar** lo más antiguo. En términos absolutos, el turno 8 cuesta **×3.60** el turno 1.

### Curva C — Deriva de memoria (recall) vs `turn_index`, por escenario

| Turno | growing | pivot | contradiction |
|---|---|---|---|
| 1 | 1.000 (Helios) | 1.000 (Django) | 1.000 (Atlas) |
| 2 | 1.000 (Helios) | 1.000 (Django) | 1.000 (Atlas) |
| 3 | 1.000 (Helios) | 1.000 (Django) | 1.000 (30k) |
| 4 | 1.000 (Helios) | 1.000 (Django) | **0.000 (30k)** |
| 5 | 1.000 (Helios) | 1.000 (Go) | **0.000 (30k)** |
| 6 | 1.000 (Helios) | 1.000 (Go) | **0.067 (30k)** |
| 7 | 1.000 (Helios) | 1.000 (Go) | **0.000 (30k)** |
| 8 | 1.000 (Helios) | 1.000 (Go) | 1.000 (80k) |

**Lectura:**
- **growing**: recall perfecto (1.000). El nombre `Helios`, fijado en el turno 1, sobrevive en
  `ProjectMetadata.project_name` toda la conversación.
- **pivot**: recall perfecto. La memoria **adopta el cambio de stack** en el turno 5 (el fact
  rastreado pasa de `Django` a `Go` y se sigue encontrando). El extractor incorpora la tecnología
  nueva; el ejercicio no penaliza "olvidar" la vieja tras un pivote (es lo deseado).
- **contradiction**: aquí está la **deriva real**. El presupuesto `30k`, declarado en el turno 3,
  se encuentra ese mismo turno pero **desaparece de la memoria en los turnos 4–7** (recall ≈ 0):
  el extractor no lo promueve a un hecho duradero de `ProjectMetadata`, y como no hay
  summarizer/anclas (GAP), no queda dónde persistirlo. En el turno 8 la corrección a `80k` vuelve
  a encontrarse (recién dicha). Recall del escenario: **0.508** — la mitad del tiempo el sistema
  "no se acuerda" de la cifra que el cliente fijó.

---

## 3) ¿Dónde empieza a romperse el CAG? (lectura)

Con datos reales, el primer punto de ruptura es **la latencia, y se rompe desde el turno 1**. El
presupuesto conversacional razonable (< 4 s) **se incumple en el 62% de los turnos** (P50 global
5.1 s, P95 15.9 s, pico de 38.5 s), y lo hace **incluso sin adjunto**: a 0 KB solo el 46% de los
turnos entra en presupuesto. Es decir, el problema de latencia **no** lo causa el tamaño del
contexto — de hecho la Curva A demuestra que el contexto ni siquiera crece, porque el campo
`description` se trunca a 2000 caracteres y `tokens_in` se congela en ~2 760 desde los 5 KB
mientras el adjunto real llega a 398 000 caracteres. Ese truncado es el segundo modo de ruptura, y
es **silencioso**: el endpoint devuelve 200 y una estimación con pinta razonable ignorando el 99%
del documento. Sin comparar `enriched_transcript_chars` contra `tokens_in`, sería invisible. La
conclusión de ingeniería: antes de aceptar adjuntos grandes, el CAG necesita **resumen/anclaje** del
contexto (las piezas del GAP: summarizer + anchors), no un truncado ciego; y la latencia del propio
modelo ya exige una estrategia (streaming, modelo más rápido, o trocear el trabajo) para cumplir un
SLA conversacional.

El coste, en cambio, **no** es el cuello de botella *con este modelo*: 100% de los turnos dentro del
presupuesto de 0.02 USD y $0.14 por las 355 conversaciones-turno. Pero la Curva B enseña la
dinámica que sí escala: el coste por turno crece linealmente con el historial hasta el turno 7
(×3.60 respecto al turno 1) y se estabiliza en el turno 8 cuando la ventana deslizante
(`MAX_HISTORY_TURNS = 6`) empieza a tirar lo antiguo — el coste deja de subir **a cambio de
olvidar**. Y ese olvido no es teórico: la Curva C lo cuantifica en el escenario `contradiction`,
donde el presupuesto que el cliente fija en el turno 3 (`30k`) **se pierde de la memoria en los
turnos 4–7** (recall del escenario 0.508), porque nunca se promueve a un hecho estructurado y no hay
summarizer/anclas que lo retengan. En resumen: **el CAG aguanta las conversaciones que crecen de
forma coherente (recall 1.000) y encaja un pivote de stack, pero se rompe en tres sitios concretos —
latencia por encima del SLA desde el primer turno, truncado silencioso de adjuntos > 5 KB, y deriva
de memoria en hechos que no llegan a `ProjectMetadata`.** Esos tres puntos son exactamente los que
reforzarían las piezas del directo (streaming/modelo, summarizer, anclas) y, más allá, la razón de
saltar a RAG cuando el corpus deja de caber con calidad en el contexto.
