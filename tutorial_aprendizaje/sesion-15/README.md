# Sesión 15 — Despliegue y puesta en producción (catch-up)

> **Módulo 6.** Nota de estudio consolidada (compilada del **ejercicio completo** + índice de
> lecciones + conceptos). El salto de la S15: dejar de ejecutar el estimador "en mi máquina" y
> empaquetarlo como un **sistema de servicios** que arranca con **un comando**, con fronteras de
> red y de credenciales pensadas para producción.

## Idea central
"Producción" no es un servidor: es un conjunto de **propiedades** — reproducible (`docker compose up`
y funciona igual en cualquier sitio), **aislado** (el servicio IA no está expuesto a internet),
**observable** (health checks, logs) y **con secretos fuera del código**. El ejercicio te obliga a
partir el monolito mental en servicios con **el mínimo de superficie pública**.

## Las 6 lecciones (índice)
1. **Qué entendemos por producción** — las propiedades de arriba; "en mi máquina" no cuenta.
2. **Documentar el sistema** — diagrama de servicios, puertos, variables; `docs/deployment-local.md`.
3. **Partir en servicios** — qué es público (backend de negocio) y qué es interno (servicio IA, BBDD).
4. **Contenerización con Docker** — `Dockerfile` por servicio, `docker-compose.yml`, redes y volúmenes.
5. **CI/CD y autenticación entre servicios** — tokens de servicio (`X-Service-Token`), `.env` fuera de git.
6. **Despliegue en clouds** — panorama (dónde iría cada servicio); local es el objetivo de la entrega.

## El ejercicio "Dockerización del proyecto" (qué construir) — deadline lunes 20 sept
Un **`docker-compose.yml`** que levante **4 servicios** con las fronteras correctas:

| Servicio | Rol | Exposición |
|---|---|---|
| `business-backend` | backend de negocio (Rails) | **público**, puerto `3000` |
| `ai-service` | el estimador (FastAPI) | **interno**, **sin `ports:`** — solo alcanzable en la red de compose |
| `postgres` | datos de negocio + checkpointer | interno |
| `vector-db` | pgvector / índice | interno |

- **Requisitos duros:**
  - `ai-service` **NO** publica puertos al host (nadie lo llama desde fuera; solo `business-backend`).
  - Endpoint **`/health`** en el servicio IA que responde **sin llamar al LLM** (liveness barato).
  - **Autenticación servicio-a-servicio** con cabecera **`X-Service-Token`** validada contra
    `AI_SERVICE_TOKEN`; sin token válido → 401.
  - **`.env.example` versionado** (con las claves, sin valores) y **`.env` en `.gitignore`** (nunca al repo).
  - Entregar **`docs/deployment-local.md`**: diagrama de servicios, variables, y el arranque en un comando.

- **Comprobación de aceptación:** `docker compose up` levanta todo; `curl` a `/health` del backend
  público responde; el servicio IA **no** es accesible directamente desde el host; una petición al IA
  **sin** `X-Service-Token` da 401 y **con** token válido pasa.

**Fuera de alcance:** CI/CD real (pipelines), despliegue en cloud, HTTPS/reverse-proxy, secretos
gestionados (Vault/SSM) — se nombran en las lecciones pero la entrega es **local**.

## Conexión con tu Proyecto Final
Esta es **la fase de despliegue** del capstone. El copiloto municipal encaja igual: un frontend/gateway
público y el **servicio IA aislado** (no debe ser llamable desde internet), Postgres + vector-db
internos, `/health`, y **token de servicio** entre gateway y IA. Para un servicio público municipal,
el aislamiento de red y los secretos fuera del código no son opcionales. `docs/deployment-local.md`
es directamente un entregable del proyecto.

## Estado
Material de estudio (no construido). Ejercicio no entregado (deadline pasado, lunes 20 sept). **Es la
capa que cierra el Proyecto Final** — se construye una sola vez, al final, sobre lo de S13/S14.
