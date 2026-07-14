"""Sanity check CLI: similitud coseno entre dos textos (sesión 07).

Embebe dos textos con text-embedding-3-small y devuelve su similitud coseno. Es el
mínimo aceptable que demuestra que el pipeline funciona end-to-end y que los
embeddings discriminan entre textos cercanos y lejanos.

Reutiliza OpenAIEmbedder (el mismo del endpoint) y la cosine_similarity de
embedding_pipeline/similarity.py (implementada a mano, sin numpy).

Uso (dos formas, ambas documentadas en el README):
  # Fuera del contenedor (con .env cargado):
  uv run python scripts/compare.py \
      --text-a "OAuth 2.0 authentication backend for fintech" \
      --text-b "JWT-based authorization service for banking app"

  # Dentro del contenedor:
  docker compose exec servicio_ia python scripts/compare.py --text-a "..." --text-b "..."

Necesita OPENAI_API_KEY en el entorno / .env: hace llamadas reales a la API de
embeddings (coste despreciable: dos textos cortos son fracciones de céntimo).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite ejecutar el script directamente (python scripts/compare.py) añadiendo la
# raíz del repo al path, para que "import app...." funcione sin instalar el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.embedding_pipeline.embedder import OpenAIEmbedder  # noqa: E402
from app.embedding_pipeline.similarity import cosine_similarity  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="compare.py",
        description="Cosine similarity between two texts via text-embedding-3-small.",
    )
    parser.add_argument("--text-a", required=True, help="First text to embed.")
    parser.add_argument("--text-b", required=True, help="Second text to embed.")
    args = parser.parse_args(argv)

    embedder = OpenAIEmbedder()
    vec_a = embedder.embed_one(args.text_a)
    vec_b = embedder.embed_one(args.text_b)
    similarity = cosine_similarity(vec_a, vec_b)

    print(f"Text A: {args.text_a}")
    print(f"Text B: {args.text_b}")
    print(f"Cosine similarity: {similarity:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
