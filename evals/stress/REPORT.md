# Stress test del CAG — "medir dónde rompe" (sesión 06)

> ## AVISO: ESTOS NÚMEROS SON SINTÉTICOS (modo mock)
>
> Este informe se ha generado en **modo MOCK**: el runner parchea las costuras que
> llamarían a litellm/OpenAI (generación estructurada, extractor de metadatos y
> moderación) por funciones sintéticas, **sin ninguna llamada real a APIs ni coste**.
> Sirve para validar el *instrumental de medición* (esquema de columnas, métricas,
> curvas) y para enseñar la *forma* de las curvas, **no** para sacar conclusiones de
> rendimiento real. La latencia es simulada; los tokens y el coste se calculan offline
> con `litellm.token_counter` / `litellm.cost_per_token` (deterministas, sin red).
>
> ### Cómo regenerar el deliverable REAL
>
> 1. Arranca el servidor con una API key de verdad en el `.env`:
>    ```bash
>    uv run uvicorn app.main:app --reload   # necesita OPENAI_API_KEY o ANTHROPIC_API_KEY
>    ```
> 2. Lanza el runner en modo HTTP contra ese servidor:
>    ```bash
>    uv run python -m evals.stress.run \
>        --http http://localhost:8000 \
>        --scenarios growing,pivot,contradiction \
>        --attachment-sizes 0,5,20,50,100 \
>        --repeats 3 \
>        --output evals/stress/results.csv
>    ```
>    Con datos reales, la latencia será la de verdad y el coste reflejará el modelo
>    configurado. Vuelve a calcular las tablas de abajo sobre el nuevo `results.csv`.

Muestra: **360 filas** = 3 escenarios x 5 tamaños de adjunto (0/5/20/50/100 KB) x 3
repeticiones x 8 turnos. Presupuestos usados: latencia <= 4000 ms, coste <= 0.02 USD/turno.

---

## Adaptación a nuestra base (GAP respecto al enunciado del directo)

El enunciado original asume piezas que en **pre-session-05 no existen** (eran del
DIRECTO de la sesión 5, no implementado): **anclas (anchors)**, **summarizer
acumulativo**, **tier dinámico** y **Actor-Critic-Boss**, además del framework de evals
con `golden_dataset`. Por tanto:

- El harness mide **lo que SÍ existe**: el endpoint conversacional con memoria
  (`ProjectMetadata` + ventana deslizante), adjuntos, generación estructurada y cachés.
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
| growing | 56.9 | 60.3 | 0.041346 | 0.00 | 1.000 |
| pivot | 56.5 | 60.4 | 0.041540 | 0.00 | 1.000 |
| contradiction | 56.5 | 60.3 | 0.041348 | 0.00 | 0.875 |
| **Global** | **56.7** | **60.3** | **0.124234** | **0.00** | **0.958** |

- **Latencia** (sintética): plana entre escenarios porque, tras el truncado del prompt
  (ver curva A), todos ven un contexto de tamaño similar.
- **Coste acumulado**: ~0.041 USD por escenario (suma de 120 turnos/escenario en la
  muestra). Calculado offline; en real dependerá del modelo.
- **Hit rate cachés = 0.00**: esperado por el GAP (el endpoint conversacional no cachea).
- **Recall del fact-tracker**: `growing` y `pivot` preservan el hecho clave en todos los
  turnos; `contradiction` baja a 0.875 por una pérdida de memoria detectada en el turno 2.

---

## 2) Las tres curvas

### Curva A — Latencia vs `tokens_in` (binned por tamaño de adjunto)

| Tamaño adjunto (KB) | Media `enriched_transcript_chars` | Media `tokens_in` | P50 latencia (ms) | P95 latencia (ms) | % dentro de presupuesto |
|---|---|---|---|---|---|
| 0 | 77 | 820 | 54.3 | 56.3 | 100% |
| 5 | 16 168 | 2 611 | 57.3 | 60.3 | 100% |
| 20 | 77 271 | 2 611 | 57.7 | 60.3 | 100% |
| 50 | 197 691 | 2 611 | 57.2 | 60.3 | 100% |
| 100 | 397 946 | 2 611 | 57.3 | 60.3 | 100% |

**Lectura clave (el hallazgo más importante del ejercicio):** `enriched_transcript_chars`
(el tamaño REAL que entra por la puerta) crece de 16 K a **398 K** caracteres, pero
`tokens_in` se **estanca en 2 611** a partir de 5 KB. Es decir: **el modelo deja de ver
el contexto extra**. La causa es el límite de 2000 caracteres de
`EstimationRequest.description`: el contenido enriquecido se **trunca** antes de
componer el prompt. Por eso medimos el tamaño real (sin truncar) en
`enriched_transcript_chars` y el efectivo en `tokens_in`: su **divergencia** es la señal
de que el CAG ha empezado a "romperse" silenciosamente.

### Curva B — Coste acumulado vs `turn_index` (escenario `growing`, media sobre tamaños/repeticiones)

| Turno | Coste medio del turno (USD) | Coste acumulado (USD) |
|---|---|---|
| 1 | 0.000150 | 0.000150 |
| 2 | 0.000211 | 0.000362 |
| 3 | 0.000268 | 0.000630 |
| 4 | 0.000324 | 0.000954 |
| 5 | 0.000380 | 0.001334 |
| 6 | 0.000437 | 0.001771 |
| 7 | 0.000493 | 0.002264 |
| 8 | 0.000492 | 0.002756 |

**Lectura:** el coste por turno **sube monótonamente** del turno 1 al 7 (de 0.00015 a
0.00049 USD) porque cada turno reenvía un historial más largo (más memoria = más tokens
de entrada). En el turno 8 se **aplana** (0.000492 ≈ 0.000493): la **ventana deslizante**
(`MAX_HISTORY_TURNS = 6`) ha empezado a descartar los pares más antiguos, así que el
contexto deja de crecer. El "impuesto de memoria" del CAG tiene, por tanto, un techo
gracias a la ventana — a costa de **olvidar** lo más antiguo.

### Curva C — Deriva de memoria (recall) vs `turn_index`, por escenario

| Turno | growing | pivot | contradiction |
|---|---|---|---|
| 1 | 1.000 (Helios) | 1.000 (Django) | 1.000 (Atlas) |
| 2 | 1.000 | 1.000 | **0.000 (Atlas)** |
| 3 | 1.000 | 1.000 | 1.000 (30k) |
| 4 | 1.000 | 1.000 | 1.000 (30k) |
| 5 | 1.000 | 1.000 (Go) | 1.000 (30k) |
| 6 | 1.000 | 1.000 (Go) | 1.000 (30k) |
| 7 | 1.000 | 1.000 (Go) | 1.000 (30k) |
| 8 | 1.000 | 1.000 (Go) | 1.000 (80k) |

**Lectura:**
- **growing**: recall perfecto. El nombre `Helios`, fijado en el turno 1, sobrevive en la
  memoria (`ProjectMetadata.project_name`) toda la conversación.
- **pivot**: la memoria **adopta el cambio de stack** en el turno 5 (el fact rastreado
  pasa de `Django` a `Go` y se sigue encontrando). El extractor incorpora la tecnología
  nueva sin que el ejercicio penalice "olvidar" la vieja: es lo deseado tras un pivote.
- **contradiction**: aparece la única **deriva** de la muestra en el **turno 2** (recall
  0.000 para `Atlas`). El nombre del proyecto se mencionó en el turno 1 ("we want Atlas")
  pero el extractor sintético solo lo captura con patrones tipo "project X" / "building X",
  así que en el turno 2 —que no repite el nombre— el hecho no está ni en `ProjectMetadata`
  ni en el transcript de ese turno. A partir del turno 3 el fact rastreado es el
  presupuesto, que sí queda en `agreed_scope`, y en el turno 8 la corrección a `80k` se
  preserva correctamente (la última versión gana). Recall del escenario: 0.875.

---

## 3) ¿Dónde empieza a romperse el CAG? (lectura)

El primer punto de ruptura **no es la latencia ni el coste, sino la entrada de contexto**.
La curva A lo deja claro: a partir de adjuntos de unos **5 KB**, el contenido enriquecido
que de verdad llega al modelo (`tokens_in`) se **congela** mientras el tamaño real del
adjunto sigue creciendo hasta casi medio millón de caracteres. La causa es estructural
—el campo `description` se trunca a 2000 caracteres para caber en el prompt— y es
**silenciosa**: el endpoint devuelve 200 y una estimación con pinta razonable, pero está
ignorando el 99% del documento adjunto. Sin la instrumentación de `turn_observed`
(comparar `enriched_transcript_chars` contra `tokens_in`) este fallo sería invisible.
La conclusión de ingeniería es que, antes de aceptar adjuntos grandes, el CAG necesita una
estrategia de **resumen/anclaje** del contexto (justo las piezas del GAP: summarizer +
anchors), no un truncado ciego.

El segundo eje de degradación es la **memoria conversacional**, y ahí el coste y la deriva
cuentan historias complementarias. La curva B muestra que el coste por turno crece de
forma lineal mientras la conversación cabe en la ventana deslizante, y se **estabiliza en
el turno 8** cuando la ventana (`MAX_HISTORY_TURNS = 6`) empieza a tirar los turnos viejos:
el coste deja de subir, pero **a cambio de olvidar**. La curva C confirma que ese olvido no
es teórico: en `contradiction` la memoria ya **pierde el nombre del proyecto en el turno 2**
porque el extractor no lo fijó como hecho duradero, y solo el dato que llega a
`ProjectMetadata` (el presupuesto, la corrección a `80k`) se conserva con fiabilidad. En
resumen, **el CAG aguanta bien las conversaciones que crecen de forma coherente, encaja
razonablemente un pivote de stack, y empieza a romperse en dos sitios concretos: con
adjuntos grandes (truncado silencioso) y con hechos efímeros que nunca se promueven a
memoria estructurada (deriva).** Esos dos puntos son exactamente los que las piezas del
directo (anchors, summarizer, tier dinámico) vendrían a reforzar.
