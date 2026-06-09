"""Cacheo exact-match de respuestas del LLM (lección "Cacheo inteligente").

Idea: la misma transcripción, con el mismo contexto CAG, el mismo modelo y los
mismos parámetros, produce la misma estimación. Regenerarla es tirar dinero y
tiempo. Así que la guardamos y la segunda vez la servimos de caché:
    1ª vez -> 4 s y coste de tokens.
    2ª vez -> microsegundos y coste 0.

Decisiones de diseño de este módulo:

1) CLAVE DETERMINISTA. La clave es un hash SHA-256 de TODO lo que afecta a la
   salida: mensajes, modelo, temperatura, max_tokens y el system prompt. Si
   cambias cualquiera de esos (p. ej. añades un ejemplo CAG nuevo al system
   prompt), la clave cambia automáticamente y las entradas viejas caducan por
   TTL. Esto es "invalidación implícita por versionado del prompt".

2) BACKEND ENCHUFABLE. Por defecto usamos un backend en memoria (un dict con
   TTL) que funciona sin instalar nada. En producción cambias a Redis con una
   variable de entorno (CACHE_BACKEND=redis). El curso usa Redis; aquí lo
   dejamos opcional para que el proyecto arranque sin levantar infraestructura.

Nota: el cacheo SEMÁNTICO (capturar reformulaciones con embeddings) se ve como
concepto en el material, pero requiere base de datos vectorial y se trabaja en
las sesiones 07-08. Para transcripciones largas, el exact-match es la estrategia
correcta.
"""

from __future__ import annotations

import hashlib
import json
import time
from functools import lru_cache
from typing import Protocol

from app.config import get_settings


def build_cache_key(
    *,
    messages: list[dict],
    model: str,
    temperature: float,
    max_tokens: int,
    system_prompt: str,
) -> str:
    """Genera una clave de caché determinista a partir de todo lo que afecta al output.

    Usamos sort_keys=True para que el JSON sea estable (mismo contenido -> misma
    cadena -> mismo hash), independientemente del orden de las claves del dict.
    """
    raw = json.dumps(
        {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "system_prompt": system_prompt,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"llm:{digest}"


class CacheBackend(Protocol):
    """Contrato mínimo de un backend de caché. Memoria y Redis lo cumplen igual."""

    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...
    def clear(self) -> None: ...


class InMemoryBackend:
    """Backend por defecto: un dict en memoria con expiración por TTL.

    Suficiente para desarrollo, demos y un único proceso. No sobrevive a un
    reinicio ni se comparte entre workers; para eso está Redis.
    """

    def __init__(self) -> None:
        # clave -> (valor_serializado, instante_de_expiracion)
        self._store: dict[str, tuple[str, float]] = {}

    def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            # Caducada: la borramos perezosamente y devolvemos miss.
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._store[key] = (value, time.monotonic() + ttl_seconds)

    def clear(self) -> None:
        self._store.clear()


class RedisBackend:
    """Backend Redis (opcional). Requiere `pip install redis` y un Redis corriendo.

    Usa SETEX, que guarda el valor con expiración atómica. Es lo que usaríamos en
    producción: persistente y compartido entre todos los workers/instancias.
    """

    def __init__(self, redis_url: str) -> None:
        import redis  # import perezoso: solo si realmente usas este backend

        self._redis = redis.from_url(redis_url, decode_responses=True)

    def get(self, key: str) -> str | None:
        return self._redis.get(key)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._redis.setex(key, ttl_seconds, value)

    def clear(self) -> None:
        self._redis.flushdb()


class LLMCache:
    """Fachada de cacheo: oculta el backend y serializa/deserializa el resultado.

    Guardamos el resultado completo (contenido + metadatos: modelo, tokens...) como
    JSON, para poder devolver un objeto igual al de una llamada real, marcado con
    cache_hit=True.
    """

    def __init__(self, backend: CacheBackend, ttl_seconds: int) -> None:
        self._backend = backend
        self._ttl = ttl_seconds

    def get(self, key: str) -> dict | None:
        raw = self._backend.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    def set(self, key: str, value: dict) -> None:
        self._backend.set(key, json.dumps(value, ensure_ascii=False), self._ttl)

    def clear(self) -> None:
        self._backend.clear()


def _build_backend() -> CacheBackend:
    settings = get_settings()
    if settings.cache_backend.lower() == "redis":
        return RedisBackend(settings.redis_url)
    return InMemoryBackend()


@lru_cache
def get_cache() -> LLMCache:
    """Devuelve una única instancia de caché para todo el proceso (singleton).

    Cacheada con @lru_cache para que el dict en memoria (o la conexión a Redis)
    se reutilice entre peticiones. En tests llamamos a get_cache.cache_clear()
    para empezar de cero.
    """
    settings = get_settings()
    return LLMCache(_build_backend(), settings.cache_ttl_seconds)
