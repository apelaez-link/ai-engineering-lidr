# 01 — Interfaces conversacionales (Streamlit)

> 📚 **Concepto del curso:** [material_curso/01](material_curso/01-interfaces-conversacionales.md)
> 🧩 **Código:** `streamlit_app.py`

## La idea en una frase

Streamlit te da una interfaz de chat con historial y streaming en ~40 líneas de Python, sin
una sola línea de JavaScript. A cambio aceptas su modelo de ejecución particular.

## El concepto que más confunde: la re-ejecución

**Cada vez que el usuario interactúa, Streamlit re-ejecuta el script entero, de arriba a abajo.**
No hay callbacks ni componentes con estado propio: el script *es* la app, y se vuelve a correr
en cada clic o cada mensaje. Consecuencia directa: cualquier dato que quieras conservar entre
interacciones (el historial del chat) **debe vivir en `st.session_state`**, no en variables
normales (que se reinician en cada re-ejecución).

En `streamlit_app.py` esto son las primeras líneas:
```python
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_meta" not in st.session_state:
    st.session_state.last_meta = None
```

## Recorrido por el código

**Render del historial** (Nivel 1) — en cada re-ejecución repintamos todos los mensajes:
```python
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
```

**Entrada + respuesta en streaming** (Niveles 1 y 2):
```python
if prompt := st.chat_input("Pega aquí la transcripción…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        meta = {}
        history = st.session_state.messages[:-1]          # todo menos el msg recién añadido
        full_response = st.write_stream(
            stream_estimation(prompt, history=history, meta=meta)   # ← generador del wrapper
        )
    st.session_state.messages.append({"role": "assistant", "content": full_response})
```
Tres detalles importantes:
- **`st.write_stream`** consume un generador de fragmentos y los pinta token a token; devuelve
  el texto completo al final (lo guardamos en el historial). Eso es todo el "streaming visual":
  Streamlit resuelve la fontanería.
- **Reutilizamos la lógica del proyecto.** No llamamos a OpenAI/Anthropic aquí; llamamos a
  `stream_estimation`, que pasa por el wrapper. Así la UI hereda **gratis** caché, fallback y
  trazabilidad. El system prompt es exactamente el del endpoint CAG (cumple el requisito del
  ejercicio).
- **`history = messages[:-1]`** porque `stream_estimation` vuelve a añadir el `prompt` como
  turno de usuario internamente. Si pasáramos la lista entera, lo duplicaríamos.

**Panel lateral con contexto CAG** (Nivel 3) — `st.sidebar` con tres bloques:
1. El system prompt activo (`_build_system_prompt()`), en un `text_area` deshabilitado.
2. Los ejemplos CAG inyectados (`ESTIMATION_EXAMPLES`).
3. Métricas de la última llamada (`st.session_state.last_meta`): modelo, tokens, latencia,
   coste, y banderas `⚡ caché` / `🔁 fallback`.

**La API key no está hardcodeada:** `load_dotenv()` carga el `.env` y Pydantic Settings lee de
ahí. Si faltan ambas keys, mostramos un `st.warning` en vez de reventar.

## Por qué Streamlit y no Gradio/Chainlit aquí

Porque el estimador necesita **más que chat**: el sidebar con el contexto CAG y las métricas.
Ahí Streamlit es lo más natural (Gradio es para demos rápidas; Chainlit para chat de agentes
con auth/persistencia — lo verás en los módulos 4-5).

## Reto

1. **Nivel visible:** abre la app, haz una estimación, y observa el sidebar. Repite la *misma*
   transcripción: la métrica debe mostrar `⚡ caché` y latencia ~0 ms (la caché del wrapper en
   acción, lección 03).
2. **Toca el código:** añade al sidebar un botón "🗑️ Limpiar conversación" que haga
   `st.session_state.messages = []` y `st.rerun()`. Pista: `st.sidebar.button(...)`.
3. **Experimenta con la re-ejecución:** pon un `print("re-ejecutando script")` en la primera
   línea y observa en el terminal cuántas veces se imprime al escribir un mensaje. Entenderás
   por qué el estado va en `session_state`.
