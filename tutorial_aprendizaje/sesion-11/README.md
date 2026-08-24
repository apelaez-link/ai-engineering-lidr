# Sesión 11 — RAG Avanzado: generación y calidad

> Rama `session-11/pre-work`. Cierra el RAG por el lado del **generador**: subimos la
> citación a **nivel de línea** y la hacemos **verificable por código**, y montamos una
> **evaluación objetiva con RAGAS** sobre el golden set. Deadline del ejercicio: **domingo
> 23 de agosto**.

---

## 0. El gap que había que cerrar primero (Opción B)

El enunciado asume "el generador estructurado de la sesión 9, que ya produce una estimación
en JSON con citación obligatoria". **Nuestro repo no lo tenía**: hicimos la S9 como
**diagnóstico**, no construimos la etapa de generación — llegábamos solo hasta el *retrieval*
(S10). Así que, en **Opción B** (nuestro repo, no el fork), lo primero fue **construir ese
generador** (`app/generation/`): recuperar contexto (reutilizando la S10) → generar una
estimación estructurada → verificar. Sobre esa base se montan las dos partes del ejercicio.

Módulo nuevo `app/generation/`:
- [`schemas.py`](../../app/generation/schemas.py) — `SourceReference`, `EstimateLineItem`, `Estimate`, `CitationReport`.
- [`generator.py`](../../app/generation/generator.py) — prompt de atribución por línea + Instructor (`response_model=Estimate`).
- [`verify.py`](../../app/generation/verify.py) — `verify_citations()` (detección de colgantes).
- [`pipeline.py`](../../app/generation/pipeline.py) — recuperar → generar → verificar.

> Nota de stack: el enunciado usa la Responses API de OpenAI (`client.responses.parse`);
> nosotros usamos **Instructor sobre litellm** (el patrón de salida estructurada de la S04)
> para mantener la abstracción de proveedores del repo. El contrato (JSON estricto tipado)
> es el mismo, y Instructor da el bucle **fix/retry** contra los validadores del schema.

---

## 1. Citación verificable a nivel de línea

**Schema (Parte 1.1).** Cada línea de la estimación transporta sus fuentes:

```python
class SourceReference(BaseModel):
    chunk_id: str; document_id: str; evidence: str   # evidencia VERBATIM

class EstimateLineItem(BaseModel):
    component: str; hours: float; rationale: str
    grounded: bool; sources: list[SourceReference]
```

**Regla de integridad** (validador Pydantic → Instructor reintenta si falla): `grounded=True`
⇒ al menos una fuente; `grounded=False` ⇒ **no puede inventar horas** (`hours=0`) ni traer
fuentes; se marca explícitamente como "sin datos suficientes".

**Prompt de atribución (Parte 1.2).** El modelo debe: citar solo `chunk_id` presentes en el
contexto, **copiar la cifra/span verbatim** en `evidence` (no parafrasear), y marcar
`grounded=false` cuando no hay soporte en vez de estimar a ojo.

**Verificación (Parte 1.3).** `verify_citations(estimate, retrieved_chunk_ids)` recorre las
líneas y marca cada una como **grounded / dangling / insufficient**. Una **citación colgante**
(cita un `chunk_id` que no estaba en el contexto) es una alucinación con apariencia de rigor;
se registra con structlog por `request_id` y se hace visible en el informe. La detección se
prueba con un caso a propósito en [`tests/generation/test_verify.py`](../../tests/generation/test_verify.py).

Ejemplo real (de [`sample_estimate.json`](../../evals/generation/sample_estimate.json)): la
línea "Cart and Checkout: 160h" cita `BUD-2024-045::CART-002` con `evidence="Estimated hours:
160"` — copiado literal del chunk. **0 citaciones colgantes** en las 5 consultas.

---

## 2. Evaluación con RAGAS

**Golden set (Parte 2.1).** Reutilizamos las 5 consultas de la S10 y les añadimos
`ground_truth` (estimación de referencia), fijado con las **horas reales por componente** de
los presupuestos históricos ([`evals/generation/golden_set.py`](../../evals/generation/golden_set.py)).

**RAGAS (Parte 2.2-2.3).** Por consulta damos a RAGAS las 4 entradas (question, answer,
contexts, ground_truth) y calculamos las 4 métricas con juez `gpt-4o-mini` + embeddings
`text-embedding-3-small` ([`evals/generation/run.py`](../../evals/generation/run.py) →
[`REPORT.md`](../../evals/generation/REPORT.md), `results.csv`):

| Consulta | faithfulness | answer_relevancy | context_precision | context_recall |
|----------|-------------:|-----------------:|------------------:|---------------:|
| Q1 | 0.556 | 0.000 | 0.810 | 0.667 |
| Q2 | 0.462 | 0.420 | 0.810 | 0.500 |
| Q3 | 0.600 | 0.545 | 1.000 | 0.500 |
| Q4 | 0.300 | 0.615 | 0.950 | 1.000 |
| Q5 | 0.000 | 0.511 | 1.000 | 0.500 |
| **media** | **0.383** | **0.418** | **0.914** | **0.633** |

Verificación de citaciones: 5/5 consultas sin colgantes (Q2 y Q3 100% grounded; Q1/Q4/Q5 con
alguna línea marcada "insufficient" — el sistema reconoce lo que no puede fundamentar).

---

## 3. Nota sobre los números más llamativos (entregable)

**Lo que más chirría: `faithfulness` media 0,38 pese a 0 citaciones colgantes.** No es una
contradicción — es que **RAGAS y nuestra verificación miden cosas distintas**. `verify_citations`
comprueba la **estructura** (que cada `chunk_id` citado exista y la evidencia sea verbatim), y
ahí salimos limpios. RAGAS `faithfulness` evalúa **todo el texto de la respuesta** —incluyendo
el **resumen ejecutivo**, el **total sumado** y las líneas **"insufficient data"**— y esas
afirmaciones **sintetizadas/meta no aparecen literalmente en ningún chunk**, así que las
penaliza. Dicho de otro modo: RAGAS castiga la síntesis legítima y la **honestidad de marcar
huecos**. `context_precision` alta (0,91) confirma lo de la S10 (el retrieval trae lo relevante
arriba); `context_recall` media (0,63) dice que el `ground_truth` menciona componentes que no
siempre entran en el contexto (recall del retrieval). Y ojo con `answer_relevancy` (Q1=0,0):
RAGAS avisó *"LLM returned 1 generation instead of 3"*, así que esa métrica quedó **degradada y
hay que leerla con cautela**.

**Direcciones para el directo** (esto es el baseline que se extiende en vivo): **content
augmentation** (meter en el contexto lo que hoy vive en la metadata y ordenar/limpiar antes de
generar) y **formatear la respuesta** para que las afirmaciones mapeen 1:1 con las fuentes
subirían `faithfulness` sin sacrificar la honestidad de marcar lo que falta.

---

## 4. Cómo ejecutarlo

```bash
docker compose up -d postgres && uv run alembic upgrade head   # BBDD S8/S10 (37 chunks)
# generación citada + verificación + RAGAS (llamadas reales a OpenAI):
DATABASE_URL=postgresql+asyncpg://estimator:estimator@localhost:5433/estimator \
  uv run python -m evals.generation.run
uv run pytest -q          # 155 tests (los de BBDD/LLM se saltan o mockean)
```

## 5. Qué llevar al directo (lo que pide el enunciado)
- La **tabla RAGAS** de arriba (baseline que extenderemos en vivo).
- El **informe de verificación de citaciones** sobre una estimación real (`sample_estimate.json` + la tabla de la §1).
- La **nota** de la §3 (los números más llamativos).

## 6. Nota honesta (Opción B, continuidad)
Hecho sobre **nuestro repo continuo** y **nuestros datos** (no el fork del profesor). El
generador que el enunciado daba por existente (S9-live) lo **construimos aquí**. Reutiliza el
retrieval de la S10 y la salida estructurada de la S04; lo nuevo es la citación por línea,
`verify_citations` y RAGAS. Todo el código en inglés; la prosa y el golden set, en español/inglés
según pedía el enunciado.
