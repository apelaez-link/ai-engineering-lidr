"""Tests del cacheo semántico (TEMA 3, sesión 04).

Mockeamos litellm.embedding para devolver vectores CONTROLADOS, de forma que
podamos forzar similitudes coseno concretas sin llamadas reales:

  - Misma intención (vector casi idéntico) en el MISMO bucket  -> HIT.
  - Mismo vector pero en un bucket DISTINTO                     -> MISS (aislamiento).
  - Vector lejano (casi ortogonal) en el mismo bucket          -> MISS (bajo umbral).

Las descripciones se mapean a vectores con un diccionario en el mock, así cada
test controla exactamente qué vector recibe cada texto.
"""

from unittest.mock import patch

import numpy as np

from app.cache.semantic import SemanticCache, cosine_similarity, make_bucket

# Vectores de prueba en 3D (suficiente para razonar sobre coseno).
# v_a y v_a2 apuntan casi en la misma dirección -> similitud ~1.0.
V_A = [1.0, 0.0, 0.0]
V_A2 = [0.99, 0.01, 0.0]
# v_far es casi ortogonal a v_a -> similitud ~0.0.
V_FAR = [0.0, 1.0, 0.0]

# Mapa texto -> vector que usará el mock de litellm.embedding.
_EMBEDDINGS = {
    "intent original": V_A,
    "intent reformulada": V_A2,
    "intent distinta": V_FAR,
}


def _fake_embedding(*args, **kwargs):
    """Simula litellm.embedding devolviendo el vector mapeado para el input dado."""
    text = kwargs["input"][0]
    vector = _EMBEDDINGS[text]
    return {"data": [{"embedding": vector}]}


BUCKET_A = make_bucket(
    project_type="web_saas", detail_level="medium", output_format="phases_table", prompt_version="v1"
)
BUCKET_B = make_bucket(
    project_type="mobile_app", detail_level="summary", output_format="narrative", prompt_version="v2"
)


def test_cosine_similarity_basic() -> None:
    """Sanity check de la similitud coseno (vectores idénticos vs ortogonales)."""
    assert cosine_similarity(np.array(V_A), np.array(V_A)) == 1.0
    assert abs(cosine_similarity(np.array(V_A), np.array(V_FAR))) < 1e-9


@patch("litellm.embedding", side_effect=_fake_embedding)
def test_same_intent_same_bucket_is_hit(mock_embedding) -> None:
    """Una reformulación (vector casi idéntico) en el mismo bucket = HIT."""
    cache = SemanticCache(threshold=0.92)
    cache.write("intent original", BUCKET_A, '{"answer": 1}')

    hit = cache.lookup("intent reformulada", BUCKET_A)
    assert hit == '{"answer": 1}'


@patch("litellm.embedding", side_effect=_fake_embedding)
def test_same_vector_different_bucket_is_miss(mock_embedding) -> None:
    """El mismo vector en un bucket distinto NO debe matchear (aislamiento de buckets)."""
    cache = SemanticCache(threshold=0.92)
    cache.write("intent original", BUCKET_A, '{"answer": 1}')

    # Buscamos la MISMA intención pero en otro bucket -> miss (bucket vacío).
    miss = cache.lookup("intent original", BUCKET_B)
    assert miss is None


@patch("litellm.embedding", side_effect=_fake_embedding)
def test_far_vector_same_bucket_is_miss(mock_embedding) -> None:
    """Un vector lejano (intención distinta) en el mismo bucket = MISS (bajo umbral)."""
    cache = SemanticCache(threshold=0.92)
    cache.write("intent original", BUCKET_A, '{"answer": 1}')

    miss = cache.lookup("intent distinta", BUCKET_A)
    assert miss is None


@patch("litellm.embedding", side_effect=_fake_embedding)
def test_empty_bucket_is_miss(mock_embedding) -> None:
    """Lookup en una caché vacía devuelve miss sin reventar."""
    cache = SemanticCache(threshold=0.92)
    assert cache.lookup("intent original", BUCKET_A) is None
