# 04 — Streaming y manejo de respuestas largas

> Material del curso LIDR · AI Engineering · Sesión 3 (Antonio Pérez). Recuperado de la plataforma. (≈18 min)

## El problema de la respuesta monolítica

El usuario pulsa enviar, ve un spinner 5-10 s y de golpe aparece un bloque de texto. Durante
esos segundos no sabe si el sistema procesa, se colgó o perdió conexión. Es el comportamiento
por defecto de una API REST: el servidor genera la respuesta completa y solo entonces la envía.
Funciona con respuestas de milisegundos, mal cuando un LLM tarda segundos.

El **streaming** envía la respuesta fragmento a fragmento, según el LLM la genera. El usuario
ve el texto "escribiéndose" (como ChatGPT/Claude). Aunque el tiempo total sea el mismo, recibe
el **primer token en milisegundos**. Además, puede empezar a procesar/leer antes de que termine.

## Tres mecanismos, un objetivo

### StreamingResponse (chunked transfer) — el más básico
FastAPI envía con `Transfer-Encoding: chunked` (sin `Content-Length`): "te voy enviando
trozos". El servidor usa un generador async; el cliente lee con `response.body.getReader()`.

```python
from fastapi.responses import StreamingResponse

async def generate_estimation(transcription: str):
    stream = client.chat.completions.create(model="gpt-4o-mini", messages=[...], stream=True)
    for chunk in stream:
        content = chunk.choices[0].delta.content
        if content:
            yield content

@app.post("/estimate")
async def estimate(transcription: str):
    return StreamingResponse(generate_estimation(transcription), media_type="text/plain")
```
Clave: `stream=True`. Cada `chunk.choices[0].delta.content` es un fragmento. Cliente:
```javascript
const reader = (await fetch('/estimate', {...})).body.getReader();
const decoder = new TextDecoder();
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  result.innerText += decoder.decode(value);
}
```
**Cuándo:** datos crudos (texto plano, archivos, audio/vídeo) sin estructura. Menor overhead.

### Server-Sent Events (SSE) — el recomendado para LLMs
Un nivel por encima: envía **eventos estructurados** (`data`, `event`, `id`, `retry`),
`Content-Type: text/event-stream`, y el navegador tiene API nativa (`EventSource`). Añade
**estructura y resiliencia**: tipos de evento y reconexión automática (reenvía el último `id`).

```python
from fastapi.sse import EventSourceResponse, ServerSentEvent  # FastAPI ≥ 0.135

@app.post("/estimate/stream", response_class=EventSourceResponse)
async def estimate_stream(transcription: str):
    stream = client.chat.completions.create(model="gpt-4o-mini", messages=[...], stream=True)
    for chunk in stream:
        content = chunk.choices[0].delta.content
        if content:
            yield ServerSentEvent(data=content)
```
(En versiones anteriores necesitabas `sse-starlette`.) Cliente:
```javascript
const es = new EventSource('/estimate/stream');
es.onmessage = (e) => { result.innerText += e.data; };
es.onerror = () => es.close();
```
**Cuándo:** eventos estructurados (texto en `data`, metadatos en `meta`), reconexión
automática, API limpia en cliente. Es el **estándar de facto** para streaming de LLMs y lo que
usan OpenAI y Anthropic en sus APIs.

> Nota de este repo: para no depender de la versión exacta de FastAPI, el endpoint
> `/estimate/stream` implementa SSE con `StreamingResponse(media_type="text/event-stream")` y
> framing manual (`event:` / `data:`), codificando el texto como JSON para que los saltos de
> línea del Markdown no rompan el protocolo. Misma idea, máxima compatibilidad.

### WebSockets — bidireccional
Canal bidireccional y persistente (ambos lados envían en cualquier momento). Handshake HTTP
(`Upgrade: websocket`, `101 Switching Protocols`) y luego frames sobre TCP.
```python
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    while True:
        transcription = await websocket.receive_text()
        stream = client.chat.completions.create(model="gpt-4o-mini", messages=[...], stream=True)
        for chunk in stream:
            if chunk.choices[0].delta.content:
                await websocket.send_text(chunk.choices[0].delta.content)
        await websocket.send_text("[END]")
```
**Cuándo:** comunicación bidireccional real. Más complejo de implementar/testear/escalar; sin
reconexión automática; problemas con load balancers sin sticky sessions.

## Cuál usar para nuestro proyecto

- **En Streamlit:** nada a mano. `st.write_stream()` acepta el stream del SDK y lo renderiza
  token a token. Por eso el ejercicio lo pide.
- **En el endpoint FastAPI (clientes no-Streamlit):** **SSE**. Eventos estructurados,
  reconexión, implementación limpia.
- **WebSockets:** para más adelante (agentes que piden clarificaciones durante tareas largas).

## Streaming con diferentes proveedores

Cada SDK lo hace distinto:
```python
# OpenAI
for chunk in openai_client.chat.completions.create(model="gpt-4o-mini", messages=msgs, stream=True):
    yield chunk.choices[0].delta.content or ""

# Anthropic (context manager + eventos de texto)
with anthropic_client.messages.stream(model="claude-haiku-4-5", messages=msgs, max_tokens=4096) as stream:
    for text in stream.text_stream:
        yield text
```
Otro argumento para la capa de abstracción: con **LiteLLM** la interfaz de streaming es
uniforme (convención OpenAI para todos los proveedores):
```python
from litellm import completion
for chunk in completion(model="gpt-4o-mini", messages=msgs, stream=True):
    yield chunk.choices[0].delta.content or ""
```

## Manejo de respuestas largas

Los modelos tienen límite de tokens de salida. Si la estimación lo excede, se corta a media
frase (peor que no tener estimación). Estrategias:
- **`max_tokens` generoso** — si tus estimaciones son 500-800 tokens, pon 2000 de margen. Solo
  pagas lo que se genera; un máximo alto no cuesta más si la respuesta es corta.
- **Detectar truncamiento** — `finish_reason == "length"` (vs `"stop"`) indica corte; puedes
  pedir continuación o avisar al usuario.
- **Diseñar el prompt** — "genera una estimación concisa de máximo 500 palabras" reduce
  desbordes (no es garantía: los modelos no cuentan palabras con precisión).

Para el Proyecto 1: `max_tokens` generoso + detección de `finish_reason` es suficiente.

## Recursos
- Hassaan Bin Aslam — "Streaming Responses in FastAPI"
- FastAPI Docs — "Server-Sent Events (SSE)"
- Sevalla — "Real-time OpenAI Response Streaming with FastAPI"
