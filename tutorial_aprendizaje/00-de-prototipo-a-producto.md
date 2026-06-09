# 00 — De prototipo a producto

> 📚 **Concepto del curso:** [material_curso/00](material_curso/00-de-prototipo-a-producto.md)

## El salto

En la sesión 02 tenías esto: una petición entra por `/estimate`, el servicio construye el
prompt CAG, llama **directamente** al SDK de OpenAI o Anthropic con un `if/elif`, y devuelve
la estimación. Funciona, pero:

- Si OpenAI se cae, tu producto se para.
- La misma transcripción se paga y se espera dos veces.
- El usuario mira un spinner 10 s sin feedback.
- No sabes qué costó cada llamada ni qué modelo respondió.
- Solo se puede probar con curl/Swagger.

La sesión 03 resuelve cada uno de esos puntos con una capa nueva. La idea rectora:
**introducir un "wrapper" entre tu lógica de negocio y los proveedores**, y colgar de él la
caché, el fallback y la trazabilidad. La interfaz (Streamlit) se sienta encima.

## La arquitectura en capas (mira `app/main.py`)

```
Streamlit / cliente HTTP
        │
        ▼
Router  (app/routers/estimations.py)      ← capa HTTP: valida y delega
        │
        ▼
Servicio CAG (app/services/llm_service.py) ← negocio: prompt + conversación
        │
        ▼
Wrapper (app/services/llm_wrapper.py)      ← ⭐ abstracción + fallback + caché + logging
        │
        ├── Caché (app/cache/llm_cache.py)
        └── LiteLLM → OpenAI / Anthropic
```

`app/main.py` hace dos cosas nuevas respecto a la sesión 02:
1. Llama a `configure_logging()` **antes** de crear la app (para que todo log salga con formato).
2. Usa `lifespan` (patrón moderno) para registrar el arranque.

El resto del módulo es ir bajando por esas capas. Cada lección siguiente es una de ellas.

## Por qué este orden de lecciones

Vamos de fuera hacia dentro: primero **la interfaz** (lo que ve el usuario, el ejercicio
entregable), luego **el wrapper** (abstracción + fallback), después **la caché**, el
**streaming** y por último la **observabilidad**. Así cada pieza se apoya en la anterior.

## Reto

Arranca las dos caras del sistema y compáralas:
```bash
uv run uvicorn app.main:app --reload     # API en http://localhost:8000/docs
uv run streamlit run streamlit_app.py    # UI en http://localhost:8501
```
Lanza la misma transcripción por Swagger y por la interfaz de chat. Fíjate en que en la API
la respuesta llega "de golpe" (verás el JSON con `cache_hit`, `tokens_in`, `cost_usd`…) y en
Streamlit se "escribe" token a token. Es el mismo wrapper por debajo: dos experiencias.

> Si no tienes API key todavía, puedes seguir el tutorial igualmente: los tests
> (`uv run pytest`) mockean el LLM y demuestran cada capa sin gastar un céntimo.
