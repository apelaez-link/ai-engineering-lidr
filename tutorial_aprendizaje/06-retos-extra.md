# 06 — Retos extra (comparando con el repo del profesor)

> Esta lección no sale del material del curso: nace de **comparar nuestro proyecto con el
> repo de referencia del profesor** (`LIDR-academy/ai-engineering`) y quedarnos con ideas
> útiles, con criterio propio (no porque "lo suyo" sea siempre correcto).

Tras cerrar los 5 patrones de la sesión, añadimos cuatro mejoras. Cada una responde a una
diferencia real que encontramos al comparar.

## 1. Evaluación estructural — `app/services/evaluation.py`
**Qué es:** un chequeo por **regex (sin LLM)** de que la estimación está bien formada
(título, desglose, total, equipo, duración, supuestos) y, lo más valioso, que **la suma de
horas de las tareas cuadra con el total declarado** — caza la mala aritmética del modelo.
Usa el `finish_reason` del mini-reto para detectar truncamiento. Devuelve `score` (0-1) + `issues`.

**Dónde aparece:** `POST /api/v1/estimate` ahora trae un campo `evaluation`, y el sidebar de
Streamlit muestra "✅ Calidad de la estimación".

**Por qué importa:** es la semilla de un *guardrail* de outputs — el tema central de la
sesión 4 ("Guardrails y validación de outputs"). El profesor lo tiene en inglés y con tabla
`Task|Hours|Cost`; nosotros lo adaptamos a **nuestro formato en español** (horas, sin tabla).

## 2. Cliente HTML del SSE — `app/static/sse_demo.html`
Un HTML mínimo que consume `POST /estimate/stream` con `fetch` + un **parser SSE en JS** y
pinta la respuesta token a token. Sirve para *ver* el streaming sin Streamlit.
Montado con `StaticFiles` en `app/main.py` → `http://localhost:8000/static/sse_demo.html`.

**Comparación:** el profesor también tiene un `sse_demo.html`. Su Streamlit es **cliente HTTP**
del API (consume el SSE); el nuestro **importa** el servicio en proceso. Las dos topologías son
válidas (ver dudas para el profesor). Este HTML nos da, además, una forma de probar el SSE de verdad.

## 3. Redis con Docker — `docker-compose.yml`
`docker compose up -d` levanta un `redis:7-alpine`. Con `CACHE_BACKEND=redis` en `.env`, la
caché pasa de memoria a **Redis persistente y compartido**. Así nuestra caché (que por defecto
es en memoria, para arrancar sin infra) puede comportarse como en producción con un comando.

## 4. Tests más duros — `fakeredis` + test del SSE
- `fakeredis` prueba el backend Redis **sin servidor** (drop-in de `redis-py`).
- `tests/test_estimate_stream.py` cubre el endpoint SSE (antes no se testeaba el stream).

## Dudas que quedaron para el profesor
1. ¿Streamlit debe ser **cliente del API** (como él) o vale **importar** el servicio (como nosotros)? El enunciado es ambiguo.
2. ¿Qué se espera tener hecho **antes** del directo? (su rama `session_3` ya trae wrapper/caché).
3. `evaluation.py`: ¿es de la sesión 3 o adelanto de la sesión 4 (guardrails)?

## Reto para ti
Nuestra evaluación es estructural (regex). El siguiente nivel es **LLM-as-judge**: pedir a un
modelo barato que puntúe la *calidad* (realismo, completitud) de la estimación, no solo su
forma. Es exactamente lo que trabajaremos en la sesión 4 — pero puedes intentar un primer
`evaluate_with_llm(text) -> score` reutilizando el wrapper. ¿Cómo evitarías que esa evaluación
dispare el coste en cada petición? (pista: cacheo + muestreo).
