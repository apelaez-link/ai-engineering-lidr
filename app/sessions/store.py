"""Almacén EN MEMORIA de sesiones conversacionales (sesión 05).

Un store mínimo: un diccionario {session_id -> Session} que vive en el proceso.

¿Por qué en memoria y no Redis/BBDD?
  En esta fase del curso priorizamos "correr sin infra": el ejercicio debe poder
  ejecutarse y testearse sin levantar una base de datos ni un Redis. La contrapartida
  es la VOLATILIDAD: si el proceso del backend se reinicia, todas las sesiones se
  pierden, y con varias réplicas detrás de un balanceador cada una tendría su propio
  store (las sesiones no se comparten). Es una limitación CONSCIENTE y aceptable para
  aprender el patrón de memoria conversacional. En producción este store se sustituye
  por Redis (con TTL por sesión) o una BBDD, manteniendo la misma interfaz pública
  (create_session / get_session), de modo que el resto del código no cambie.

El singleton se expone con @lru_cache (igual que get_settings / get_cache): así hay
un único store por proceso y los tests pueden aislarse con get_store.cache_clear().
"""

from __future__ import annotations

import uuid
from functools import lru_cache

from app.logging_config import get_logger
from app.sessions.models import Session

logger = get_logger(component="sessions_store")


class SessionStore:
    """Store en memoria de sesiones. Interfaz mínima: create / get.

    La interfaz se mantiene deliberadamente pequeña para que migrar a Redis o a una
    BBDD en el futuro sea un cambio localizado (misma firma de métodos).
    """

    def __init__(self) -> None:
        # Diccionario simple en memoria. La clave es el session_id (uuid4 como str).
        self._sessions: dict[str, Session] = {}

    def create_session(self) -> Session:
        """Crea una sesión nueva con un session_id uuid4 y la registra en el store."""
        session_id = str(uuid.uuid4())
        session = Session(session_id=session_id)
        self._sessions[session_id] = session
        logger.info("session_created", session_id=session_id)
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Devuelve la sesión por id, o None si no existe (el router lo traduce a 404)."""
        return self._sessions.get(session_id)


@lru_cache
def get_store() -> SessionStore:
    """Devuelve el SessionStore único del proceso (cacheado con @lru_cache).

    Como en get_settings, el @lru_cache garantiza una sola instancia por proceso.
    En tests, get_store.cache_clear() descarta el store y obliga a recrearlo limpio,
    evitando que las sesiones de un test se filtren al siguiente.
    """
    return SessionStore()
