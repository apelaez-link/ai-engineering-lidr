# Sesión 15 — Cómo ejecutarlo paso a paso (Dockerización)

La S15 no añade una funcionalidad nueva al estimador: **empaqueta** todo lo construido
(S2-S14) como un sistema de servicios que arranca con un comando, con las fronteras de red
y de secretos de producción. El entregable principal es
[`docs/deployment-local.md`](../../docs/deployment-local.md) — esta guía lo resume y explica
qué aprender.

Artefactos nuevos:
- [`Dockerfile`](../../Dockerfile) — imagen del servicio IA (FastAPI) con uv.
- [`docker-compose.prod.yml`](../../docker-compose.prod.yml) — el stack completo (gateway +
  ai-service + postgres + redis).
- [`deploy/gateway.conf.template`](../../deploy/gateway.conf.template) — nginx público que
  inyecta el `X-Service-Token`.
- [`app/security.py`](../../app/security.py) — middleware que exige el token (401 si falta).
- [`.env.example`](../../.env.example) actualizado (incluye `AI_SERVICE_TOKEN`).

---

## Dos formas de ejecutar

### A) Local con uv (como en S2-S14) — sigue funcionando

Sin `AI_SERVICE_TOKEN`, la autenticación está **desactivada** y todo va como antes:

```bash
uv run pytest tests/test_service_token.py -q     # 3 passed
uv run uvicorn app.main:app --reload
curl -s http://localhost:8000/health             # {"status":"ok"}
```

### B) El stack Docker de producción (lo nuevo de la S15)

Receta completa en [`docs/deployment-local.md`](../../docs/deployment-local.md). Resumen:

```bash
cp .env.example .env
#   rellena OPENAI_API_KEY y genera AI_SERVICE_TOKEN=$(openssl rand -hex 32)

docker compose -f docker-compose.prod.yml up --build
```

> ⏳ El primer `--build` descarga e instala las dependencias (incluido torch): tarda y la
> imagen es grande. Es normal.

Migra e ingesta la primera vez (desde DENTRO, porque el servicio IA no está publicado):

```bash
docker compose -f docker-compose.prod.yml exec ai-service uv run alembic upgrade head
docker compose -f docker-compose.prod.yml exec ai-service \
  uv run python scripts/ingest_sample_budgets.py --base-url http://localhost:8000
```

## Qué comprobar (y por qué importa)

1. **El sistema arranca con un comando** y el gateway responde en `localhost:3000`:
   ```bash
   curl -s http://localhost:3000/health      # {"status":"ok"} (vía gateway, sin token)
   ```
2. **A través del gateway, una petición real funciona** (el gateway inyecta el token):
   ```bash
   curl -s -X POST http://localhost:3000/agent/estimate -H "Content-Type: application/json" \
     -d "$(jq -Rs '{transcript: ., model: "gpt-4o"}' examples/transcripts/01_clear.txt)" | jq '.stopped_reason'
   ```
3. **El servicio IA NO es accesible desde el host** (no publica puertos):
   ```bash
   curl -s http://localhost:8000/health      # connection refused (esperado)
   ```
4. **Sin token válido → 401** (comprobación desde dentro de la red): ver el paso 4 de
   `docs/deployment-local.md`.

Estas 4 comprobaciones SON los criterios de aceptación del ejercicio: servicio IA aislado,
puerta pública única, token obligatorio y arranque reproducible.

## El detalle del token (qué mirar en el código)

- [`app/security.py`](../../app/security.py): el middleware exime `/health` y la
  documentación, y exige `X-Service-Token` en el resto. **Si `AI_SERVICE_TOKEN` está vacío,
  no exige nada** (por eso el modo local A sigue cómodo).
- [`deploy/gateway.conf.template`](../../deploy/gateway.conf.template): nginx añade
  `proxy_set_header X-Service-Token "${AI_SERVICE_TOKEN}"` al reenviar. El token se
  sustituye al arrancar el contenedor (envsubst), nunca vive en el código.

## Conexión con el Proyecto Final

Esta es la **capa de despliegue** del capstone: tu copiloto tendrá el mismo patrón — un
gateway/frontend público y el **servicio IA aislado** (no llamable desde internet), con
token de servicio, `/health` y secretos fuera del código. `docs/deployment-local.md` es
directamente uno de los artefactos que pide el Proyecto Final.
