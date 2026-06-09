"""Punto de entrada de la aplicación FastAPI.

Aquí se ensambla todo: se configura el logging estructurado, se crea la app, se
registra el router de estimaciones bajo el prefijo /api/v1 y se expone /health.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.logging_config import configure_logging, get_logger
from app.routers import estimations

# Configuramos structlog ANTES de crear la app, para que cualquier log de arranque
# (y todos los de las peticiones) salga ya con el formato correcto.
configure_logging()
logger = get_logger(component="app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la app (patrón moderno que sustituye a @app.on_event)."""
    logger.info("app_started", version=app.version)
    yield
    logger.info("app_stopped")


app = FastAPI(
    title="Estimador CAG — Pro (sesión 03)",
    description=(
        "Servicio que genera estimaciones de software a partir de transcripciones de "
        "reunión usando arquitectura CAG. Sobre el endpoint de la sesión 02 añade un "
        "wrapper con abstracción de proveedores + fallback, cacheo, streaming (SSE) y "
        "trazabilidad con structlog."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# Registramos el router. Todos sus endpoints colgarán de /api/v1
# -> POST /estimate queda en POST /api/v1/estimate, etc.
app.include_router(estimations.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health() -> dict:
    """Comprobación de salud del servicio. Útil para monitorización y CI/CD."""
    return {"status": "ok"}
