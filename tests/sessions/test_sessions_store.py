"""Tests del store en memoria de sesiones (sesión 05).

Comprobamos el ciclo básico create_session / get_session y que cada sesión nace
con un id único y memoria vacía. Sin APIs reales (es un dict en memoria).
"""

from app.sessions.store import SessionStore, get_store


def test_create_session_returns_unique_id() -> None:
    """create_session crea sesiones con session_id distintos (uuid4)."""
    store = SessionStore()
    s1 = store.create_session()
    s2 = store.create_session()
    assert s1.session_id != s2.session_id
    # Una sesión nueva nace con memoria vacía.
    assert s1.project_metadata.is_empty()
    assert s1.history.turns == []


def test_get_session_roundtrip() -> None:
    """get_session devuelve la misma sesión creada; None si el id no existe."""
    store = SessionStore()
    created = store.create_session()
    fetched = store.get_session(created.session_id)
    assert fetched is created
    assert store.get_session("does-not-exist") is None


def test_get_store_is_singleton() -> None:
    """get_store está cacheado: dos llamadas devuelven la MISMA instancia."""
    get_store.cache_clear()
    a = get_store()
    b = get_store()
    assert a is b
    # cache_clear fuerza una instancia nueva (aislamiento entre tests).
    get_store.cache_clear()
    c = get_store()
    assert c is not a
