"""Logging estructurado con structlog (lección "Observabilidad, logging y trazabilidad").

¿Por qué no el logging normal? Porque con LLMs el `print`/`logging` clásico es
ciego: sabes que /estimate devolvió 200 en 4.2 s, pero no qué modelo respondió,
cuántos tokens gastó, cuánto costó, ni si vino de caché o de un fallback.

structlog trata los logs como DATOS, no como strings. Cada evento es un objeto con
campos tipados (model, tokens_in, cost_usd, latency_ms, cache_hit, fallback_used...)
que luego puedes filtrar, agregar y graficar sin parsear texto con regex.

Configuración DUAL — el patrón que usarás en casi todo proyecto:
  - development -> consola coloreada y legible para humanos.
  - production  -> JSON, directamente ingerible por Elasticsearch/Loki/CloudWatch/
                   Logfire/Langfuse.
"""

import logging

import structlog

from app.config import get_settings


def configure_logging() -> None:
    """Configura structlog una sola vez, al arrancar la app.

    La pieza clave es la CADENA DE PROCESADORES: cada procesador recibe el
    diccionario del evento, lo enriquece (nivel, timestamp...) y lo pasa al
    siguiente. El último de la cadena es siempre el *renderer* que decide el
    formato final (consola bonita vs JSON).
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Procesadores comunes a desarrollo y producción.
    shared_processors = [
        structlog.contextvars.merge_contextvars,  # incluye contexto vinculado por request
        structlog.processors.add_log_level,        # añade "level": info/warning/error
        structlog.processors.TimeStamper(fmt="iso"),  # "timestamp" en ISO-8601
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,      # serializa excepciones si las hay
    ]

    if settings.env.lower() == "production":
        # Producción: JSON de una línea por evento.
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        # Desarrollo: salida coloreada y alineada, fácil de leer en el terminal.
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        # filtra por nivel ANTES de procesar (más eficiente que filtrar al final).
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(**initial_context: object) -> structlog.stdlib.BoundLogger:
    """Atajo para obtener un logger, opcionalmente con contexto ya vinculado.

    Ejemplo:
        log = get_logger(component="llm_wrapper")
        log.info("llm_call_started", model="gpt-4o-mini")
    """
    return structlog.get_logger().bind(**initial_context)
