"""Wrapper de abstracción de proveedores (el corazón de la sesión 03).

Este módulo es la capa que se coloca ENTRE la lógica de negocio (el estimador) y
los proveedores de LLM (OpenAI, Anthropic, ...). Es el equivalente a un ORM, pero
para modelos de lenguaje: tu código habla un solo idioma y el wrapper traduce.

Reúne las cuatro capas de la sesión:

  1. ABSTRACCIÓN  -> usamos LiteLLM (`litellm.completion`), que expone una interfaz
                     única compatible con 100+ modelos. Cambiar de proveedor es
                     configuración ("gpt-4o-mini" -> "anthropic/claude-haiku-4-5"),
                     no código.
  2. FALLBACK     -> recorremos una lista de proveedores por prioridad. Si el
                     primero falla, rotamos al siguiente, clasificando el error
                     (auth / rate-limit / timeout / server) para decidir qué hacer.
  3. CACHEO       -> antes de llamar al LLM consultamos la caché exact-match.
  4. OBSERVABILIDAD -> cada llamada (directa, de caché o vía fallback) se registra
                     con structlog: modelo, tokens, coste, latencia, cache_hit...

El estimador (capa de negocio) solo llama a `complete()` o `stream()`. No sabe ni
le importa qué proveedor respondió: recibe un resultado normalizado.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field

import litellm

from app.cache import build_cache_key, get_cache
from app.config import get_settings
from app.logging_config import get_logger

# LiteLLM por defecto manda telemetría y, ante params no soportados por un
# proveedor, puede fallar. Lo silenciamos y le pedimos que ignore params extra.
litellm.telemetry = False
litellm.drop_params = True

logger = get_logger(component="llm_wrapper")


# ── Excepciones de LiteLLM que clasificamos para el fallback ────────────────
# LiteLLM normaliza los errores de todos los proveedores a las clases de OpenAI.
# Importamos defensivamente: si una clase no existe en la versión instalada,
# usamos Exception como sustituto para no romper el import.
def _exc(name: str) -> type[BaseException]:
    return getattr(litellm, name, Exception)


AuthenticationError = _exc("AuthenticationError")
RateLimitError = _exc("RateLimitError")
Timeout = _exc("Timeout")
APIConnectionError = _exc("APIConnectionError")
ServiceUnavailableError = _exc("ServiceUnavailableError")
InternalServerError = _exc("InternalServerError")

# Errores que justifican ROTAR al siguiente proveedor (el problema es del proveedor,
# no de nuestra petición).
RETRYABLE_ERRORS: tuple[type[BaseException], ...] = (
    RateLimitError,
    Timeout,
    APIConnectionError,
    ServiceUnavailableError,
    InternalServerError,
)


class AllProvidersFailedError(RuntimeError):
    """Se lanza cuando NINGÚN proveedor de la lista de fallback consiguió responder."""


@dataclass
class LLMResult:
    """Resultado normalizado de una llamada, sea del proveedor que sea o de caché."""

    content: str
    model: str
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    cache_hit: bool = False
    fallback_used: bool = False
    finish_reason: str | None = None
    providers_tried: list[str] = field(default_factory=list)


def _resolve_model(provider: str) -> tuple[str, str]:
    """Traduce un proveedor lógico ("openai"/"anthropic") a (model_id, api_key) de LiteLLM."""
    settings = get_settings()
    if provider == "openai":
        return settings.openai_model, settings.openai_api_key
    if provider == "anthropic":
        # LiteLLM identifica los modelos de Anthropic con el prefijo "anthropic/".
        return f"anthropic/{settings.anthropic_model}", settings.anthropic_api_key
    raise ValueError(f"Proveedor desconocido: '{provider}'. Usa 'openai' o 'anthropic'.")


def _available_providers() -> list[str]:
    """Proveedores del orden de fallback que TIENEN api key configurada.

    No tiene sentido intentar un proveedor sin credenciales: lo saltamos de salida.
    """
    settings = get_settings()
    out: list[str] = []
    for provider in settings.fallback_providers:
        try:
            _model, api_key = _resolve_model(provider)
        except ValueError:
            continue
        if api_key:
            out.append(provider)
    return out


def _estimate_cost(response: object, model: str) -> float:
    """Calcula el coste en USD de una respuesta. Defensivo: si no hay precio, 0.0."""
    try:
        return float(litellm.completion_cost(completion_response=response))
    except Exception:  # modelo sin precio en el mapa de LiteLLM, etc.
        return 0.0


class LLMWrapper:
    """Punto de entrada único para llamar al LLM con abstracción + fallback + caché + logs."""

    # ── Llamada síncrona (no streaming) ─────────────────────────────────────
    def complete(self, system_prompt: str, conversation: list[dict]) -> LLMResult:
        settings = get_settings()
        providers = _available_providers()
        if not providers:
            # Sin ninguna API key no podemos llamar a nadie: error de configuración.
            raise ValueError(
                "No hay ningún proveedor con API key configurada. "
                "Rellena OPENAI_API_KEY o ANTHROPIC_API_KEY en el .env."
            )

        # 1) CACHÉ: ¿ya tenemos esta respuesta? La clave depende del primer modelo
        #    (el preferido) + el system prompt + los parámetros.
        primary_model, _ = _resolve_model(providers[0])
        cache_key = build_cache_key(
            messages=conversation,
            model=primary_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            system_prompt=system_prompt,
        )
        cache = get_cache()
        if settings.cache_enabled:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.info("llm_cache_hit", model=cached.get("model"), key=cache_key[:18])
                result = LLMResult(**cached)
                result.cache_hit = True
                result.latency_ms = 0.0
                return result

        # 2) LLM con FALLBACK: probamos proveedores por orden.
        messages = [{"role": "system", "content": system_prompt}, *conversation]
        tried: list[str] = []
        last_error: Exception | None = None

        for index, provider in enumerate(providers):
            is_fallback = index > 0
            model, api_key = _resolve_model(provider)
            tried.append(provider)
            call_log = logger.bind(provider=provider, model=model, fallback=is_fallback)
            call_log.info("llm_call_started")
            start = time.perf_counter()
            try:
                response = litellm.completion(
                    model=model,
                    messages=messages,
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                    api_key=api_key,
                )
                latency_ms = (time.perf_counter() - start) * 1000
                usage = response.usage
                result = LLMResult(
                    content=response.choices[0].message.content or "",
                    model=model,
                    provider=provider,
                    tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
                    tokens_out=getattr(usage, "completion_tokens", 0) or 0,
                    cost_usd=_estimate_cost(response, model),
                    latency_ms=round(latency_ms, 1),
                    cache_hit=False,
                    fallback_used=is_fallback,
                    finish_reason=response.choices[0].finish_reason,
                    providers_tried=tried.copy(),
                )
                call_log.info(
                    "llm_call_completed",
                    latency_ms=result.latency_ms,
                    tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out,
                    cost_usd=round(result.cost_usd, 6),
                    finish_reason=result.finish_reason,
                    fallback_used=is_fallback,
                )
                # 3) Guardamos en caché para la próxima vez (sin marcas de tiempo/coste
                #    de ESTA llamada concreta, que se rellenan al servir).
                if settings.cache_enabled:
                    cache.set(cache_key, asdict(result))
                return result

            except AuthenticationError as exc:
                # Key inválida: reintentar con el mismo proveedor no sirve. Rotamos,
                # por si otro proveedor tiene credenciales válidas, pero lo avisamos.
                latency_ms = (time.perf_counter() - start) * 1000
                last_error = exc
                call_log.error(
                    "llm_call_failed",
                    error_type="AuthenticationError",
                    error_msg=str(exc),
                    latency_ms=round(latency_ms, 1),
                    action="rotate_provider",
                )
                continue
            except RETRYABLE_ERRORS as exc:
                # Problema temporal del proveedor (rate limit, timeout, 5xx): rotamos.
                latency_ms = (time.perf_counter() - start) * 1000
                last_error = exc
                call_log.warning(
                    "fallback_triggered",
                    error_type=type(exc).__name__,
                    error_msg=str(exc),
                    latency_ms=round(latency_ms, 1),
                    next_provider=providers[index + 1] if index + 1 < len(providers) else None,
                )
                continue
            except Exception as exc:  # cualquier otro error inesperado: rotamos
                latency_ms = (time.perf_counter() - start) * 1000
                last_error = exc
                call_log.error(
                    "llm_call_failed",
                    error_type=type(exc).__name__,
                    error_msg=str(exc),
                    latency_ms=round(latency_ms, 1),
                    action="rotate_provider",
                )
                continue

        # Si llegamos aquí, todos los proveedores fallaron.
        logger.error("all_providers_failed", providers_tried=tried)
        raise AllProvidersFailedError(
            f"Todos los proveedores fallaron ({', '.join(tried)}). Último error: {last_error}"
        ) from last_error

    # ── Llamada en STREAMING (token a token) ─────────────────────────────────
    def stream(
        self, system_prompt: str, conversation: list[dict], *, meta: dict | None = None
    ) -> Iterator[str]:
        """Generador que produce el texto de la respuesta token a token.

        Pensado para `st.write_stream` (Streamlit) y para el endpoint SSE. Como un
        generador no puede a la vez "yield" texto y "return" metadatos, los metadatos
        de la última llamada (modelo, tokens, coste, latencia, cache_hit) se vuelcan
        en el dict `meta` que pase el llamante.

        Interacción con la caché (ver material de streaming): si hay cache hit,
        devolvemos la respuesta completa de golpe (no hay nada que "escribir en vivo",
        ya la tenemos). Si no, hacemos streaming real y al terminar guardamos en caché.
        """
        meta = meta if meta is not None else {}
        settings = get_settings()
        providers = _available_providers()
        if not providers:
            raise ValueError(
                "No hay ningún proveedor con API key configurada. "
                "Rellena OPENAI_API_KEY o ANTHROPIC_API_KEY en el .env."
            )

        primary_model, _ = _resolve_model(providers[0])
        cache_key = build_cache_key(
            messages=conversation,
            model=primary_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            system_prompt=system_prompt,
        )
        cache = get_cache()
        if settings.cache_enabled:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.info("llm_cache_hit", model=cached.get("model"), streaming=True)
                meta.update({**cached, "cache_hit": True, "latency_ms": 0.0})
                yield cached["content"]  # de golpe: ya la teníamos
                return

        messages = [{"role": "system", "content": system_prompt}, *conversation]
        tried: list[str] = []
        last_error: Exception | None = None

        for index, provider in enumerate(providers):
            is_fallback = index > 0
            model, api_key = _resolve_model(provider)
            tried.append(provider)
            call_log = logger.bind(provider=provider, model=model, fallback=is_fallback, streaming=True)
            call_log.info("llm_call_started")
            start = time.perf_counter()
            chunks: list[str] = []
            try:
                response = litellm.completion(
                    model=model,
                    messages=messages,
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                    api_key=api_key,
                    stream=True,
                )
                for chunk in response:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        chunks.append(delta)
                        yield delta  # <- el usuario ve el texto "escribiéndose"

                full_text = "".join(chunks)
                latency_ms = (time.perf_counter() - start) * 1000
                # En streaming el usage no siempre viene; lo estimamos con el tokenizer
                # de LiteLLM para no perder la trazabilidad de tokens/coste.
                tokens_in, tokens_out, cost = _stream_usage(model, messages, full_text)
                result = LLMResult(
                    content=full_text,
                    model=model,
                    provider=provider,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost,
                    latency_ms=round(latency_ms, 1),
                    cache_hit=False,
                    fallback_used=is_fallback,
                    finish_reason="stop",
                    providers_tried=tried.copy(),
                )
                call_log.info(
                    "llm_call_completed",
                    latency_ms=result.latency_ms,
                    tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out,
                    cost_usd=round(result.cost_usd, 6),
                    fallback_used=is_fallback,
                )
                if settings.cache_enabled:
                    cache.set(cache_key, asdict(result))
                meta.update(asdict(result))
                return

            except RETRYABLE_ERRORS as exc:
                last_error = exc
                call_log.warning("fallback_triggered", error_type=type(exc).__name__, error_msg=str(exc))
                continue
            except Exception as exc:
                last_error = exc
                call_log.error("llm_call_failed", error_type=type(exc).__name__, error_msg=str(exc))
                continue

        logger.error("all_providers_failed", providers_tried=tried)
        raise AllProvidersFailedError(
            f"Todos los proveedores fallaron ({', '.join(tried)}). Último error: {last_error}"
        ) from last_error


def _stream_usage(model: str, messages: list[dict], output: str) -> tuple[int, int, float]:
    """Estima tokens de entrada/salida y coste para una respuesta en streaming.

    Defensivo: si el tokenizer o el mapa de precios no conocen el modelo, devolvemos
    ceros para no romper la trazabilidad.
    """
    try:
        tokens_in = litellm.token_counter(model=model, messages=messages)
        tokens_out = litellm.token_counter(model=model, text=output)
    except Exception:
        return 0, 0, 0.0
    try:
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=model, prompt_tokens=tokens_in, completion_tokens=tokens_out
        )
        cost = float(prompt_cost) + float(completion_cost)
    except Exception:
        cost = 0.0
    return tokens_in, tokens_out, cost


# Instancia única reutilizable (el wrapper no guarda estado entre llamadas).
wrapper = LLMWrapper()
