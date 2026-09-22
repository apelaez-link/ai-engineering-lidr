"""Autenticación servicio-a-servicio con token (sesión 15).

En producción, el servicio IA (este FastAPI) es INTERNO: no se expone a internet. Solo lo
llama el backend de negocio (el gateway), que se identifica con una cabecera
`X-Service-Token`. Este middleware exige ese token en todas las rutas MENOS las de
liveness/documentación, y responde 401 si falta o no coincide.

Diseño para que el repo siga siendo cómodo en local:
  - Si `AI_SERVICE_TOKEN` está VACÍO (por defecto en dev), la autenticación se DESACTIVA:
    puedes arrancar la app con uvicorn y llamarla sin cabeceras, como en S2-S14.
  - En Docker (docker-compose.prod.yml) se define `AI_SERVICE_TOKEN`, así que el token
    pasa a ser OBLIGATORIO y el servicio queda protegido.

Rutas EXENTAS (no requieren token): `/health` (liveness, sin LLM), y la documentación
(`/docs`, `/redoc`, `/openapi.json`) y los estáticos. Todo lo demás exige el token.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings

# Prefijos exentos: liveness + documentación + estáticos.
EXEMPT_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/static")

SERVICE_TOKEN_HEADER = "X-Service-Token"


def _is_exempt(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in EXEMPT_PREFIXES)


class ServiceTokenMiddleware(BaseHTTPMiddleware):
    """Exige `X-Service-Token` salvo en rutas exentas. Se salta si no hay token configurado."""

    async def dispatch(self, request: Request, call_next):
        token = get_settings().ai_service_token
        # Sin token configurado -> auth desactivada (modo desarrollo local).
        if not token:
            return await call_next(request)
        if _is_exempt(request.url.path):
            return await call_next(request)
        provided = request.headers.get(SERVICE_TOKEN_HEADER)
        if provided != token:
            return JSONResponse(
                status_code=401,
                content={"detail": f"missing or invalid {SERVICE_TOKEN_HEADER}"},
            )
        return await call_next(request)
