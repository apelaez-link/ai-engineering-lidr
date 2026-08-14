"""Embedder sobre la API de OpenAI (sesión 07).

Genera embeddings con ``text-embedding-3-small`` (1536 dimensiones por defecto).
Decisiones de la lección "Selección de modelos": modelo bloqueado a
text-embedding-3-small (barato, multilingüe decente, API ya configurada desde la
sesión 01), dimensión por defecto (Matryoshka se deja como palanca del directo).

Usamos el SDK de OpenAI DIRECTAMENTE (no litellm) porque el ejercicio lo pide así y
porque necesitamos su excepción ``RateLimitError`` para el reintento. El resto del
proyecto sigue usando litellm para el chat; los embeddings son un camino aparte.

Puntos clave del enunciado implementados aquí:
  - embed_many llama a la API en BATCHES (100 por defecto), no una llamada por chunk.
  - Reintento exponencial simple ante RateLimitError (3 intentos: 1s, 2s, 4s).
  - Logging structlog por batch: nº de chunks, nº de tokens, latencia.
  - Coste estimado con una CONSTANTE de módulo claramente etiquetada.
"""

from __future__ import annotations

import time

from openai import OpenAI, RateLimitError

from app.config import get_settings
from app.logging_config import get_logger

from .schemas import Chunk, EmbeddedChunk

logger = get_logger(component="embedder")

# Modelo de embeddings del proyecto (lección "Selección de modelos").
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# Precio de text-embedding-3-small en el momento de escribir (cambia con el tiempo):
# $0.02 por millón de tokens de ENTRADA. Constante etiquetada, fácil de actualizar.
COST_PER_1M_INPUT_TOKENS_USD = 0.02

# Tamaño de batch recomendado por el enunciado: 100 chunks por llamada.
DEFAULT_BATCH_SIZE = 100

# Reintento ante rate limit: 3 intentos con esperas 1s, 2s, 4s (backoff exponencial).
RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)


def estimate_cost_usd(total_tokens: int) -> float:
    """Coste estimado en USD de embeber ``total_tokens`` tokens de entrada."""
    return total_tokens / 1_000_000 * COST_PER_1M_INPUT_TOKENS_USD


class OpenAIEmbedder:
    """Genera embeddings de textos y de chunks con la API de OpenAI.

    El cliente se puede inyectar (útil para tests: se pasa un doble que no toca la red).
    Si no se inyecta, se construye con la OPENAI_API_KEY del .env.
    """

    def __init__(
        self,
        client: OpenAI | None = None,
        model: str = EMBEDDING_MODEL,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self._model = model
        self._batch_size = batch_size
        if client is not None:
            self._client = client
        else:
            settings = get_settings()
            if not settings.openai_api_key:
                raise ValueError(
                    "OPENAI_API_KEY no está configurada. Los embeddings usan la API de "
                    "OpenAI directamente; rellena la clave en el .env."
                )
            self._client = OpenAI(api_key=settings.openai_api_key)

    def embed_one(self, text: str) -> list[float]:
        """Embebe un único texto y devuelve su vector. Lo usa scripts/compare.py."""
        return self._embed_texts([text])[0]

    def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        """Embebe una lista de chunks en batches y devuelve EmbeddedChunk (con vector).

        Preserva el orden: la API devuelve los embeddings en el mismo orden que los
        textos de entrada, así que emparejamos por índice dentro de cada batch.
        """
        embedded: list[EmbeddedChunk] = []
        for start in range(0, len(chunks), self._batch_size):
            batch = chunks[start : start + self._batch_size]
            vectors = self._embed_texts([c.text for c in batch])
            for chunk, vector in zip(batch, vectors):
                embedded.append(
                    EmbeddedChunk(**chunk.model_dump(), embedding=vector)
                )
        return embedded

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Una llamada a la API (con reintentos) para un batch de textos.

        Reintenta SOLO ante RateLimitError (transitorio) con backoff 1s/2s/4s. Cualquier
        otro error se propaga hacia arriba (lo traduce el router a 500).
        """
        attempt = 0
        while True:
            started = time.perf_counter()
            try:
                response = self._client.embeddings.create(
                    model=self._model, input=texts
                )
            except RateLimitError:
                if attempt >= len(RETRY_BACKOFF_SECONDS):
                    logger.error("embeddings_rate_limited_giving_up", attempts=attempt)
                    raise
                wait = RETRY_BACKOFF_SECONDS[attempt]
                attempt += 1
                logger.warning(
                    "embeddings_rate_limited_retrying", attempt=attempt, wait_s=wait
                )
                time.sleep(wait)
                continue

            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            total_tokens = getattr(response.usage, "total_tokens", 0)
            logger.info(
                "embeddings_batch_completed",
                chunks=len(texts),
                tokens=total_tokens,
                latency_ms=latency_ms,
                model=self._model,
            )
            # response.data viene ordenado por el índice del input.
            return [item.embedding for item in response.data]
