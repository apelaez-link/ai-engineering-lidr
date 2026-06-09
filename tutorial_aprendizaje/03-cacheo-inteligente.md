# 03 — Cacheo inteligente

> 📚 **Concepto del curso:** [material_curso/03](material_curso/03-cacheo-inteligente.md)
> 🧩 **Código:** `app/cache/llm_cache.py` (+ uso en `app/services/llm_wrapper.py`)

## La idea en una frase

La misma transcripción, con el mismo contexto y modelo, produce la misma estimación. Guárdala
y la segunda vez sírvela de caché: instantánea y coste 0.

## Las dos decisiones que importan

### 1) La clave determinista
No basta con hashear el prompt: si cambias el modelo o la temperatura, la respuesta cambia.
**Todo lo que afecta al output entra en la clave.** En `build_cache_key`:
```python
raw = json.dumps({
    "messages": messages, "model": model, "temperature": temperature,
    "max_tokens": max_tokens, "system_prompt": system_prompt,
}, sort_keys=True, ensure_ascii=False)
return f"llm:{hashlib.sha256(raw.encode()).hexdigest()}"
```
`sort_keys=True` hace el JSON estable (mismo contenido → mismo hash, sin importar el orden).

Consecuencia elegante: como el `system_prompt` incluye los ejemplos CAG, **si añades o cambias
un ejemplo, la clave cambia sola** y las entradas viejas caducan por TTL. Eso es *invalidación
implícita por versionado del prompt* — no tienes que borrar la caché a mano.
(Compruébalo en `tests/test_cache.py::test_cache_key_changes_with_system_prompt`.)

### 2) El backend enchufable
La caché habla con un `CacheBackend` (un `Protocol` con `get/set/clear`). Hay dos implementaciones:
- **`InMemoryBackend`** (por defecto): un `dict` con expiración por TTL. Cero infraestructura,
  perfecto para desarrollo y demos. No sobrevive a reinicios ni se comparte entre workers.
- **`RedisBackend`** (opcional): `SETEX` (valor + expiración atómica). Lo de producción:
  persistente y compartido. Se activa con `CACHE_BACKEND=redis` en el `.env`.

> El curso usa Redis desde el principio. Aquí lo dejamos opcional para que el proyecto arranque
> sin levantar nada — pero el cambio a Redis es una variable de entorno, no código. Esa es,
> otra vez, la filosofía de la sesión.

## Cómo lo usa el wrapper

En `LLMWrapper.complete()`, **antes** de llamar al LLM:
```python
cache_key = build_cache_key(messages=conversation, model=primary_model, ...,
                            system_prompt=system_prompt)
if settings.cache_enabled:
    cached = cache.get(cache_key)
    if cached is not None:
        logger.info("llm_cache_hit", ...)
        result = LLMResult(**cached); result.cache_hit = True; result.latency_ms = 0.0
        return result            # ← no se llama al LLM
# ... miss: llama al LLM, y al terminar:
cache.set(cache_key, asdict(result))
```
La latencia de un hit es ~0 ms (y el coste, 0). En el smoke test del repo, la **segunda**
llamada idéntica devolvió `cache_hit: true` sin tocar al proveedor.

## Por qué exact-match (y no semántico) aquí

El material describe tres capas: exact-match, semántico (embeddings + similitud) y multi-nivel.
Para nuestro estimador, las transcripciones son **documentos largos**: la probabilidad de
match exacto (reenviar la misma) es alta, y la búsqueda semántica sobre textos tan largos tiene
particularidades que merecen su propio tratamiento (sesiones 07-08, con bases vectoriales). Por
eso aquí el exact-match es la decisión correcta, y el semántico queda como concepto.

## Cuándo NO cachear
Recuerda del material: no caches generación creativa, datos en tiempo real, contexto de usuario
muy variable, o temperatura alta (>0.7). Nuestro caso (estimación determinista, repetible) es
justo el bueno para cachear.

## Reto

1. **Mide el efecto:** lanza la misma transcripción dos veces por `/docs` y compara
   `latency_ms` y `cache_hit` entre la 1ª y la 2ª respuesta.
2. **Rompe la caché a propósito:** edita un ejemplo en `app/context/examples.py` y vuelve a
   lanzar la *misma* transcripción. ¿`cache_hit`? (No: cambió el system prompt → cambió la clave.)
3. **TTL:** baja `CACHE_TTL_SECONDS=5` en `.env`, repite una llamada, espera 6 s y repite. La
   tercera debería volver a ser miss. Revisa `test_cache.py::test_inmemory_respects_ttl`.
4. **(Avanzado) Redis:** si tienes Docker, `docker run -p 6379:6379 redis`, pon
   `CACHE_BACKEND=redis` y confirma que la caché ahora sobrevive a reiniciar el servidor.
