"""Tests de la búsqueda híbrida (sesión 10): RRF puro + orquestación mockeada.

El RRF se prueba como función pura (matemática, sin BBDD). La orquestación de
hybrid_search se prueba con las dos consultas del repository mockeadas (AsyncMock), sin
Postgres: comprobamos que fusiona ambos rankings y que un chunk que sale bien en UNA
sola rama puede colarse en el top-k.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.embedding_pipeline.hybrid import hybrid_search, reciprocal_rank_fusion


# ── RRF puro ─────────────────────────────────────────────────────────────────────


def test_rrf_single_list_preserves_order() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"]], k=60)
    assert [key for key, _ in fused] == ["a", "b", "c"]
    # Score decreciente con la posición: 1/(60+1) > 1/(60+2) > 1/(60+3).
    scores = [s for _, s in fused]
    assert scores[0] > scores[1] > scores[2]


def test_rrf_rewards_agreement_across_lists() -> None:
    """Un doc en el top de AMBAS listas gana a uno que solo lidera una."""
    # 'x' es 1º en ambas; 'a' es 1º en una pero no aparece en la otra.
    fused = dict(reciprocal_rank_fusion([["x", "a"], ["x", "b"]], k=60))
    assert fused["x"] > fused["a"]
    assert fused["x"] > fused["b"]


def test_rrf_rescues_item_present_in_one_list() -> None:
    """Un item que solo sale en una lista sigue puntuando (no se pierde)."""
    fused = dict(reciprocal_rank_fusion([["a", "b"], ["c"]], k=60))
    assert set(fused) == {"a", "b", "c"}
    assert fused["c"] == pytest.approx(1.0 / 61)


def test_rrf_k_dampens_positional_gap() -> None:
    """k grande achica la diferencia entre la 1ª y la 2ª posición."""
    small_k = dict(reciprocal_rank_fusion([["a", "b"]], k=1))
    big_k = dict(reciprocal_rank_fusion([["a", "b"]], k=1000))
    assert (small_k["a"] - small_k["b"]) > (big_k["a"] - big_k["b"])


def test_rrf_empty_input() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


# ── Orquestación de hybrid_search (repository mockeado) ────────────────────────────


def _vec_row(cid: int, distance: float) -> dict:
    return {
        "chunk_id": cid,
        "document_id": cid,
        "chunk_type": "budget_component",
        "content": f"vec content {cid}",
        "distance": distance,
        "metadata": {"src": "vec"},
    }


def _lex_row(cid: int, rank: float) -> dict:
    return {
        "chunk_id": cid,
        "document_id": cid,
        "chunk_type": "budget_component",
        "content": f"lex content {cid}",
        "rank": rank,
        "metadata": {"src": "lex"},
    }


def test_hybrid_fuses_both_branches() -> None:
    # Vector: [1, 2, 3]  ·  Léxica: [3, 4, 1]  -> el 1 y el 3 salen en ambas.
    vec = [_vec_row(1, 0.10), _vec_row(2, 0.20), _vec_row(3, 0.30)]
    lex = [_lex_row(3, 0.9), _lex_row(4, 0.5), _lex_row(1, 0.1)]

    with patch(
        "app.embedding_pipeline.hybrid.search_chunks",
        new=AsyncMock(return_value=vec),
    ), patch(
        "app.embedding_pipeline.hybrid.lexical_search_chunks",
        new=AsyncMock(return_value=lex),
    ):
        results = asyncio.run(
            hybrid_search(
                session=object(),
                query_vector=[0.0],
                query_text="q",
                k=4,
                candidate_pool=10,
                rrf_k=60,
            )
        )

    ids = [r["chunk_id"] for r in results]
    scores = {r["chunk_id"]: r["rrf_score"] for r in results}
    # 1 y 3 salen en AMBAS listas -> puntúan por encima de 2 y 4 (cada uno en una sola).
    assert set(ids[:2]) == {1, 3}
    assert set(ids[2:]) == {2, 4}
    assert min(scores[1], scores[3]) > max(scores[2], scores[4])
    # Todos llevan rrf_score y conservan payload.
    assert all("rrf_score" in r for r in results)


def test_hybrid_prefers_vector_payload_on_overlap() -> None:
    """Si un chunk sale en ambas ramas, el payload devuelto es el vectorial (distance)."""
    vec = [_vec_row(1, 0.10)]
    lex = [_lex_row(1, 0.9)]
    with patch(
        "app.embedding_pipeline.hybrid.search_chunks",
        new=AsyncMock(return_value=vec),
    ), patch(
        "app.embedding_pipeline.hybrid.lexical_search_chunks",
        new=AsyncMock(return_value=lex),
    ):
        results = asyncio.run(
            hybrid_search(
                session=object(),
                query_vector=[0.0],
                query_text="q",
                k=5,
                candidate_pool=10,
            )
        )
    assert results[0]["metadata"]["src"] == "vec"
    assert results[0]["distance"] == 0.10
