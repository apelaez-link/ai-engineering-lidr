# Sesión 11 — Evaluación de la generación (RAGAS + citación)

> Generado por `evals/generation/run.py`. Pipeline real (retrieval S10 + generador citado S11), juez RAGAS gpt-4o-mini. 5 consultas, k de contexto=8.

## Métricas RAGAS por consulta

| Consulta | faithfulness | answer_relevancy | context_precision | context_recall |
|----------|-------------:|-----------------:|------------------:|---------------:|
| Q1 | 0.353 | 0.000 | 0.810 | 0.667 |
| Q2 | 0.538 | 0.406 | 0.804 | 1.000 |
| Q3 | 0.385 | 0.480 | 1.000 | 0.500 |
| Q4 | 0.300 | 0.611 | 0.950 | 1.000 |
| Q5 | 0.000 | 0.511 | 1.000 | 1.000 |
| **media** | **0.315** | **0.402** | **0.913** | **0.833** |

## Verificación de citaciones por consulta

| Consulta | líneas | grounded | dangling | insufficient |
|----------|-------:|---------:|---------:|-------------:|
| Q1 | 10 | 5 | 0 | 5 |
| Q2 | 5 | 5 | 0 | 0 |
| Q3 | 5 | 3 | 0 | 2 |
| Q4 | 3 | 3 | 0 | 0 |
| Q5 | 8 | 5 | 0 | 3 |

**Citaciones colgantes en todo el golden set: 0.** (La detección se valida además con un caso a propósito en `tests/generation/test_verify.py`.)
