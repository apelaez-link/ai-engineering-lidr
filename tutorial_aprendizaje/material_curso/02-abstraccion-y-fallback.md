# 02 — Abstracción de proveedores y estrategias de fallback

> Material del curso LIDR · AI Engineering · Sesión 3 (Antonio Pérez). Recuperado de la plataforma. (≈20 min)

## El problema: acoplamiento a un proveedor

El endpoint de la sesión 02 está **acoplado a un único proveedor**. Si usas el SDK de
OpenAI, tu código importa `openai`, llama a `client.chat.completions.create()` y parsea una
respuesta con la estructura de OpenAI. Cambiar a Claude no es cambiar una variable: hay que
reescribir la llamada, adaptar el parseo, manejar errores diferentes y ajustar tokens.

No es teórico. En el ecosistema actual: **los proveedores se caen** (OpenAI y Anthropic han
tenido incidentes); **los precios cambian**; **aparecen modelos mejores cada trimestre**;
**las APIs evolucionan** (params nuevos, formatos, deprecaciones). Si cambiar de modelo
implica refactorizar el backend, no lo harás — y pagarás de más o tendrás peor calidad.

La industria ya resolvió esto antes: hace una década dejamos de escribir SQL a mano contra
cada base de datos y adoptamos **ORMs** (SQLAlchemy, Prisma…). Una capa de abstracción entre
tu lógica y el proveedor de datos. **Lo que un ORM hace para bases de datos, una capa de
abstracción de LLMs lo hace para modelos de lenguaje.**

## Qué es una capa de abstracción de LLMs

Una interfaz unificada entre tu app y los proveedores. En vez de llamar al SDK de OpenAI o
Anthropic, llamas a una función genérica (`completion()`) y la capa traduce al formato del
proveedor configurado. Tu lógica habla un solo idioma; el wrapper traduce a tantos
proveedores como necesites.

De esto (acoplado):
```python
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(model="gpt-4o-mini", messages=[...])
estimation = response.choices[0].message.content
```
A esto (desacoplado):
```python
from litellm import completion
response = completion(
    model="gpt-4o-mini",   # Cambiar a "claude-haiku-4-5" = 0 cambios en lógica
    messages=[...],
)
estimation = response.choices[0].message.content
```
Cambiar de proveedor es ahora **configuración**, no código.

## Construirlo tú mismo vs usar una herramienta existente

Puedes escribir tu propio wrapper, pero **esa clase crece rápido**: mantenimiento continuo
ante cambios de API; re-implementar reintentos con backoff, conteo de tokens, rate limits,
normalización de respuestas, errores por SDK; casos borde no anticipados (timeouts parciales,
respuestas truncadas, fallos intermitentes); y el coste real (tiempo que no inviertes en tu
producto). Un wrapper propio tiene sentido solo cuando tu necesidad es muy específica y
ninguna herramienta la cubre. En la mayoría de proyectos, la abstracción existente merece la pena.

## Herramientas de abstracción

- **LiteLLM (el agregador ligero, el que usamos)** — librería open source con interfaz
  compatible para 100+ modelos de 10+ proveedores. No impone chains/agents/pipelines: solo
  estandariza la llamada. Aporta **Router con fallback y reintentos**, **tracking de costes**,
  **rate limiting** y **proxy mode**. >40.000 estrellas en GitHub.
- **OpenRouter (marketplace)** — una sola API key para decenas de modelos, facturación
  consolidada. Simplicidad operativa, pero tus datos pasan por sus servidores (compliance) y
  aplican margen. Bueno para prototipos.
- **LangChain (framework completo)** — abstracción como parte de chains/agents/memoria/tools.
  Para *solo* abstraer, está sobredimensionado ("usar Rails para una página estática").
  Brilla en orquestación compleja (módulos 4 y 5).

Ejemplo de fallback con el Router de LiteLLM:
```python
from litellm import Router
router = Router(
    model_list=[
        {"model_name": "estimator", "litellm_params": {"model": "gpt-4o-mini", "api_key": "sk-..."}},
        {"model_name": "estimator", "litellm_params": {"model": "claude-haiku-4-5", "api_key": "sk-ant-..."}},
    ],
    num_retries=2,
)
response = router.completion(model="estimator", messages=[...])
```
El código usa el **nombre lógico** `estimator`; el Router decide el modelo físico y rota si hay fallos.

> **Seguridad de dependencias:** en marzo de 2026 las versiones 1.82.7 y 1.82.8 de LiteLLM
> en PyPI fueron comprometidas con código malicioso. Se detectaron y bloquearon rápido, pero
> es un recordatorio: **fija versiones** en tu `pyproject.toml` y verifica hashes. Aplica a
> cualquier dependencia.

## Estrategias de fallback

- **Secuencial (la más común)** — lista ordenada de proveedores; intenta el 1º, si falla el
  2º, etc. El orden refleja tu preferencia (primero el más barato/rápido).
- **Por tipo de error** — no todos los errores merecen fallback. Auth (key inválida) → no
  reintentar. Timeout → reintentar. 429 (rate limit) → esperar/rotar. Configuración granular:
  ```python
  def call_with_fallback(messages, providers):
      for provider in providers:
          try:
              return provider.call(messages)
          except AuthenticationError:
              raise            # no tiene sentido reintentar ni rotar
          except RateLimitError:
              continue         # rotar al siguiente
          except TimeoutError:
              if provider.retries_left > 0: provider.retry_with_backoff()
              else: continue
          except ServerError:
              continue
      raise AllProvidersFailedError()
  ```
- **Routing por complejidad (avanzado)** — transcripciones simples → modelo económico;
  complejas → modelo potente. No es fallback, es routing inteligente (sesiones de agentes).

## Criterios para elegir tu herramienta
- **Privacidad** — ¿pueden tus datos pasar por terceros? Si no, descarta proxies externos
  (OpenRouter). LiteLLM mantiene llamadas directas a tu proveedor.
- **Complejidad** — solo abstracción+fallback → LiteLLM; orquestación de agentes → LangChain;
  marketplace con factura única → OpenRouter.
- **Overhead operativo** — LiteLLM librería = `pip install` + 1 línea; LiteLLM proxy = infra;
  LangChain = aprender un framework.
- **Madurez** — todas maduras a estas alturas.

> La abstracción de proveedores **no es un lujo arquitectónico, es un requisito** para
> cualquier sistema con LLMs que aspire a producción. El coste de implementarla es mínimo;
> el de no tenerla aparece el día que tu proveedor se cae, sube precios o depreca tu modelo.

## Recursos
- ProxAI — "The LLM Abstraction Layer: Why Your Codebase Needs One in 2025"
- LiteLLM — docs oficiales (Getting Started, Router) · docs.litellm.ai
