"""Búsqueda híbrida por fusión de rankings (sesión 10).

Combina las DOS recuperaciones que ya tenemos en repository.py:

    semántica (vector, cosine)  ─┐
                                 ├─ Reciprocal Rank Fusion (RRF) ─→ ranking único
    léxica (full-text, ts_rank) ─┘

¿Por qué RRF y no sumar/normalizar los scores? Porque la distancia coseno (0..2, menor
mejor) y el ts_rank_cd (0..N, mayor mejor) viven en escalas DISTINTAS e incomparables.
RRF tira los scores a la basura y se queda solo con la POSICIÓN en cada lista: un
documento que sale alto en cualquiera de las dos búsquedas puntúa bien. Es robusto,
no necesita calibración y es el método que usa la lección de búsqueda híbrida.

    RRF(doc) = Σ_listas  1 / (k + rank_en_esa_lista)      (rank es 1-based)

La constante k (60 por convención, de Cormack et al. 2009) amortigua el peso de las
primeras posiciones: sin ella, el rank 1 dominaría todo. Con k grande, las diferencias
entre posiciones se suavizan.

La función `reciprocal_rank_fusion` es PURA (sin BBDD): se testea con listas a mano.
`hybrid_search` orquesta las dos consultas reales y las fusiona.
"""

from __future__ import annotations

from typing import Any, Hashable

from sqlalchemy.ext.asyncio import AsyncSession

from .models_db import FULLTEXT_CONFIG
from .repository import lexical_search_chunks, search_chunks

# Constante RRF estándar. Configurable desde app.config (rrf_k) y desde la medición.
DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    rankings: list[list[Hashable]], k: int = DEFAULT_RRF_K
) -> list[tuple[Hashable, float]]:
    """Fusiona varias listas rankeadas en una sola por Reciprocal Rank Fusion.

    Args:
        rankings: lista de listas; cada sublista son claves (p.ej. chunk_id) EN ORDEN
            de relevancia (la primera es el rank 1). No hace falta que tengan la misma
            longitud ni los mismos elementos.
        k: constante de amortiguación (60 por defecto).

    Returns:
        Lista de (clave, score_rrf) ordenada de mayor a menor score. El orden entre
        empates es estable respecto a la primera aparición (Python sort es estable y
        recorremos las listas en orden).
    """
    scores: dict[Hashable, float] = {}
    for ranking in rankings:
        for position, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + position)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


async def hybrid_search(
    session: AsyncSession,
    query_vector: list[float],
    query_text: str,
    k: int,
    candidate_pool: int,
    rrf_k: int = DEFAULT_RRF_K,
    fulltext_config: str = FULLTEXT_CONFIG,
) -> list[dict[str, Any]]:
    """Recupera por vector y por full-text, fusiona con RRF y devuelve los k mejores.

    `candidate_pool` es cuántos candidatos pide a CADA rama antes de fusionar (p.ej. 50).
    Debe ser >= k: cuanto más ancho, más oportunidades tiene la fusión de rescatar un
    documento que una sola rama dejaría fuera del top-k. La query semántica y la léxica
    usan el MISMO texto de consulta (la léxica lo tokeniza; la semántica ya viene
    embebida en query_vector, generado por el llamante con el mismo modelo de la ingesta).

    Cada resultado lleva `rrf_score` (el score de fusión) y conserva el payload del
    chunk (content, metadata, y distance/rank si esa rama lo aportó).
    """
    vec_rows = await search_chunks(session, query_vector, candidate_pool)
    lex_rows = await lexical_search_chunks(
        session, query_text, candidate_pool, fulltext_config
    )

    fused = reciprocal_rank_fusion(
        [[r["chunk_id"] for r in vec_rows], [r["chunk_id"] for r in lex_rows]], rrf_k
    )

    # Índice de payloads por chunk_id (unión de ambas ramas). Damos preferencia al
    # payload vectorial (trae `distance`); si un chunk solo salió en la léxica, usamos
    # el suyo (trae `rank`).
    by_id: dict[int, dict[str, Any]] = {r["chunk_id"]: r for r in lex_rows}
    by_id.update({r["chunk_id"]: r for r in vec_rows})

    results: list[dict[str, Any]] = []
    for chunk_id, rrf_score in fused[:k]:
        row = dict(by_id[chunk_id])
        row["rrf_score"] = rrf_score
        results.append(row)
    return results
