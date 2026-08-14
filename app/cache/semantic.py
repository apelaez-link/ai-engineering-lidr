"""Cacheo SEMÁNTICO de respuestas (sesión 04, lección "Cacheo semántico").

El cacheo exact-match (app/cache/llm_cache.py) solo acierta si la entrada es
BYTE A BYTE idéntica. Pero "app para reservar mesas en restaurantes" y "plataforma
de reservas para restaurantes" son la MISMA intención escrita distinto: el
exact-match falla y pagamos otra generación. El cacheo semántico resuelve esto:

  1. Embebe la descripción a un vector (litellm.embedding).
  2. Busca la entrada más PARECIDA por similitud coseno.
  3. Si la similitud >= umbral, devuelve esa respuesta (HIT).

Dos decisiones clave de la lección:

  - BUCKETS. No basta con que la descripción se parezca: la respuesta depende
    también de project_type, detail_level, output_format y la versión del prompt.
    Comparar la descripción de un "summary narrative v1" con la de un "detailed
    phases_table v2" no tiene sentido. Por eso particionamos el store en buckets
    deterministas y SOLO buscamos similitud dentro del mismo bucket.

  - SIN INFRA POR DEFECTO. El store es un dict en memoria, igual de "enchufable"
    que el exact-match. En producción se sustituiría por redisvl/Redis (un índice
    vectorial con búsqueda KNN), pero el contrato de SemanticCache no cambiaría.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(component="semantic_cache")


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Similitud coseno entre dos vectores: 1.0 = idénticos, 0.0 = ortogonales.

    Defensiva ante vectores nulos (norma 0): devolvemos 0.0 para no dividir por cero.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def make_bucket(
    *, project_type: str, detail_level: str, output_format: str, prompt_version: str
) -> str:
    """Clave determinista de partición: respuestas solo comparables en el mismo bucket.

    Componemos los parámetros que cambian la FORMA/INTENCIÓN de la respuesta. La
    descripción NO entra aquí (esa es la parte "borrosa" que comparamos por
    similitud); el bucket es la parte "exacta".
    """
    return f"{project_type}:{detail_level}:{output_format}:{prompt_version}"


@dataclass
class _Entry:
    """Una entrada del store semántico: vector + respuesta serializada."""

    embedding: np.ndarray
    response_json: str


class SemanticCache:
    """Caché semántica en memoria con búsqueda por similitud coseno dentro de bucket.

    Almacena entradas agrupadas por bucket. En `lookup` embebe la descripción y
    devuelve la respuesta de la entrada más parecida del MISMO bucket si supera el
    umbral; si no, miss. En `write` guarda la nueva entrada en su bucket.

    El embedding se calcula con `litellm.embedding` (modelo configurable). En los
    tests se mockea para devolver vectores controlados, sin llamadas reales.
    """

    def __init__(
        self,
        *,
        embedding_model: str | None = None,
        threshold: float | None = None,
    ) -> None:
        settings = get_settings()
        self._embedding_model = embedding_model or settings.semantic_cache_embedding_model
        self._threshold = threshold if threshold is not None else settings.semantic_cache_threshold
        # bucket -> lista de entradas. En producción sería un índice vectorial (redisvl).
        self._store: dict[str, list[_Entry]] = {}

    # ── Embedding ────────────────────────────────────────────────────────────
    def _embed(self, text: str) -> np.ndarray:
        """Convierte un texto en su vector de embedding usando litellm.

        Import perezoso de litellm para no acoplar el módulo al proveedor en import
        time y para que el mock de los tests sea sencillo.
        """
        import litellm

        response = litellm.embedding(model=self._embedding_model, input=[text])
        vector = response["data"][0]["embedding"]
        return np.asarray(vector, dtype=float)

    # ── Lookup ────────────────────────────────────────────────────────────────
    def lookup(self, description: str, bucket: str) -> str | None:
        """Busca una respuesta cacheada semánticamente equivalente.

        Args:
            description: Descripción del proyecto (la parte "borrosa").
            bucket: Clave determinista de partición (make_bucket).

        Returns:
            El response_json de la mejor coincidencia si su similitud >= umbral,
            o None si no hay candidatos en el bucket o ninguno supera el umbral.
        """
        entries = self._store.get(bucket)
        if not entries:
            logger.info("semantic_cache_miss", reason="empty_bucket", bucket=bucket)
            return None

        query = self._embed(description)
        best_sim = -1.0
        best_entry: _Entry | None = None
        for entry in entries:
            sim = cosine_similarity(query, entry.embedding)
            if sim > best_sim:
                best_sim = sim
                best_entry = entry

        if best_entry is not None and best_sim >= self._threshold:
            logger.info(
                "semantic_cache_hit", bucket=bucket, similarity=round(best_sim, 4)
            )
            return best_entry.response_json

        logger.info(
            "semantic_cache_miss",
            reason="below_threshold",
            bucket=bucket,
            best_similarity=round(best_sim, 4),
        )
        return None

    # ── Write ───────────────────────────────────────────────────────────────
    def write(self, description: str, bucket: str, response_json: str) -> None:
        """Guarda una nueva entrada (embedding + respuesta) en su bucket.

        Se llama SOLO después de validar la respuesta (ver orden del pipeline en
        el router): nunca cacheamos una salida que no haya pasado los guardrails.
        """
        embedding = self._embed(description)
        self._store.setdefault(bucket, []).append(
            _Entry(embedding=embedding, response_json=response_json)
        )
        logger.info("semantic_cache_write", bucket=bucket, size=len(self._store[bucket]))

    def clear(self) -> None:
        """Vacía el store (usado en tests entre casos)."""
        self._store.clear()


@lru_cache
def get_semantic_cache() -> SemanticCache:
    """Devuelve una única instancia de la caché semántica para todo el proceso.

    Igual que get_cache (exact-match): @lru_cache para reutilizar el store en
    memoria entre peticiones. En tests se llama a get_semantic_cache.cache_clear().
    """
    return SemanticCache()
