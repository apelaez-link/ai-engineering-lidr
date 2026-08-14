"""Script de validación del endpoint de búsqueda semántica (sesión 08).

Reemplaza el compare.py de la sesión 07 (que medía similitud entre pares de textos
sueltos) por cinco consultas representativas contra POST /search, formateando el
top-k de cada una. Las cinco ejercitan el corpus desde ángulos distintos.

Uso:
  # con el servidor levantado (uvicorn) y Postgres migrado + corpus ingestado:
  uv run python query_examples.py
  # (equivalente containerizado del enunciado: docker compose run --rm ai_service python query_examples.py)

Lee la URL base de API_BASE_URL (por defecto http://localhost:8000). Guarda su salida
en output_examples.txt con:  uv run python query_examples.py > output_examples.txt
"""

from __future__ import annotations

import os
import sys

import httpx

# Cinco consultas que ejercitan el dataset desde ángulos distintos (enunciado):
QUERIES: list[tuple[str, str]] = [
    (
        "Componente directo conocido (sanity check)",
        "REST API development with JWT authentication for financial sector",
    ),
    (
        "Reformulación semántica (mismo concepto, otro vocabulario)",
        "secure backend service with token-based access control for banking applications",
    ),
    (
        "Dominio distinto (no debería estar en el corpus)",
        "mobile application for restaurant reservations",
    ),
    (
        "Consulta ambigua (genérica, muchos matches parciales)",
        "integration with external system",
    ),
    (
        "Consulta muy específica (vocabulario técnico preciso)",
        "migration from monolith to microservices architecture using Kubernetes",
    ),
]

K = 5
CONTENT_PREVIEW_CHARS = 120


def main() -> int:
    base_url = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
    client = httpx.Client(base_url=base_url, timeout=30.0)

    for label, query in QUERIES:
        print("=" * 100)
        print(f"QUERY [{label}]")
        print(f"  {query!r}")
        try:
            resp = client.post("/search", json={"query": query, "k": K})
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {exc}", file=sys.stderr)
            print(f"  (¿está el servidor en {base_url} y el corpus ingestado?)")
            return 1

        body = resp.json()
        print(f"  search_time_ms={body['search_time_ms']}  results={len(body['results'])}")
        print(f"  {'#':>2}  {'dist':>7}  {'chunk_id':>8}  {'chunk_type':<18}  content")
        for i, r in enumerate(body["results"], start=1):
            preview = " ".join(r["content"].split())[:CONTENT_PREVIEW_CHARS]
            print(
                f"  {i:>2}  {r['distance']:>7.4f}  {r['chunk_id']:>8}  "
                f"{r['chunk_type']:<18}  {preview}"
            )
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
