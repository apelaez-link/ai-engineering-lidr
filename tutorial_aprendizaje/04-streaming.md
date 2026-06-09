# 04 — Streaming y respuestas largas

> 📚 **Concepto del curso:** [material_curso/04](material_curso/04-streaming.md)
> 🧩 **Código:** `app/routers/estimations.py` (`/estimate/stream`), `app/services/llm_wrapper.py` (`stream`), `streamlit_app.py`

## La idea en una frase

En vez de esperar a la respuesta completa y enviarla de golpe, la mandamos fragmento a
fragmento según el LLM la genera. El usuario ve la estimación "escribiéndose" — el primer token
llega en milisegundos aunque el total tarde lo mismo.

## Dos sitios donde aparece el streaming en este repo

### 1) En Streamlit: lo resuelve el framework
`st.write_stream(stream_estimation(...))`. Le pasas un **generador de strings** y él lo pinta
token a token. No tocas HTTP. Por eso el ejercicio pide Streamlit: el streaming de UI sale gratis.

### 2) En FastAPI: un endpoint SSE para clientes externos
El material compara tres mecanismos:

| Mecanismo | Nivel | Cuándo |
|---|---|---|
| **StreamingResponse** (chunked) | bytes crudos | texto plano/archivos, mínimo overhead |
| **SSE** (text/event-stream) | eventos estructurados (`event`, `data`, reconexión) | **streaming de LLMs en web** (estándar de facto) |
| **WebSockets** | canal bidireccional | chat con ida y vuelta real (agentes) |

Para clientes que no sean Streamlit, elegimos **SSE**. En `estimations.py`:
```python
@router.post("/estimate/stream")
def estimate_stream(request):
    def event_source():
        meta = {}
        for chunk in stream_estimation(request.transcription, history=..., meta=meta):
            yield f"event: token\ndata: {json.dumps({'text': chunk})}\n\n"
        meta.pop("content", None)
        yield f"event: done\ndata: {json.dumps(meta)}\n\n"   # métricas finales
    return StreamingResponse(event_source(), media_type="text/event-stream")
```
Detalle práctico: **codificamos cada fragmento como JSON** dentro de `data:`. El Markdown de la
estimación tiene saltos de línea, y en SSE cada evento termina en línea en blanco — si metieras
el texto crudo, un `\n` rompería el framing. El cliente hace `JSON.parse(event.data)`.

> El material muestra `from fastapi.sse import EventSourceResponse` (FastAPI ≥ 0.135). Aquí
> usamos `StreamingResponse` con `media_type="text/event-stream"` y framing manual para no
> depender de la versión exacta de FastAPI. Misma idea SSE, máxima compatibilidad.

## El generador del wrapper (`LLMWrapper.stream`)

Es el corazón del streaming, y reúne las capas:
```python
def stream(self, system_prompt, conversation, *, meta=None):
    # 1) Caché: si hay hit, devolvemos la respuesta entera de golpe (no hay nada que "escribir")
    if cached: meta.update({**cached, "cache_hit": True}); yield cached["content"]; return
    # 2) Miss: streaming real desde el primer proveedor disponible (con fallback)
    response = litellm.completion(model=..., messages=..., stream=True)
    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            chunks.append(delta)
            yield delta                       # ← el usuario lo ve aparecer
    # 3) Al terminar: estima tokens/coste, loguea, y guarda en caché
    meta.update(asdict(result))
```
Dos cosas que aprender aquí:
- **Caché + streaming:** un cache hit no se "escribe" token a token (ya lo tienes); se devuelve
  entero. Solo el *miss* hace streaming real. Es la interacción que describe el material.
- **Trazabilidad en streaming:** el `usage` no siempre viene en los chunks, así que estimamos
  `tokens_in/out` con `litellm.token_counter` y el coste con `litellm.cost_per_token`. Así no
  perdemos las métricas aunque sea streaming (lo verás en el evento `done`).
- **Metadatos vía `meta`:** un generador no puede `yield` texto y `return` datos a la vez, así
  que el llamante pasa un dict `meta` que se rellena al terminar. Streamlit lo lee para el
  sidebar; el router lo envía en el evento `done`.

## Respuestas largas

Si la estimación excede `max_tokens`, se corta a media frase. Defensas (material): `max_tokens`
generoso (`LLM_MAX_TOKENS` en `.env`), detectar `finish_reason == "length"`, y pedir concisión
en el prompt. Nuestro `LLMResult` guarda `finish_reason`, así que puedes detectar el truncamiento.

## Reto

1. **Velo por terminal (SSE):**
   ```bash
   curl -N -X POST http://localhost:8000/api/v1/estimate/stream \
     -H "Content-Type: application/json" \
     -d '{"transcription":"App de reservas con pagos y notificaciones push."}'
   ```
   Verás `event: token` repetidos y un `event: done` con las métricas.
2. **Cache + streaming:** repite el mismo curl. La segunda vez el evento `done` traerá
   `cache_hit: true` y el texto llegará de una (vino de caché). Conecta esto con la lección 03.
3. **Trunca a propósito:** baja `LLM_MAX_TOKENS=60`, pide una estimación larga y mira
   `finish_reason` en la respuesta JSON de `/estimate`. ¿`"length"`?
