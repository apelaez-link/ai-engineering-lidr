"""Stress test del CAG (sesión 06): "medir dónde rompe".

Idea central de la sesión: un CAG no "se rompe" de golpe; se DEGRADA. A medida que
crece el contexto (más turnos, adjuntos más grandes, requisitos que se contradicen),
suben la latencia y el coste, y la memoria empieza a perder hechos. Este subpaquete
es el instrumental para MEDIR esa degradación de forma reproducible:

  - scenarios.py : perfiles multi-turno (growing / pivot / contradiction).
  - metrics.py   : métricas deterministas (latencia, coste, deriva de memoria).
  - fixtures/    : generador de PDFs sintéticos de varios tamaños.
  - run.py       : runner CLI que orquesta scenarios x tamaños x repeticiones.

No hace EVALS de calidad con LLM-as-judge (eso es de sesiones posteriores): aquí
todo es DETERMINISTA y barato, para poder ejecutarlo en CI sin coste ni APIs.
"""
