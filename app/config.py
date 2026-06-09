"""Configuración centralizada de la aplicación.

Usamos Pydantic BaseSettings para cargar y VALIDAR las variables de entorno
desde el archivo .env. Ventajas frente a leer os.environ a mano:
  - Tipado y validación automática (p. ej. LLM_TEMPERATURE se convierte a float).
  - Valores por defecto declarativos.
  - Un único punto de verdad para toda la config del proyecto.

En la sesión 03 ampliamos esta config con los parámetros de las nuevas capas:
fallback de proveedores, cacheo y logging. Todo es configuración, no código:
cambiar de proveedor, activar/desactivar la caché o subir el nivel de log no
requiere tocar la lógica de negocio.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Le dice a Pydantic de dónde leer las variables y cómo comportarse.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignora variables del .env que no estén declaradas aquí
    )

    # ── Proveedores ────────────────────────────────────────────────────────
    # Proveedor "preferido" (compatibilidad con la sesión 02). El wrapper de la
    # sesión 03 usa más bien provider_fallback_order para decidir el orden.
    llm_provider: str = "openai"

    # Orden de fallback: lista separada por comas. El wrapper intenta el primero;
    # si falla (timeout, rate limit, caída del proveedor), rota al siguiente.
    # Solo se usan los proveedores para los que haya API key configurada.
    provider_fallback_order: str = "openai,anthropic"

    # Claves de API. Por defecto vacías para que el proyecto no reviente al importar;
    # validamos su presencia en el wrapper, justo antes de llamar al LLM.
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Modelos económicos por defecto. Son nombres lógicos; el wrapper los traduce
    # al identificador que espera LiteLLM (a Anthropic le antepone "anthropic/").
    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-haiku-4-5"

    # Parámetros de generación.
    llm_temperature: float = 0.7
    llm_max_tokens: int = 1500

    # Multi-turn: nº máximo de turnos (pares user+assistant) que se conservan del
    # historial. La "ventana deslizante" descarta los más antiguos al superarlo,
    # para que la conversación no crezca sin control (ver material 05 de la sesión 02).
    llm_max_history_turns: int = 10

    # ── Cacheo (sesión 03) ─────────────────────────────────────────────────
    # Cacheo exact-match de respuestas. Misma transcripción + mismo contexto =
    # misma estimación, así que la segunda vez la servimos de caché (instantáneo,
    # coste 0). Ver tutorial 03 y el material "Cacheo inteligente".
    cache_enabled: bool = True
    # Backend de la caché: "memory" (por defecto, sin infra) o "redis".
    cache_backend: str = "memory"
    # TTL en segundos. 24h es razonable para estimaciones (no cambian de un día
    # para otro). Para datos en tiempo real usaríamos minutos.
    cache_ttl_seconds: int = 86_400
    # URL de Redis (solo si cache_backend="redis").
    redis_url: str = "redis://localhost:6379/0"

    # ── Observabilidad / logging (sesión 03) ───────────────────────────────
    # "development" -> logs de consola legibles y coloreados.
    # "production"  -> logs en JSON, listos para Elasticsearch/Loki/CloudWatch.
    env: str = "development"
    log_level: str = "INFO"

    @property
    def fallback_providers(self) -> list[str]:
        """Lista de proveedores del orden de fallback, normalizada y sin vacíos."""
        return [p.strip().lower() for p in self.provider_fallback_order.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia única de Settings (cacheada).

    El @lru_cache hace que Settings se construya una sola vez en todo el proceso,
    evitando releer el .env en cada petición. Es el patrón recomendado para
    inyectar la configuración como dependencia en FastAPI.
    """
    return Settings()
