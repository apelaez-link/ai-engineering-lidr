# Despliegue local del estimador (sesión 15)

Cómo levantar **todo el sistema con un comando**, con las fronteras de red y de secretos
que tendría en producción. El objetivo del ejercicio: que el **servicio IA sea interno**
(no accesible desde internet), que solo lo llame el **gateway** identificándose con un
**token de servicio**, y que los **secretos vivan fuera del código**.

## Arquitectura de servicios

```
                 (host)
                   │  :3000
                   ▼
            ┌──────────────┐   X-Service-Token    ┌──────────────┐
   internet │   gateway    │ ───────────────────▶ │  ai-service  │  (FastAPI, INTERNO)
   ───────▶ │  (nginx)     │   red interna         │  :8000       │  sin puertos al host
            └──────────────┘                       └──────┬───────┘
              público :3000                                │
                                                           ├─▶ postgres (pgvector)  INTERNO
                                                           │     datos + vector + checkpointer
                                                           └─▶ redis (caché)        INTERNO
```

| Servicio | Rol | Exposición |
|---|---|---|
| **gateway** (nginx) | Puerta pública; hace de backend de negocio. Reenvía al servicio IA **inyectando `X-Service-Token`**. | **Público**, `localhost:3000` |
| **ai-service** (FastAPI) | El estimador (S2-S14: CAG→RAG→agentes). | **Interno** — `expose: 8000`, **sin `ports:`** |
| **postgres** (pgvector) | Datos relacionales + vectores + checkpointer del grafo. | Interno |
| **redis** | Backend de la caché. | Interno |

> **Nota sobre "vector-db".** La arquitectura de referencia del curso separa `postgres`
> (negocio) y `vector-db`. **Nuestro proyecto consolida** relacional + vector en un único
> Postgres con **pgvector** (más simple y es como está construida la app: una sola
> `DATABASE_URL`). Por eso aquí el "almacén vectorial" ES el servicio `postgres`. El 4º
> servicio real que sí usamos es `redis` (la caché).

## Variables de entorno

Los secretos **no se versionan**: `.env` está en `.gitignore`; versionamos `.env.example`
como plantilla. `docker compose` lee el `.env` automáticamente.

```bash
cp .env.example .env
# Rellena en .env:
#   OPENAI_API_KEY=sk-...
#   AI_SERVICE_TOKEN=$(openssl rand -hex 32)   # genera un token y pégalo
```

Variables clave para el despliegue:

| Variable | Para qué |
|---|---|
| `OPENAI_API_KEY` | Embeddings + LLM del servicio IA |
| `AI_SERVICE_TOKEN` | Token que el gateway inyecta y el servicio IA exige (401 si falta) |
| `DATABASE_URL` | Postgres async del servicio IA (el compose la fija al servicio `postgres`) |
| `GRAPH_CHECKPOINTER_URL` | DSN psycopg del checkpointer (idem, `postgres`) |

En `docker-compose.prod.yml`, `DATABASE_URL`, `GRAPH_CHECKPOINTER_URL`, `REDIS_URL` y
`CACHE_BACKEND` ya se definen apuntando a los servicios internos: no los pongas en `.env`
para el modo Docker (solo `OPENAI_API_KEY` y `AI_SERVICE_TOKEN`).

## Arranque en un comando

```bash
docker compose -f docker-compose.prod.yml up --build
```

Esto construye la imagen del servicio IA y levanta gateway + ai-service + postgres + redis.
Espera a que `ai-service` esté `healthy` (el healthcheck consulta `/health`).

La **primera vez**, migra el esquema e ingesta los datos **desde dentro** (el servicio IA
no está publicado, así que se ejecuta dentro de su contenedor):

```bash
# migraciones (crea tablas + extensión pgvector + índices)
docker compose -f docker-compose.prod.yml exec ai-service uv run alembic upgrade head

# ingesta de los 15 presupuestos de ejemplo (contra su propio localhost:8000)
docker compose -f docker-compose.prod.yml exec ai-service \
  uv run python scripts/ingest_sample_budgets.py --base-url http://localhost:8000
```

> El checkpointer del grafo (LangGraph) crea sus tablas solo, la primera vez que llamas a
> `/graph/estimate` o `/multiagent/estimate`.

## Comprobaciones de aceptación

```bash
# 1) El gateway (público) responde y expone la liveness del servicio IA (sin token).
curl -s http://localhost:3000/health
# -> {"status":"ok"}

# 2) A través del gateway, una petición real funciona (el gateway inyecta el token).
curl -s -X POST http://localhost:3000/agent/estimate \
  -H "Content-Type: application/json" \
  -d "$(jq -Rs '{transcript: ., model: "gpt-4o"}' examples/transcripts/01_clear.txt)" | jq '.stopped_reason'

# 3) El servicio IA NO es accesible directamente desde el host (no publica puertos).
curl -s http://localhost:8000/health ; echo "  <- connection refused esperado"

# 4) Desde dentro de la red, SIN token la ruta protegida da 401 (el gateway sí lo inyecta).
docker compose -f docker-compose.prod.yml exec ai-service python - <<'PY'
import json, urllib.request, urllib.error
req = urllib.request.Request(
    "http://localhost:8000/graph/estimate",
    data=json.dumps({"transcript": "x"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    urllib.request.urlopen(req)
    print("inesperado: pasó sin token")
except urllib.error.HTTPError as e:
    print("sin token ->", e.code)   # -> sin token -> 401
PY
```

## Parar y limpiar

```bash
docker compose -f docker-compose.prod.yml down        # para los servicios
docker compose -f docker-compose.prod.yml down -v     # + borra los volúmenes (datos)
```

## Qué queda fuera (se ve en el directo / producción real)

CI/CD (pipelines), despliegue en cloud, HTTPS/reverse-proxy con certificados, y gestión de
secretos con un gestor (Vault/SSM). Aquí el objetivo es el **despliegue local
reproducible** con las fronteras correctas.
