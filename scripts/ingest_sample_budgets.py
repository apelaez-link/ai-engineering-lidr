"""Ingesta los 15 presupuestos de `data/budgets_sample.json` en la BBDD vectorial.

Reutiliza el endpoint del pipeline (POST /embeddings/ingest, sesión 08): trocea cada
presupuesto, embebe sus componentes y los persiste. Es el paso que deja la base con datos
para que funcionen /search (S8-S10), el pipeline RAG (S11) y las tools del agente (S12).

Uso (con la API arrancada por uvicorn y Postgres levantado):
    uv run python scripts/ingest_sample_budgets.py
    uv run python scripts/ingest_sample_budgets.py --base-url http://localhost:8000

Es idempotente: si un presupuesto ya estaba ingestado, el endpoint responde 409 y aquí
lo contamos como "ya existía" sin romper. Así puedes re-ejecutarlo sin duplicar.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "budgets_sample.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="URL base de la API (por defecto http://localhost:8000).",
    )
    parser.add_argument(
        "--timeout", type=float, default=60.0, help="Timeout por request en segundos."
    )
    args = parser.parse_args()

    budgets = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    print(f"Ingestando {len(budgets)} presupuestos en {args.base_url} …")

    created = duplicated = failed = 0
    with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
        for budget in budgets:
            budget_id = budget["budget_id"]
            payload = {
                "source_path": f"budgets_sample/{budget_id}",
                "document_type": "historical_budget",
                "content": budget,
            }
            resp = client.post("/embeddings/ingest", json=payload)
            if resp.status_code == 200:
                body = resp.json()
                created += 1
                print(
                    f"  ✓ {budget_id}: document_id={body['document_id']} "
                    f"chunks={body['chunks_created']}"
                )
            elif resp.status_code == 409:
                duplicated += 1
                print(f"  = {budget_id}: ya estaba ingestado (409)")
            else:
                failed += 1
                print(f"  ✗ {budget_id}: HTTP {resp.status_code} — {resp.text[:200]}")

    print(
        f"\nHecho. Nuevos: {created} · Ya existían: {duplicated} · Fallidos: {failed}."
    )
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
