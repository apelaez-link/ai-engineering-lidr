# ✍️ Ejercicio — Interfaz conversacional con Streamlit

> Material del curso LIDR · AI Engineering · Sesión 3 (Antonio Pérez). Recuperado de la plataforma.

## Objetivo

Añadir una interfaz conversacional web al Proyecto 1 usando **Streamlit**. Al finalizar,
el alumno debe poder pegar una transcripción de reunión en una interfaz de chat y ver la
estimación generada por el LLM **en streaming**, sin necesidad de usar curl, Postman ni Swagger.

## Punto de partida

Tu proyecto de la sesión 02: un backend FastAPI con un endpoint CAG que recibe
transcripciones y devuelve estimaciones de software.

## Formato

Fichero Python (`streamlit_app.py`) en la raíz de tu proyecto. Se ejecuta con
`streamlit run streamlit_app.py`.

## Niveles

### Nivel 1 — Chat básico (obligatorio)
Crea una aplicación Streamlit con interfaz de chat (`st.chat_message`, `st.chat_input`)
que permita escribir o pegar una transcripción. La app envía ese texto al LLM
(reutilizando la lógica de llamada que ya tienes) y muestra la estimación como mensaje
del asistente.

Requisitos:
- El historial de la conversación debe mantenerse visible durante la sesión (`st.session_state`).
- El system prompt debe ser el mismo que usas en tu endpoint CAG.
- La API key no debe estar hardcodeada.

### Nivel 2 — Streaming (obligatorio)
La respuesta del LLM debe mostrarse **token a token**, no de golpe al terminar. Usa
`st.write_stream` o el patrón placeholder + delta. El usuario debe ver la estimación
"escribiéndose" en tiempo real.

### Nivel 3 — Contexto CAG en la interfaz (opcional)
Añade un panel lateral (`st.sidebar`) que muestre:
- El system prompt activo (solo lectura).
- El contexto estático inyectado (estimaciones de ejemplo del CAG).
- Métricas básicas de la última llamada: modelo, tokens de entrada, tokens de salida, tiempo de respuesta.

## Verificación

Tu ejercicio está completo cuando:
- [ ] `streamlit run streamlit_app.py` abre una interfaz de chat en el navegador.
- [ ] Puedes pegar una transcripción y recibes una estimación.
- [ ] La conversación persiste en pantalla (varias preguntas seguidas).
- [ ] La respuesta se muestra en streaming, no de golpe.
- [ ] La API key se lee desde `.env` o `st.secrets`, no está en el código.

## Entregable

Fichero `streamlit_app.py` funcional en tu proyecto.

## Documentación de referencia
- Streamlit chat elements: https://docs.streamlit.io/develop/tutorials/chat-and-llm-apps/build-conversational-apps
- SDK de tu proveedor (OpenAI o Anthropic): documentación de streaming
- Streamlit secrets management: https://docs.streamlit.io/develop/concepts/connections/secrets-management

## Nota del curso

> El wrapper de abstracción de proveedores, el cacheo inteligente y la capa de
> logging/trazabilidad los implementaremos juntos durante la sesión en vivo. No es
> necesario que los prepares antes.

**En este repo ya están implementados los tres** (wrapper, caché y logging), porque el
objetivo aquí es entender el módulo entero con código funcionando. El `streamlit_app.py`
de este proyecto reutiliza ese wrapper, así que la interfaz hereda gratis streaming,
caché y fallback.
