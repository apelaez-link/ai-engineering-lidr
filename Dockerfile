# Imagen del servicio IA (FastAPI estimador) — sesión 15.
#
# En producción este servicio es INTERNO: no publica puertos al host; solo lo alcanza el
# gateway por la red de docker-compose. Construimos con uv (mismo gestor que en local).
FROM python:3.12-slim

# uv respeta estas variables; bytecode compilado y copia (no symlink) para el runtime.
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# uv como binario estático oficial (rápido, sin pip).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 1) Capa de dependencias: copiamos solo los manifiestos y resolvemos con el lockfile.
#    Al no cambiar pyproject/uv.lock, Docker CACHEA esta capa entre builds de código.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# 2) Código de la app + instalación del propio proyecto.
COPY . .
RUN uv sync --frozen

EXPOSE 8000

# Liveness sin curl (no está en slim): urllib contra /health.
HEALTHCHECK --interval=10s --timeout=5s --retries=12 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/health').status==200 else sys.exit(1)"]

# Arranca el servidor escuchando en todas las interfaces de la red del contenedor.
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
