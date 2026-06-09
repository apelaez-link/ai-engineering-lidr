# 02 — Abstracción de proveedores y fallback

> 📚 **Concepto del curso:** [material_curso/02](material_curso/02-abstraccion-y-fallback.md)
> 🧩 **Código:** `app/services/llm_wrapper.py`

## La idea en una frase

El wrapper es a los LLMs lo que un ORM a las bases de datos: tu código habla un solo idioma y
una capa traduce a cualquier proveedor. Cambiar de OpenAI a Anthropic es **configuración**, no
una refactorización.

## El antes (sesión 02) y el después

En la sesión 02, `llm_service.py` tenía `_generate_openai()` y `_generate_anthropic()` y un
`if provider == "openai" / elif "anthropic"`. Cada proveedor con su SDK, su parseo, sus
errores. Añadir un tercero = otra función + otra rama + otro manejo de errores.

Ahora todo eso desaparece tras **una sola llamada**: `litellm.completion(model=..., messages=...)`.
LiteLLM expone una interfaz compatible con OpenAI para 100+ modelos. La diferencia entre
OpenAI y Anthropic la absorbe la librería.

## Recorrido por el código (`llm_wrapper.py`)

**Traducción proveedor → modelo de LiteLLM:**
```python
def _resolve_model(provider):
    if provider == "openai":    return settings.openai_model, settings.openai_api_key
    if provider == "anthropic": return f"anthropic/{settings.anthropic_model}", settings.anthropic_api_key
```
A Anthropic se le antepone `anthropic/` (así LiteLLM sabe a quién llamar). Eso es *todo* lo
específico de cada proveedor que queda en el código.

**Qué proveedores hay disponibles** — solo los del orden de fallback que tengan API key:
```python
def _available_providers():
    return [p for p in settings.fallback_providers if _resolve_model(p)[1]]   # [1] = api_key
```
El orden lo controla `PROVIDER_FALLBACK_ORDER=openai,anthropic` en el `.env`.

**El bucle de fallback** (versión resumida de `complete()`):
```python
for index, provider in enumerate(providers):
    is_fallback = index > 0
    model, api_key = _resolve_model(provider)
    try:
        response = litellm.completion(model=model, messages=messages,
                                      temperature=..., max_tokens=..., api_key=api_key)
        # ... normaliza, loguea, cachea y DEVUELVE
        return result
    except AuthenticationError:
        continue          # key inválida: rota (otro proveedor puede tener key buena)
    except RETRYABLE_ERRORS:   # rate limit, timeout, 5xx, conexión
        continue          # problema del proveedor: rota al siguiente
    except Exception:
        continue          # error inesperado: rota
raise AllProvidersFailedError(...)   # nadie respondió
```

Esto implementa el **fallback secuencial** + **fallback por tipo de error** del material:
clasificamos la excepción y decidimos. La clave didáctica: el `try/except` **no propaga** el
error del primer proveedor; lo registra y **rota**. El llamante (el servicio CAG) solo ve éxito
o un `AllProvidersFailedError` final.

**Resultado normalizado** — da igual quién responda, siempre devolvemos un `LLMResult`:
```python
@dataclass
class LLMResult:
    content: str; model: str; provider: str
    tokens_in: int; tokens_out: int; cost_usd: float; latency_ms: float
    cache_hit: bool; fallback_used: bool; finish_reason: str | None; providers_tried: list
```
El servicio y el router trabajan contra este contrato estable, no contra la respuesta cruda de
OpenAI/Anthropic. Esa normalización es lo que hace intercambiables a los proveedores.

## ¿Por qué LiteLLM y no un wrapper 100% casero?

Usamos LiteLLM para la **abstracción** (la traducción a cada SDK, el conteo de tokens, el mapa
de precios) pero escribimos a mano el **bucle de fallback** — porque es donde está el valor
didáctico y porque queremos control sobre la clasificación de errores. En producción podrías
delegar también el fallback al `litellm.Router` (ver material). Es el equilibrio que recomienda
el curso: no reinventes lo resuelto (SDKs, tokens, precios), pero entiende y controla tu política.

> ⚠️ **Seguridad de dependencias.** En `pyproject.toml` verás
> `litellm>=1.74,!=1.82.7,!=1.82.8`. Esas dos versiones fueron comprometidas en PyPI en marzo
> de 2026. Fijar/excluir versiones es la lección: aplica a cualquier dependencia.

## Reto

1. **Cambia de proveedor sin tocar código:** en `.env`, pon `PROVIDER_FALLBACK_ORDER=anthropic,openai`
   (con ambas keys). Reinicia y mira el campo `provider` de la respuesta: ahora responde Anthropic.
2. **Provoca un fallback de verdad:** deja `OPENAI_API_KEY` con un valor inválido (`sk-roto`) y
   una `ANTHROPIC_API_KEY` válida, con orden `openai,anthropic`. Lanza una estimación: en los
   logs verás `llm_call_failed` (openai) → `llm_call_completed` (anthropic) y la respuesta
   traerá `fallback_used: true`.
3. **Test:** lee `tests/test_wrapper.py::test_fallback_rotates_to_next_provider`. Mockea el
   primer `litellm.completion` para que lance, y comprueba que el segundo responde. Añade un
   caso donde *ambos* fallen y se levante `AllProvidersFailedError`.
