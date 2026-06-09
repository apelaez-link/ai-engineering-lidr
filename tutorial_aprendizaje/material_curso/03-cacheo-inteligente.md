# 03 — Cacheo inteligente de respuestas de LLMs

> Material del curso LIDR · AI Engineering · Sesión 3 (Antonio Pérez). Recuperado de la plataforma. (≈19 min)

## Por qué cachear respuestas de un LLM

Un project manager pega la misma transcripción dos veces (revisar la de ayer, cerró la
pestaña…). Sin caché, el sistema hace dos llamadas, paga dos veces los tokens y el usuario
espera dos veces los 3-5 s de latencia, para una respuesta casi idéntica. No es excepcional:
en apps reales hay repetición constante. Según datos de producción de 2026, el **cacheo
semántico** alcanza tasas de acierto del **40-70%** con tráfico real.

Tres beneficios: **latencia** (microsegundos/milisegundos vs segundos), **coste** (cada hit
es una llamada que no pagas), **fiabilidad** (una respuesta cacheada no depende de la
disponibilidad del proveedor).

## Cacheo en LLMs vs cacheo web tradicional

En web la clave es determinista: `GET /api/users/42` → misma respuesta. En LLMs, el input
del usuario rara vez es idéntico: "¿Cómo reseteo mi contraseña?" / "¿Proceso para recuperar
la contraseña?" / "Olvidé mi password" son la misma intención con tres formulaciones. Por eso
hay **tres capas**, de simple a sofisticada:

1. **Exact match** — comparación exacta del input. Microsegundos, simple, solo inputs idénticos.
2. **Cacheo semántico** — embeddings + similitud coseno; captura reformulaciones (milisegundos).
3. **Prompt caching del proveedor** — mecanismo nativo (Anthropic, OpenAI) que cachea porciones
   del prompt entre llamadas; reduce coste de la parte repetida, no cachea la respuesta completa.

## Exact match (lo que implementamos)

Correcto para nuestro caso: transcripciones idénticas → misma estimación. La clave es un hash
determinista de **todo lo que afecta a la respuesta** (no basta con el prompt: modelo y
temperatura también cambian el output):

```python
import hashlib, json, redis
from openai import OpenAI

class LLMCache:
    def __init__(self, redis_url="redis://localhost:6379", ttl=86400):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.client = OpenAI()
        self.ttl = ttl  # 24 horas por defecto

    def _cache_key(self, prompt, model, system_prompt):
        raw = json.dumps({"prompt": prompt, "model": model, "system_prompt": system_prompt}, sort_keys=True)
        return f"llm:{hashlib.sha256(raw.encode()).hexdigest()}"

    def completion(self, prompt, model, system_prompt):
        key = self._cache_key(prompt, model, system_prompt)
        cached = self.redis.get(key)
        if cached:
            result = json.loads(cached); result["cache_hit"] = True; return result
        response = self.client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
        )
        result = {"content": response.choices[0].message.content, "model": model,
                  "tokens_in": response.usage.prompt_tokens, "tokens_out": response.usage.completion_tokens,
                  "cache_hit": False}
        self.redis.setex(key, self.ttl, json.dumps(result))
        return result
```

El `system_prompt` forma parte de la clave: como incluye los ejemplos CAG, si los cambias la
clave cambia automáticamente y las entradas viejas caducan por TTL → **invalidación implícita**.
El **TTL** es la decisión más importante: 24 h para estimaciones; minutos para datos en tiempo real.

## Cacheo semántico (concepto)

Convierte el input en embedding, busca en caché un vector con similitud coseno por encima de
un umbral, y si lo hay devuelve la respuesta asociada:

```python
class SemanticCache:
    def __init__(self, similarity_threshold=0.95):
        self.client = OpenAI(); self.entries = []; self.threshold = similarity_threshold
    def _embed(self, text):
        return self.client.embeddings.create(model="text-embedding-3-small", input=text).data[0].embedding
    def lookup(self, query):
        qv = self._embed(query); best_score, best = 0.0, None
        for vec, resp in self.entries:
            score = cosine_sim(qv, vec)
            if score > best_score: best_score, best = score, resp
        return (best, True) if best_score >= self.threshold else (None, False)
```

El **umbral** es crítico: 0.99 → casi ningún hit; 0.85 → respuestas incorrectas. Punto de
partida 0.95, ajustar con datos reales. La búsqueda lineal en memoria no escala; en producción
se usan bases vectoriales (pgvector, Qdrant, Pinecone) → sesiones 07-08.

## Cacheo multi-nivel

Exact match (L1, rápido/barato) + semántico (L2, captura más). Si L1 falla, prueba L2 y
*promueve* a L1 para futuras consultas idénticas; si ambos fallan, llama al LLM y guarda en
ambos. Mismo patrón que L1/L2/L3 en CPUs o CDN → Redis → BD.

## Cuándo cachear y cuándo no

- **Cachea cuando:** inputs repetidos (FAQs, transcripciones), respuesta no necesita ser única
  (estimaciones, resúmenes, factual), coste/latencia importan, datos estables.
- **No cachees cuando:** cada respuesta debe ser única (creatividad, brainstorming), datos en
  tiempo real, contexto de usuario crítico y variable, temperatura alta (>0.7).

Para el Proyecto 1, exact match es claramente apropiado: tarea determinista, repetibilidad deseable.

## Invalidación: el problema difícil

> "Solo hay dos problemas difíciles en computación: invalidación de caché, nombrar cosas, y
> errores off-by-one."

- **TTL** — cada entrada expira tras un tiempo fijo. Lo que usamos por defecto.
- **Por evento** — al cambiar los datos fuente, borras las entradas asociadas (tags/namespaces).
- **Versionado del prompt** — incluir la versión del system prompt en la clave; al cambiarlo,
  las claves difieren y lo viejo caduca. Es lo que hace `_cache_key` al incluir `system_prompt`.

TTL + versionado del prompt basta para la mayoría de apps.

## Métricas (qué medir)

- **Hit rate** — % servido de caché (<20% no justifica la infra; >50% ahorro significativo).
- **Latencia hit vs miss** — diferencia esperable de 100-1000×.
- **Coste evitado** — tokens no consumidos, en dinero.
- **Tasa de stale responses** — respuestas ya incorrectas; si es alta, TTL demasiado largo.

## Recursos
- Reintech — "LLM Caching Strategies: Reduce Response Times by 80-95%"
- AI Echoes — "Benchmarking LLM Exact and Semantic Caching with Redis"
- Redis Blog — "What is Semantic Caching?"
