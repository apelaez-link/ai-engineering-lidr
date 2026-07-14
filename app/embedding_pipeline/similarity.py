"""Métricas de similitud entre vectores, con la biblioteca estándar (sesión 07).

De la lección "Embeddings: del texto a la geometría semántica". Tres funciones, cero
dependencias externas (nada de numpy ni scikit-learn, como pide el enunciado). Viven
en su propio módulo para poder testearlas sin API y reutilizarlas desde compare.py.

Para text-embedding-3-small los vectores vienen normalizados (norma ≈ 1), así que
coseno y producto escalar dan el mismo resultado; incluimos las tres por didáctica.
"""

from __future__ import annotations

import math


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Similitud coseno: (A·B) / (||A||·||B||). Rango [-1, 1]; en texto, ~[0, 1].

    Insensible a la magnitud (solo mide dirección): un documento largo no parece menos
    parecido a una consulta corta por su tamaño.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError("Vectors must have the same dimensionality")

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        raise ValueError("Cannot compute similarity for zero-norm vectors")

    return dot / (norm_a * norm_b)


def dot_product(vec_a: list[float], vec_b: list[float]) -> float:
    """Producto escalar. Para vectores normalizados equivale al coseno y es más barato."""
    if len(vec_a) != len(vec_b):
        raise ValueError("Vectors must have the same dimensionality")
    return sum(a * b for a, b in zip(vec_a, vec_b))


def euclidean_distance(vec_a: list[float], vec_b: list[float]) -> float:
    """Distancia euclídea. 0 = idénticos; a más valor, más lejanos."""
    if len(vec_a) != len(vec_b):
        raise ValueError("Vectors must have the same dimensionality")
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(vec_a, vec_b)))
