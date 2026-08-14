"""Tests de las métricas de similitud (sesión 07). Sin API: matemática pura."""

import math

import pytest

from app.embedding_pipeline.similarity import (
    cosine_similarity,
    dot_product,
    euclidean_distance,
)


def test_cosine_identical_vectors_is_one() -> None:
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors_is_zero() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_ignores_magnitude() -> None:
    """El coseno solo mira dirección: un vector y su doble dan 1.0."""
    assert cosine_similarity([1.0, 1.0], [2.0, 2.0]) == pytest.approx(1.0)


def test_cosine_opposite_vectors_is_minus_one() -> None:
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_dot_product_matches_cosine_for_normalized_vectors() -> None:
    """Para vectores normalizados (norma 1), producto escalar == coseno."""
    inv = 1 / math.sqrt(2)
    a = [inv, inv]
    b = [1.0, 0.0]
    assert dot_product(a, b) == pytest.approx(cosine_similarity(a, b))


def test_euclidean_distance_basic() -> None:
    assert euclidean_distance([0.0, 0.0], [3.0, 4.0]) == pytest.approx(5.0)


def test_dimension_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])


def test_zero_norm_raises() -> None:
    with pytest.raises(ValueError):
        cosine_similarity([0.0, 0.0], [1.0, 2.0])
