# Sesión 10 — Resultados de recuperación (precisión@5 + latencia)

> Generado por `evals/retrieval/run.py` contra Postgres real (37 chunks), embeddings reales de OpenAI y cross-encoder real. Golden set: 5 consultas. k=5, pool de recall=15, repeticiones de latencia=3 (mediana).

## Tabla comparativa (media sobre el golden set)

| Config | Descripción | Precisión@5 (media) | Latencia media (ms) |
|--------|-------------|--------------------:|--------------------:|
| A | vectorial / sin rerank | 0.920 | 1.7 |
| B | híbrida (RRF) / sin rerank | 0.800 | 3.1 |
| C | vectorial / rerank | 0.920 | 24.0 |
| D | híbrida (RRF) / rerank | 0.920 | 25.8 |

## Precisión@5 por consulta

| Config | Q1 | Q2 | Q3 | Q4 | Q5 |
|--------|------:|------:|------:|------:|------:|
| A | 1.00 | 1.00 | 0.60 | 1.00 | 1.00 |
| B | 0.60 | 1.00 | 0.60 | 1.00 | 0.80 |
| C | 1.00 | 1.00 | 0.60 | 1.00 | 1.00 |
| D | 1.00 | 1.00 | 0.60 | 1.00 | 1.00 |

## Latencia por consulta (ms, mediana de 3)

| Config | Q1 | Q2 | Q3 | Q4 | Q5 |
|--------|------:|------:|------:|------:|------:|
| A | 2 | 1 | 2 | 1 | 2 |
| B | 3 | 4 | 4 | 3 | 3 |
| C | 24 | 23 | 27 | 23 | 23 |
| D | 24 | 23 | 28 | 26 | 27 |
