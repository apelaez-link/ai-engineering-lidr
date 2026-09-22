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

    # ── Memoria conversacional (sesión 05) ──────────────────────────────────
    # Tamaño de la ventana deslizante del historial conversacional (en PARES
    # user+assistant). El estimador conversacional reenvía como mucho estos N
    # turnos al LLM; al superarlos, descarta los más antiguos. 6 es un buen
    # equilibrio entre contexto suficiente y coste de tokens controlado.
    max_history_turns: int = 6

    # Modelo usado por el EXTRACTOR de metadatos (un segundo LLM que destila los
    # hechos del proyecto de cada turno vía Instructor). Por defecto reutilizamos
    # un modelo económico de OpenAI; puede apuntarse a uno distinto del de
    # estimación (la tarea de extracción es más simple y barata).
    metadata_extractor_model: str = "gpt-4o-mini"

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

    # ── Persistencia vectorial (sesión 08): PostgreSQL + pgvector ───────────
    # URL de conexión async (driver asyncpg). Apunta a localhost:5433 porque el
    # docker-compose publica el Postgres del proyecto en 5433 (el 5432 suele estar
    # ocupado por otro Postgres local). Corriendo la app dentro de un contenedor de
    # la misma red, el host sería `postgres:5432`. Sobreescribible con DATABASE_URL.
    database_url: str = (
        "postgresql+asyncpg://estimator:estimator@localhost:5433/estimator"
    )

    # ── Recuperación avanzada (sesión 10): híbrida + reranking ──────────────
    # Idioma de la config de full-text search (to_tsvector/plainto_tsquery). DEBE
    # coincidir con la migración 0002 y models_db.FULLTEXT_CONFIG. Nuestro corpus está
    # en inglés (el enunciado usa 'spanish' para su dataset en español).
    fulltext_language: str = "english"
    # Constante k de Reciprocal Rank Fusion (amortiguación de las primeras posiciones).
    rrf_k: int = 60
    # Anchura de recall: candidatos que pide cada rama antes de fusionar/reordenar. Es
    # la "N" del recall-then-rerank (recupera N amplio, reordena a k pequeño).
    retrieval_candidate_pool: int = 50
    # Reranking con cross-encoder. Apagado por defecto (arrastra torch y añade latencia);
    # se enciende por env RERANK_ENABLED=true o por petición, SIN tocar código.
    rerank_enabled: bool = False
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # ── Cacheo SEMÁNTICO (sesión 04) ────────────────────────────────────────
    # A diferencia del exact-match, el cacheo semántico captura reformulaciones:
    # dos descripciones distintas con la MISMA intención comparten respuesta.
    # Embebe la descripción y busca por similitud coseno dentro de un "bucket"
    # determinista (mismos parámetros). Store en memoria por defecto (sin infra);
    # en producción se usaría redisvl/Redis como backend vectorial.
    semantic_cache_enabled: bool = True
    # Modelo de embeddings (configurable). Default económico de OpenAI.
    semantic_cache_embedding_model: str = "text-embedding-3-small"
    # Umbral de similitud coseno para considerar HIT (0-1). 0.92 es conservador:
    # exige descripciones muy parecidas semánticamente para reutilizar respuesta.
    semantic_cache_threshold: float = 0.92

    # ── Capa de agentes (sesión 12): agente a mano sobre la Responses API ───
    # Modelo del agente. El enunciado pide gpt-5 medium. La Responses API funciona
    # también con gpt-4o/gpt-4o-mini: si tu cuenta no tiene acceso a gpt-5, pon
    # AGENT_MODEL=gpt-4o (el bucle detecta que no es modelo de razonamiento y omite
    # el parámetro `reasoning`). Para DEPURAR el bucle barato: gpt-5-mini / gpt-4o-mini.
    agent_model: str = "gpt-5"
    # Esfuerzo de razonamiento (solo aplica a modelos gpt-5/o*; se ignora en gpt-4o).
    agent_reasoning_effort: str = "medium"
    # CONDICIÓN DE PARADA del bucle: tope de vueltas antes de forzar el cierre.
    agent_max_steps: int = 8
    # Referencias que devuelve cada llamada a search_budgets (recall acotado = menos
    # contexto arrastrado = menos coste; ver lección 6).
    agent_search_k: int = 5

    # ── Orquestación con LangGraph (sesión 13) ─────────────────────────────
    # Checkpointer del grafo: persiste el estado por thread_id en Postgres
    # (AsyncPostgresSaver). Crea SUS PROPIAS tablas (checkpoints...), convive con
    # pgvector en la misma BBDD. Apágalo (false) para correr el grafo sin persistencia.
    graph_checkpointer_enabled: bool = True
    # DSN del checkpointer en formato PSYCOPG (postgresql://…), NO +asyncpg: langgraph
    # usa psycopg, no asyncpg. Mismo Postgres del proyecto (localhost:5433).
    graph_checkpointer_url: str = (
        "postgresql://estimator:estimator@localhost:5433/estimator"
    )
    # Observabilidad del grafo con Logfire (span por nodo). Con LOGFIRE_TOKEN exporta a
    # la nube de Logfire; sin token corre en local sin enviar nada.
    logfire_enabled: bool = True

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
