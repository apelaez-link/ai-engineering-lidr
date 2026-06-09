"""Interfaz conversacional con Streamlit para el estimador (EJERCICIO de la sesión 03).

Ejecútalo con:
    uv run streamlit run streamlit_app.py

Cubre los tres niveles del ejercicio:
  - Nivel 1 (chat básico):   st.chat_message / st.chat_input + historial en session_state.
  - Nivel 2 (streaming):     st.write_stream sobre el generador del wrapper.
  - Nivel 3 (contexto CAG):   sidebar con system prompt, ejemplos CAG y métricas de la
                              última llamada (modelo, tokens, latencia, coste, caché...).

Decisión clave: la UI NO habla con OpenAI/Anthropic directamente. Reutiliza la lógica
del proyecto (`stream_estimation`), que pasa por el WRAPPER y por tanto hereda gratis
la abstracción de proveedores, el fallback, el cacheo y la trazabilidad. El system
prompt es exactamente el mismo que usa el endpoint CAG. La API key se lee del .env
(vía Pydantic Settings) o de st.secrets; nunca está hardcodeada.
"""

import streamlit as st
from dotenv import load_dotenv

# Carga el .env (claves de API) antes de importar la config/servicios.
load_dotenv()

from app.config import get_settings  # noqa: E402
from app.context.examples import ESTIMATION_EXAMPLES  # noqa: E402
from app.services.llm_service import _build_system_prompt, stream_estimation  # noqa: E402

st.set_page_config(page_title="Estimador de software (CAG)", page_icon="🧮", layout="wide")
st.title("🧮 Estimador de software")
st.caption(
    "Pega la transcripción de una reunión con el cliente y recibe una estimación. "
    "Arquitectura CAG + wrapper con fallback, cacheo y streaming (sesión 03)."
)

# Historial de la conversación en session_state: Streamlit re-ejecuta el script
# entero en cada interacción, así que persistimos el chat aquí para que no se pierda.
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_meta" not in st.session_state:
    st.session_state.last_meta = None


# ── Nivel 3: panel lateral con el contexto CAG y métricas ───────────────────
with st.sidebar:
    st.header("🔎 Contexto CAG")

    with st.expander("System prompt activo", expanded=False):
        st.text_area(
            "system_prompt",
            value=_build_system_prompt(),
            height=300,
            disabled=True,
            label_visibility="collapsed",
        )

    with st.expander(f"Ejemplos inyectados ({len(ESTIMATION_EXAMPLES)})", expanded=False):
        for i, ej in enumerate(ESTIMATION_EXAMPLES, start=1):
            st.markdown(f"**Ejemplo {i}**")
            st.caption(ej["meeting_summary"])

    st.divider()
    st.subheader("📊 Última llamada")
    meta = st.session_state.last_meta
    if meta:
        col1, col2 = st.columns(2)
        col1.metric("Modelo", meta.get("model", "—"))
        col2.metric("Latencia", f"{meta.get('latency_ms', 0):.0f} ms")
        col1.metric("Tokens entrada", meta.get("tokens_in", 0))
        col2.metric("Tokens salida", meta.get("tokens_out", 0))
        col1.metric("Coste", f"${meta.get('cost_usd', 0):.6f}")
        col2.metric("Proveedor", meta.get("provider", "—"))
        flags = []
        if meta.get("cache_hit"):
            flags.append("⚡ caché")
        if meta.get("fallback_used"):
            flags.append("🔁 fallback")
        st.caption(" · ".join(flags) if flags else "✅ llamada directa al proveedor primario")
    else:
        st.caption("Aún no has hecho ninguna estimación.")


# Avisamos si no hay ninguna API key configurada (causa de error más común).
settings = get_settings()
if not (settings.openai_api_key or settings.anthropic_api_key):
    st.warning(
        "No hay ninguna API key configurada. Copia `.env.example` a `.env` y rellena "
        "`OPENAI_API_KEY` o `ANTHROPIC_API_KEY` (o usa `.streamlit/secrets.toml`)."
    )


# ── Niveles 1 y 2: render del historial + chat con streaming ────────────────
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Pega aquí la transcripción de la reunión…"):
    # 1) Mostrar y guardar el mensaje del usuario.
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2) Generar la estimación en streaming (token a token).
    with st.chat_message("assistant"):
        meta: dict = {}
        # history = todo lo anterior al mensaje recién añadido (stream_estimation
        # vuelve a añadir 'prompt' como turno de usuario internamente).
        history = st.session_state.messages[:-1]
        try:
            full_response = st.write_stream(
                stream_estimation(prompt, history=history, meta=meta)
            )
        except ValueError as exc:
            full_response = f"⚠️ Configuración: {exc}"
            st.error(full_response)
        except Exception as exc:  # noqa: BLE001
            full_response = f"⚠️ Error al llamar al LLM: {exc}"
            st.error(full_response)

    # 3) Persistir la respuesta y las métricas para el sidebar.
    st.session_state.messages.append({"role": "assistant", "content": full_response})
    if meta:
        st.session_state.last_meta = meta
        st.rerun()  # refresca el sidebar con las métricas de esta llamada
