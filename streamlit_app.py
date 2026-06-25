"""Interfaz CONVERSACIONAL del estimador (sesión 05).

Da el salto de la sesión 04 (formulario transaccional) a una UI con MEMORIA: cada
pestaña del navegador abre una "sesión" en el backend (POST /sessions) y, a partir
de ahí, cada mensaje del usuario es un turno de la misma conversación. El backend
recuerda los turnos anteriores (ventana deslizante) y va acumulando los hechos del
proyecto (project_metadata), que mostramos en el panel lateral.

Novedades respecto a la sesión 04:
  - Al cargar la página se crea una sesión y se guarda su id en st.session_state.
  - Campo de transcripción + carga MÚLTIPLE de adjuntos (PDF/Word/txt).
  - Cada envío hace POST /sessions/{id}/estimate (multipart/form-data) con httpx.
  - El sidebar muestra el project_metadata actual (memoria viva de la conversación).
  - Botón "Nueva conversación" que crea una sesión nueva y resetea el estado.

La URL del backend se lee de API_BASE_URL (default http://localhost:8000). La API
key NUNCA se hardcodea aquí: vive en el backend.

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
    page_title="Estimador conversacional",
    page_icon="💬",
    layout="wide",
)


# ── Gestión de la sesión conversacional ──────────────────────────────────────
def create_session() -> str | None:
    """Crea una sesión nueva en el backend y devuelve su session_id (o None si falla)."""
    try:
        response = httpx.post(f"{API_BASE_URL}/api/v1/sessions", timeout=30.0)
        response.raise_for_status()
        return response.json()["session_id"]
    except httpx.HTTPError as exc:
        st.error(
            f"No se pudo crear la sesión en el backend ({API_BASE_URL}). "
            f"¿Está levantado?\n\nDetalle: {exc}"
        )
        return None


def reset_conversation() -> None:
    """Crea una sesión nueva y resetea el estado de la UI (botón 'Nueva conversación')."""
    st.session_state.session_id = create_session()
    st.session_state.turns = []          # historial de turnos mostrados en la UI
    st.session_state.project_metadata = {}  # memoria acumulada (la pinta el sidebar)


def fetch_project_metadata(session_id: str) -> dict:
    """Consulta al backend la memoria viva (project_metadata) de la sesión.

    El backend es la fuente de verdad de la memoria; la UI solo la PINTA. Si la
    llamada falla, devolvemos {} (el sidebar mostrará 'sin hechos' en vez de romper).
    """
    try:
        response = httpx.get(f"{API_BASE_URL}/api/v1/sessions/{session_id}", timeout=30.0)
        response.raise_for_status()
        return response.json().get("project_metadata", {})
    except httpx.HTTPError:
        return {}


# Streamlit re-ejecuta el script entero en cada interacción; session_state persiste.
# Al cargar por primera vez, abrimos una sesión conversacional automáticamente.
if "session_id" not in st.session_state:
    reset_conversation()


st.title("💬 Estimador conversacional")
st.caption(
    "Conversa con el estimador: recuerda los turnos anteriores y los hechos del "
    "proyecto, y acepta documentos adjuntos como contexto. Sesión 05 — memoria "
    "conversacional y contexto enriquecido."
)


# ── Sidebar: memoria viva de la conversación ─────────────────────────────────
with st.sidebar:
    st.header("🧠 Memoria del proyecto")
    st.caption(f"Sesión: `{st.session_state.session_id or '—'}`")

    metadata = st.session_state.get("project_metadata") or {}
    if metadata and any(
        metadata.get(k) for k in ("project_name", "assumed_team_size", "mentioned_technologies", "agreed_scope")
    ):
        if metadata.get("project_name"):
            st.metric("Proyecto", metadata["project_name"])
        if metadata.get("assumed_team_size"):
            st.metric("Equipo asumido", f"{metadata['assumed_team_size']} personas")
        techs = metadata.get("mentioned_technologies") or []
        if techs:
            st.write("**Tecnologías mencionadas**")
            st.write(", ".join(techs))
        if metadata.get("agreed_scope"):
            st.write("**Alcance acordado**")
            st.info(metadata["agreed_scope"])
    else:
        st.caption("Todavía no se conocen hechos del proyecto. Empieza a conversar.")

    st.divider()
    st.subheader("⚙️ Configuración")
    prompt_version = st.selectbox(
        "Versión del prompt",
        options=["v1", "v2"],
        index=0,
        help="Variante del template Jinja2 para comparar resultados.",
    )
    project_type = st.selectbox(
        "Tipo de proyecto",
        options=["web_saas", "mobile_app", "internal_tool", "data_pipeline"],
    )
    detail_level = st.radio(
        "Nivel de detalle",
        options=["summary", "medium", "detailed"],
        index=1,
        horizontal=True,
    )
    output_format = st.selectbox(
        "Formato de salida",
        options=["phases_table", "line_items", "narrative"],
    )

    st.divider()
    if st.button("🆕 Nueva conversación", use_container_width=True):
        reset_conversation()
        st.rerun()


# ── Historial de turnos de la conversación ───────────────────────────────────
for turn in st.session_state.get("turns", []):
    with st.chat_message("user"):
        st.markdown(turn["user"])
        for fname in turn.get("attachments", []):
            st.caption(f"📎 {fname}")
    with st.chat_message("assistant"):
        result = turn["result"]
        st.markdown(f"**{result['summary']}**")
        col1, col2, col3 = st.columns(3)
        col1.metric("Duración", f"{result['total_duration_weeks']} sem")
        col2.metric("Coste", f"{result['total_cost_eur']:,} €")
        col3.metric("Confianza", f"{result['confidence_pct']}%")
        if result.get("phases"):
            st.table(
                [
                    {
                        "Fase": p["name"],
                        "Semanas": p["duration_weeks"],
                        "Coste (€)": p["cost_eur"],
                        "Confianza (%)": p["confidence_pct"],
                    }
                    for p in result["phases"]
                ]
            )


# ── Entrada: transcripción + adjuntos ────────────────────────────────────────
st.divider()
uploaded_files = st.file_uploader(
    "📎 Adjuntos (opcional): PDF, Word o texto",
    type=["pdf", "docx", "txt"],
    accept_multiple_files=True,
    help="El texto de los documentos se inyecta como contexto enriquecido.",
)

transcript = st.chat_input("Escribe tu mensaje (transcripción de la reunión, requisitos, dudas…)")

if transcript:
    if not st.session_state.session_id:
        st.error("No hay sesión activa. Pulsa 'Nueva conversación' en el panel lateral.")
        st.stop()

    # Preparamos el multipart: campos de formulario + ficheros adjuntos.
    data = {
        "transcript": transcript,
        "project_type": project_type,
        "detail_level": detail_level,
        "output_format": output_format,
    }
    files = [
        ("attachments", (f.name, f.getvalue(), f.type or "application/octet-stream"))
        for f in (uploaded_files or [])
    ]

    with st.spinner("Pensando…"):
        try:
            response = httpx.post(
                f"{API_BASE_URL}/api/v1/sessions/{st.session_state.session_id}/estimate",
                data=data,
                files=files or None,
                params={"prompt_version": prompt_version},
                timeout=120.0,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.json().get("detail", str(exc)) if exc.response is not None else str(exc)
            st.error(f"Error del servidor ({exc.response.status_code}): {detail}")
            st.stop()
        except httpx.RequestError as exc:
            st.error(
                f"No se pudo conectar con el backend ({API_BASE_URL}). "
                f"¿Está el servidor levantado?\n\nDetalle: {exc}"
            )
            st.stop()

    # Guardamos el turno en el historial de la UI y refrescamos.
    st.session_state.turns.append(
        {
            "user": transcript,
            "attachments": [f.name for f in (uploaded_files or [])],
            "result": payload["result"],
        }
    )

    # Refrescamos la memoria del proyecto consultando el estado de la sesión: el
    # backend es la fuente de verdad (ha corrido el extractor de metadatos por su
    # cuenta), así que el sidebar muestra los hechos REALES acumulados.
    st.session_state.project_metadata = fetch_project_metadata(st.session_state.session_id)
    st.rerun()
