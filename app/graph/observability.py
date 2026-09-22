"""Observabilidad del grafo con Logfire (sesión 13, Nivel 2).

El enunciado pide una TRAZA con un span por nodo. Logfire (de Pydantic) es un backend de
tracing OpenTelemetry: cada `logfire.span("node: X")` abre un tramo cronometrado y
anidado, así ves el árbol de ejecución del grafo (qué nodo, cuánto tardó, con qué datos).

Lo hacemos robusto para el tutorial:
  - `configure_logfire()` se llama una vez. Con `send_to_logfire="if-token-present"`,
    Logfire exporta a su nube SOLO si hay un token (LOGFIRE_TOKEN) configurado; si no,
    funciona en local sin enviar nada. Así el grafo corre sin obligarte a crear cuenta.
  - `span(name, **attrs)` devuelve el span de Logfire si está configurado, o un
    nullcontext si no (o si Logfire falla al importar): los nodos no se enteran.
"""

from __future__ import annotations

import contextlib
from typing import Any

from app.logging_config import get_logger

logger = get_logger(component="graph_observability")

_configured = False


def configure_logfire(enabled: bool = True, service_name: str = "estimator-graph") -> None:
    """Configura Logfire una sola vez (idempotente). No falla si Logfire no está listo."""
    global _configured
    if _configured or not enabled:
        return
    try:
        import logfire

        # send_to_logfire='if-token-present': exporta a la nube solo si hay LOGFIRE_TOKEN;
        # en local, sin token, no envía nada (pero los spans se crean igual).
        logfire.configure(
            send_to_logfire="if-token-present",
            service_name=service_name,
            console=False,  # sin ruido en consola; los spans se ven en Logfire si hay token
        )
        _configured = True
        logger.info("logfire_configured", service_name=service_name)
    except Exception as exc:  # noqa: BLE001 — la observabilidad nunca debe tumbar el grafo
        logger.warning("logfire_configure_failed", error=str(exc))


def span(name: str, **attributes: Any):
    """Devuelve un span de Logfire (si está configurado) o un nullcontext.

    Uso en un nodo:  `with span("node: extract_requirements"): ...`
    """
    if _configured:
        import logfire

        return logfire.span(name, **attributes)
    return contextlib.nullcontext()
