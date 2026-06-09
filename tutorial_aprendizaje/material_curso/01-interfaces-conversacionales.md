# 01 — Interfaces conversacionales, frameworks y librerías

> Material del curso LIDR · AI Engineering · Sesión 3 (Antonio Pérez). Recuperado de la plataforma. (≈13 min)

## El problema que resuelven estos frameworks

Tienes un endpoint que recibe texto y devuelve una respuesta de un LLM. Funciona, pero la
única forma de probarlo es con curl, Postman o Swagger. Para que alguien no técnico lo use
—o para tener una experiencia de chat decente durante el desarrollo— necesitas una interfaz
web. Construirla desde cero (HTML/CSS/JS) es viable pero tiene coste: estado de la
conversación, streaming visual, entrada de texto, indicadores de carga… **fontanería que ya
está resuelta**. Los frameworks de interfaz para IA permiten crear una UI funcional en
Python puro, sin JavaScript, a menudo en menos de 50 líneas.

## Los tres frameworks principales

### Streamlit (el generalista)
No nació para chatbots sino para dashboards y apps de datos; luego incorporó elementos de
chat (`st.chat_message`, `st.chat_input`). **Concepto más importante: su modelo de
ejecución.** Cada interacción del usuario re-ejecuta TODO el script de arriba abajo. Esto
simplifica el desarrollo (el código se lee como un script secuencial) pero obliga a usar
`st.session_state` para persistir cualquier dato entre interacciones — incluido el historial.

Patrón de chat con streaming (≈25 líneas):

```python
import streamlit as st
from openai import OpenAI

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Escribe tu mensaje"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        stream = client.chat.completions.create(
            model="gpt-4o-mini", messages=st.session_state.messages, stream=True,
        )
        response = st.write_stream(stream)
    st.session_state.messages.append({"role": "assistant", "content": response})
```

`st.write_stream` recibe el stream del SDK y lo renderiza progresivamente — no manipulas
chunks a mano.

- **Fuerte en:** mayor comunidad, ecosistema de componentes más rico (gráficos, tablas,
  mapas, file uploads, sidebars), multipage nativo, deploy gratis en Streamlit Community Cloud.
  La mejor opción si tu app necesita algo más que chat.
- **Limitaciones:** re-ejecución completa dificulta estado complejo; sin procesos en
  background ni websockets persistentes sin workarounds; personalización visual limitada;
  se queda corto para chat en producción con auth/persistencia/threading.

### Gradio (demos de ML)
Del ecosistema Hugging Face. Filosofía input → función → output. `gr.ChatInterface` crea
chatbots rápido. `demo.launch(share=True)` genera una URL pública temporal (72 h) sin
deploy — imbatible para enseñar un prototipo en 5 minutos. Componentes nativos multimodales
(imagen/audio/vídeo). Estado más limitado que Streamlit; sin multipágina nativo.

### Chainlit (chat serio con agentes)
El más joven y especializado: diseñado *exclusivamente* como capa de UI para apps
conversacionales con LLMs. De serie: streaming, threading de mensajes, visualización del
razonamiento del agente, recolección de feedback, autenticación, persistencia de
conversaciones. Usa `async def` (construido sobre asyncio). Integración nativa con LangChain
/ LlamaIndex. Su observabilidad ("cadena de pensamiento" del agente) es su rasgo diferencial.
Incómodo para UIs no conversacionales; librería de componentes pequeña; comunidad reducida.

## Cuándo usar cada uno

- **Streamlit** — cuando tu app necesita más que chat (sidebars, gráficos, formularios), o
  para prototipado rápido. **Es el framework del ejercicio de esta sesión.**
- **Gradio** — demos rápidas, especialmente multimodales o público en Hugging Face.
- **Chainlit** — app de chat seria con agentes (observabilidad, auth, persistencia, threading).
  Se ve en los módulos 4 y 5.

## ¿Y construirlo desde cero?
Cuarta opción: HTML/CSS/JS conectado a tu FastAPI. Tiene sentido cuando necesitas control
total de la UX o el chat es un componente de una app mayor. Ventaja: control absoluto.
Desventaja: implementas tú el estado, el rendering, el streaming visual (SSE/WebSockets),
los loaders… Para producción con requisitos específicos suele ser la mejor a largo plazo;
para validar rápido, los frameworks ahorran tiempo.

## Recursos
- ATNO for GenAI — "Streamlit vs Gradio vs Chainlit" (Medium, marzo 2026)
- Streamlit Docs — "Build a basic LLM chat app"
