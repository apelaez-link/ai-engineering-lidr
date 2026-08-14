"""Reranking con cross-encoder (sesión 10): patrón recall-then-rerank.

La recuperación (vector / híbrida) es de ALTO recall pero ranking GRUESO: trae muchos
candidatos plausibles, pero su orden no es fino porque compara la consulta con cada
documento por separado (bi-encoder: dos vectores independientes y su coseno).

Un CROSS-ENCODER mira la consulta y el documento JUNTOS en una sola pasada del modelo
y emite un score de relevancia mucho más preciso. Es caro (una inferencia por par), así
que NO se puede correr sobre toda la colección: se usa en dos fases —

    recall-then-rerank:
      1) recuperación amplia y barata  -> top-N candidatos (N grande, p.ej. 50)
      2) reordenación fina y cara       -> top-k final (k pequeño, p.ej. 5)

Este wrapper aísla esa fase 2. El scorer real es sentence_transformers.CrossEncoder,
que se carga de forma PEREZOSA (descarga el modelo la primera vez, no al importar) para
que importar el módulo sea barato y los tests no necesiten torch. El scorer se puede
INYECTAR (un callable que mapea pares [consulta, doc] -> scores), y así testeamos la
lógica de reordenación con un doble determinista.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from app.logging_config import get_logger

logger = get_logger(component="reranker")

# Cross-encoder por defecto. ms-marco-MiniLM-L-6-v2: pequeño (~80 MB), entrenado para
# ranking de relevancia consulta-documento en INGLÉS (encaja con nuestro corpus). El
# enunciado usa uno multilingüe porque su dataset está en español; el nuestro es inglés.
DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Firma del scorer: recibe pares [consulta, documento] y devuelve un score por par.
Scorer = Callable[[Sequence[Sequence[str]]], Sequence[float]]


class CrossEncoderReranker:
    """Reordena candidatos por relevancia consulta-documento con un cross-encoder."""

    def __init__(
        self, model_name: str = DEFAULT_RERANK_MODEL, scorer: Scorer | None = None
    ) -> None:
        self._model_name = model_name
        self._scorer = scorer  # si se inyecta, no se carga el modelo real
        self._model: Any = None

    def _get_scorer(self) -> Scorer:
        """Devuelve el scorer inyectado o carga el CrossEncoder real (perezoso)."""
        if self._scorer is not None:
            return self._scorer
        if self._model is None:
            # Import perezoso: sentence_transformers/torch solo se cargan si de verdad
            # se usa el reranker real (no al importar este módulo ni en los tests).
            from sentence_transformers import CrossEncoder

            logger.info("reranker_loading_model", model=self._model_name)
            self._model = CrossEncoder(self._model_name)
        return self._model.predict

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int,
        text_key: str = "content",
    ) -> list[dict[str, Any]]:
        """Reordena `candidates` por score del cross-encoder y devuelve los top_k.

        Cada resultado conserva su payload y añade `rerank_score`. No muta los dicts de
        entrada (copia superficial). Si no hay candidatos, devuelve lista vacía.
        """
        if not candidates:
            return []
        pairs = [[query, c[text_key]] for c in candidates]
        scores = self._get_scorer()(pairs)
        ranked = sorted(
            zip(candidates, scores), key=lambda cs: float(cs[1]), reverse=True
        )
        results: list[dict[str, Any]] = []
        for candidate, score in ranked[:top_k]:
            row = dict(candidate)
            row["rerank_score"] = float(score)
            results.append(row)
        return results
