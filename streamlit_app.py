"""Interfaz de producto del estimador (sesión 04).

Sustituye el chat conversacional de la sesión 03 por un formulario tipado:
el usuario rellena los campos estructurados (tipo de proyecto, nivel de detalle,
formato de salida y descripción) y recibe una estimación bien formateada.

La UI habla con el backend FastAPI vía HTTP (httpx), de forma que la separación
de responsabilidades es clara: Streamlit es SOLO presentación, la lógica vive
en la API. La URL del backend se lee de la variable de entorno API_BASE_URL
(default http://localhost:8000) y la API key NUNCA se hardcodea aquí.

Ejecútalo con:
    uv run streamlit run streamlit_app.py
"""

import os

import httpx
import streamlit as st
from dotenv import load_dotenv

# Cargamos el .env antes de leer variables de entorno para que funcione en local.
load_dotenv()

# URL del backend: configurable desde el entorno (útil en Docker / CI / staging).
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Estimador de software",
    page_icon="📐",
    layout="wide",
)

st.title("📐 Estimador de software")
st.caption(
    "Rellena el formulario con los datos del proyecto y recibe una estimación "
    "estructurada generada por IA. Sesión 04 — del chat al producto."
)

# ── Inicialización del estado de sesión ─────────────────────────────────────
# Streamlit re-ejecuta el script entero en cada interacción; session_state
# persiste los datos entre ejecuciones (dentro de la misma sesión de usuario).
if "estimations" not in st.session_state:
    st.session_state.estimations = []   # historial simple de estimaciones
if "last_meta" not in st.session_state:
    st.session_state.last_meta = None


# ── Sidebar: metadatos de la última llamada ──────────────────────────────────
with st.sidebar:
    st.header("🔎 Observabilidad")
    meta = st.session_state.last_meta
    if meta:
        st.subheader("Última estimación")
        col1, col2 = st.columns(2)
        col1.metric("Modelo", meta.get("model") or "—")
        col2.metric("Latencia", f"{meta.get('latency_ms', 0):.0f} ms")
        col1.metric("Tokens entrada", meta.get("tokens_in", 0))
        col2.metric("Tokens salida", meta.get("tokens_out", 0))
        col1.metric("Coste", f"${meta.get('cost_usd', 0):.6f}")
        col2.metric("Versión prompt", meta.get("prompt_version", "—"))
        flags = []
        if meta.get("cache_hit"):
            flags.append("⚡ caché")
        if meta.get("fallback_used"):
            flags.append("🔁 fallback")
        st.caption(" · ".join(flags) if flags else "✅ llamada directa al proveedor primario")
    else:
        st.caption("Aún no has generado ninguna estimación.")

    st.divider()
    st.subheader("⚙️ Configuración")
    prompt_version = st.selectbox(
        "Versión del prompt",
        options=["v1", "v2"],
        index=0,
        help="Selecciona la variante del template Jinja2 para comparar resultados.",
    )


# ── Formulario principal ─────────────────────────────────────────────────────
with st.form("estimation_form", clear_on_submit=False):
    st.subheader("Datos del proyecto")

    description = st.text_area(
        "Descripción del proyecto *",
        placeholder=(
            "Describe el proyecto con el mayor detalle posible: funcionalidades clave, "
            "integraciones, usuarios objetivo, restricciones técnicas conocidas..."
        ),
        height=160,
        help="Mínimo 20 caracteres, máximo 2000.",
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        project_type = st.selectbox(
            "Tipo de proyecto *",
            options=["mobile_app", "web_saas", "internal_tool", "data_pipeline"],
            format_func=lambda x: {
                "mobile_app": "📱 App móvil",
                "web_saas": "🌐 Web / SaaS",
                "internal_tool": "🛠️ Herramienta interna",
                "data_pipeline": "📊 Pipeline de datos",
            }[x],
        )

    with col2:
        detail_level = st.radio(
            "Nivel de detalle *",
            options=["summary", "medium", "detailed"],
            format_func=lambda x: {
                "summary": "Resumen",
                "medium": "Medio",
                "detailed": "Detallado",
            }[x],
            horizontal=False,
        )

    with col3:
        output_format = st.selectbox(
            "Formato de salida *",
            options=["phases_table", "line_items", "narrative"],
            format_func=lambda x: {
                "phases_table": "📋 Tabla de fases",
                "line_items": "📝 Líneas de trabajo",
                "narrative": "📖 Narrativa",
            }[x],
        )

    submitted = st.form_submit_button("Estimar proyecto", use_container_width=True, type="primary")


# ── Procesamiento al enviar el formulario ────────────────────────────────────
if submitted:
    # Validación básica en el cliente antes de llamar a la API.
    if not description or len(description.strip()) < 20:
        st.error("La descripción es obligatoria y debe tener al menos 20 caracteres.")
        st.stop()

    payload = {
        "description": description.strip(),
        "project_type": project_type,
        "detail_level": detail_level,
        "output_format": output_format,
    }

    with st.spinner("Generando estimación…"):
        try:
            response = httpx.post(
                f"{API_BASE_URL}/api/v1/estimate",
                json=payload,
                params={"prompt_version": prompt_version},
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.json().get("detail", str(exc)) if exc.response else str(exc)
            st.error(f"Error del servidor ({exc.response.status_code}): {detail}")
            st.stop()
        except httpx.RequestError as exc:
            st.error(
                f"No se pudo conectar con el backend ({API_BASE_URL}). "
                f"¿Está el servidor levantado?\n\nDetalle: {exc}"
            )
            st.stop()

    # Guardamos metadatos para el sidebar y añadimos al historial.
    st.session_state.last_meta = {
        "model": data.get("model"),
        "latency_ms": data.get("latency_ms", 0),
        "tokens_in": data.get("tokens_in", 0),
        "tokens_out": data.get("tokens_out", 0),
        "cost_usd": data.get("cost_usd", 0),
        "prompt_version": data.get("prompt_version", prompt_version),
        "cache_hit": data.get("cache_hit", False),
        "fallback_used": data.get("fallback_used", False),
    }
    st.session_state.estimations.append(
        {
            "description": description[:80] + ("…" if len(description) > 80 else ""),
            "project_type": project_type,
            "output_format": output_format,
            "text": data.get("text", ""),
        }
    )

    st.success("Estimación generada correctamente.")
    st.rerun()  # refresca el sidebar con los metadatos de esta llamada


# ── Mostrar la última estimación y el historial ──────────────────────────────
if st.session_state.estimations:
    last = st.session_state.estimations[-1]
    st.subheader("Última estimación")
    st.markdown(last["text"])

    if len(st.session_state.estimations) > 1:
        with st.expander(f"Historial ({len(st.session_state.estimations)} estimaciones)", expanded=False):
            for i, est in enumerate(reversed(st.session_state.estimations[:-1]), start=1):
                st.markdown(f"**#{len(st.session_state.estimations) - i}** — {est['description']}")
                st.caption(f"Tipo: {est['project_type']} | Formato: {est['output_format']}")
                st.markdown(est["text"])
                st.divider()
