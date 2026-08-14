"""Tests del CrossEncoderReranker (sesión 10).

Inyectamos un SCORER falso (un callable determinista) para probar la lógica de
reordenación SIN cargar torch ni el modelo real. Comprobamos: que reordena por score
descendente, que trunca a top_k, que conserva el payload y añade rerank_score, y que
el import perezoso del modelo no se dispara cuando hay scorer inyectado.
"""

from app.embedding_pipeline.reranker import CrossEncoderReranker


def _candidates() -> list[dict]:
    return [
        {"chunk_id": 1, "content": "irrelevant filler", "metadata": {"x": 1}},
        {"chunk_id": 2, "content": "exact match of the query terms", "metadata": {"x": 2}},
        {"chunk_id": 3, "content": "somewhat related", "metadata": {"x": 3}},
    ]


def test_rerank_orders_by_score_desc_and_truncates() -> None:
    # Scorer determinista: puntúa por longitud del documento (más largo = más score).
    scorer = lambda pairs: [float(len(doc)) for _q, doc in pairs]
    reranker = CrossEncoderReranker(scorer=scorer)

    out = reranker.rerank("the query terms", _candidates(), top_k=2)

    assert len(out) == 2  # truncado a top_k
    # "exact match of the query terms" (30) > "irrelevant filler" (17) > "somewhat related" (16)
    assert [r["chunk_id"] for r in out] == [2, 1]
    assert out[0]["rerank_score"] == float(len("exact match of the query terms"))


def test_rerank_preserves_payload_and_does_not_mutate_input() -> None:
    scorer = lambda pairs: [1.0 for _ in pairs]
    reranker = CrossEncoderReranker(scorer=scorer)
    candidates = _candidates()

    out = reranker.rerank("q", candidates, top_k=3)

    assert out[0]["metadata"] == {"x": 1}  # payload intacto
    assert "rerank_score" not in candidates[0]  # no muta la entrada


def test_rerank_empty_returns_empty_without_calling_scorer() -> None:
    calls = []

    def scorer(pairs):
        calls.append(pairs)
        return [0.0 for _ in pairs]

    reranker = CrossEncoderReranker(scorer=scorer)
    assert reranker.rerank("q", [], top_k=5) == []
    assert calls == []  # ni siquiera se llama al scorer si no hay candidatos


def test_rerank_builds_query_document_pairs() -> None:
    seen = {}

    def scorer(pairs):
        seen["pairs"] = list(pairs)
        return [0.0 for _ in pairs]

    reranker = CrossEncoderReranker(scorer=scorer)
    reranker.rerank("my query", _candidates(), top_k=1)

    # El cross-encoder recibe pares [consulta, contenido_del_chunk].
    assert seen["pairs"][0] == ["my query", "irrelevant filler"]
    assert all(pair[0] == "my query" for pair in seen["pairs"])
