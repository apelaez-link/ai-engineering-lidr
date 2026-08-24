# Sesión 11 — Evaluación de la generación (RAGAS + citación)

> Generado por `evals/generation/run.py`. Pipeline real (retrieval S10 + generador citado S11), juez RAGAS gpt-4o-mini. 5 consultas, k de contexto=8.

## Métricas RAGAS por consulta

| Consulta | faithfulness | answer_relevancy | context_precision | context_recall |
|----------|-------------:|-----------------:|------------------:|---------------:|
| Q1 | 0.556 | 0.000 | 0.810 | 0.667 |
| Q2 | 0.462 | 0.420 | 0.810 | 0.500 |
| Q3 | 0.600 | 0.545 | 1.000 | 0.500 |
| Q4 | 0.300 | 0.615 | 0.950 | 1.000 |
| Q5 | 0.000 | 0.511 | 1.000 | 0.500 |
| **media** | **0.383** | **0.418** | **0.914** | **0.633** |

## Verificación de citaciones por consulta

| Consulta | líneas | grounded | dangling | insufficient |
|----------|-------:|---------:|---------:|-------------:|
| Q1 | 6 | 3 | 0 | 3 |
| Q2 | 5 | 5 | 0 | 0 |
| Q3 | 3 | 3 | 0 | 0 |
| Q4 | 8 | 6 | 0 | 2 |
| Q5 | 8 | 5 | 0 | 3 |

**Citaciones colgantes en todo el golden set: 0.** (La detección se valida además con un caso a propósito en `tests/generation/test_verify.py`.)
