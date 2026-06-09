"""Tests del cacheo exact-match (lección "Cacheo inteligente").

No tocan el LLM ni Redis: prueban la clave determinista y el backend en memoria.
"""

from app.cache.llm_cache import InMemoryBackend, LLMCache, build_cache_key


def test_cache_key_is_deterministic() -> None:
    # Mismo input -> misma clave (el orden de las claves del dict no importa).
    args = dict(
        messages=[{"role": "user", "content": "hola"}],
        model="gpt-4o-mini",
        temperature=0.7,
        max_tokens=1500,
        system_prompt="Eres un estimador.",
    )
    assert build_cache_key(**args) == build_cache_key(**args)


def test_cache_key_changes_with_system_prompt() -> None:
    # Cambiar el system prompt (p. ej. añadir un ejemplo CAG) cambia la clave:
    # invalidación implícita por versionado del prompt.
    base = dict(
        messages=[{"role": "user", "content": "hola"}],
        model="gpt-4o-mini",
        temperature=0.7,
        max_tokens=1500,
    )
    k1 = build_cache_key(**base, system_prompt="Prompt A")
    k2 = build_cache_key(**base, system_prompt="Prompt B")
    assert k1 != k2


def test_inmemory_get_set_roundtrip() -> None:
    cache = LLMCache(InMemoryBackend(), ttl_seconds=60)
    assert cache.get("k") is None  # miss
    cache.set("k", {"content": "estimación", "model": "gpt-4o-mini"})
    hit = cache.get("k")
    assert hit is not None
    assert hit["content"] == "estimación"


def test_inmemory_respects_ttl() -> None:
    # TTL=0 -> la entrada caduca de inmediato y el siguiente get es miss.
    cache = LLMCache(InMemoryBackend(), ttl_seconds=0)
    cache.set("k", {"content": "x"})
    assert cache.get("k") is None
