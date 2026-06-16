# 05 — Cacheo semántico de respuestas

> Material del curso LIDR · AI Engineering · Sesión 4 (Antonio Pérez). (≈25 min) · **Tema del directo.**

## El problema
Un mismo proyecto se estima 15 veces en una semana con palabras distintas ("mobile app with login, chat and push", "app móvil con login, chat y push", "app: needs auth, messaging, push notifs"...). **Quince inputs, una intención.** Cada uno cuesta céntimos y 3-5 s. El **cache exact-match** de la sesión 03 no ayuda: la clave (el texto) no es estable, cualquier diferencia genera clave nueva.

## Exact-match vs semántico
- **Exact-match:** string equality (hash map). Para LLMs captura casi nada salvo reenvíos idénticos.
- **Semántico:** compara **significados** vía **embeddings** (vectores de ~1536 dims). Textos que dicen lo mismo, aunque en idiomas distintos, producen vectores cercanos.

Mecánica: (1) embedding del input; (2) busca el vector más cercano en cache; (3) si la **similitud coseno > threshold** (0.85-0.95) → hit, devuelve la respuesta del vecino; (4) si no → miss: llama al LLM y guarda (embedding, respuesta). Números: embedding 50-100 ms, búsqueda 5-20 ms, latencia de hit 2-4× (hasta 50-100×) menor que un miss.

## El threshold es decisión de producto
- **Agresivo (0.85):** más hits, menos coste, pero riesgo de servir una respuesta cacheada para una pregunta que no era la misma ("...login, chat, push" vs "...login, chat **Stripe payments**").
- **Conservador (0.95):** casi sin falsos positivos, pero pocos hits.
- Típico 0.90-0.93; dominios sensibles (legal/médico/financiero) 0.95+. Regla: **log-only primero**, mide falsos positivos, ajusta, luego activa el bypass.

## Tres decisiones arquitectónicas
1. **Qué se cachea — cache key compuesta:** parte **determinista** (project_type + detail_level + output_format + **prompt_version**) que actúa de bucket + parte **vectorial** (embedding de la description). Así no colisionan requests con distinto formato, y al subir a `v2` los buckets de `v1` quedan huérfanos solos (no invalidas nada).
2. **Cuándo se escribe — solo DESPUÉS de los guardrails:** si cacheas antes de validar, propagas alucinaciones/inseguridades a todos los inputs parecidos durante el TTL. El cache es la última escritura del pipeline.
3. **Cuándo se sirven los hits — input guardrails PRIMERO, cache después:** saltarse los guardrails para ahorrar 50 ms permitiría a un atacante activar un hit con contenido tóxico sin pasar moderación.

## Implementación (Redis + redisvl)
```python
from redisvl.extensions.llmcache import SemanticCache
cache = SemanticCache(name="estimation_cache", redis_url="redis://localhost:6379",
                      distance_threshold=0.08, ttl=86400)  # 0.08 ≈ sim ≥ 0.92

# en el endpoint:
validate_input(request.description)             # guardrails primero
cached = cache_lookup(request)                  # bucket + embedding
if cached: return EstimationResponse(result=cached, cached=True)
result = llm_client...create(response_model=EstimationResult, ...)
cache_write(request, result)                    # solo tras validar
return EstimationResponse(result=result, cached=False)
```
El campo `cached: bool` es valioso para el frontend y para medir el hit rate real. Alternativas: LangCache (gestionado), `langchain ... RedisSemanticCache`, o manual sobre pgvector/Qdrant/Pinecone.

## Coste real
Añade latencia/coste de embedding (50-100 ms, céntimos/1k tokens) en TODA request. Sale a favor si la **tasa de hits** es alta (40-60% en servicios repetitivos como el estimator). Si cada query es única (escritura creativa), puede añadir más latencia de la que ahorra. Experimento previo: log-only una semana, mide hits potenciales, decide. TTL 24h por defecto; minutos si los datos son volátiles.

## Recursos
- Redis — *What is semantic caching?*, *redisvl Semantic Cache*, *LangCache*
- Zilliz — *Semantic Cache* · LangChain — *Caching guide*
