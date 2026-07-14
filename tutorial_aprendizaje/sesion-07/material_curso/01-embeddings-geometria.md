# 01 — Embeddings: del texto a la geometría semántica

> Material del curso LIDR · AI Engineering · Sesión 7 (Antonio Pérez). (≈21 min)

Establece la base teórica mínima: qué es un embedding, por qué funciona y cómo se comparan dos
textos vía sus vectores. Es el primer ladrillo de la búsqueda semántica.

## Qué es un embedding

Una función que toma un texto y devuelve un **vector de dimensión fija**. Para
`text-embedding-3-small` son **1536** floats; para `all-MiniLM-L6-v2`, 384; para
`text-embedding-3-large`, 3072. Lo importante no es el número, es la **propiedad**: textos
semánticamente similares producen vectores cercanos en R^n.

Las dimensiones individuales **no tienen interpretación humana** (la dimensión 142 no es
"fintech-ness"): emergen de un proceso de optimización ciego. Lo que tiene significado son las
**direcciones y distancias relativas** entre vectores.

## Cómo aprenden la geometría

Con **aprendizaje contrastivo**: durante el entrenamiento se muestran millones de tripletes
(ancla, positivo, negativo). La pérdida castiga que el ancla quede más cerca del negativo que del
positivo. Tras millones de iteraciones, emerge un espacio donde la cercanía ≈ similitud semántica.

**Qué es "el positivo" depende de qué se entrene**: parafraseos, traducciones, pares
pregunta-respuesta, fragmentos de código… La naturaleza de los positivos determina qué entiende el
modelo por "similar". Consecuencia práctica: un modelo entrenado en inglés general sobre jerga
financiera en español no discrimina igual que en su dominio.

> El clásico `rey - hombre + mujer ≈ reina` era de Word2Vec (hace una década); con embeddings
> modernos de oraciones esos juegos aritméticos casi nunca salen limpios. Lo único que necesitas:
> **vectores cercanos = textos cercanos**.

## Métricas de similitud (las tres que necesitas)

- **Coseno** — `(A·B) / (||A||·||B||)`. Rango [-1, 1]; en texto ~[0, 1]. **Insensible a la
  magnitud** (solo dirección): un documento largo no parece menos parecido a una consulta corta por
  su tamaño. Es la opción por defecto en texto.
- **Producto escalar (dot)** — el numerador del coseno. Sin acotar, sensible a magnitud, más barato.
  **Para vectores normalizados (norma 1), dot y coseno dan el mismo resultado** → muchas BBDD
  vectoriales usan dot en producción.
- **Distancia euclídea** — recta entre los puntos. 0 = idénticos. Para vectores normalizados ordena
  igual que el coseno (`euclidean² = 2 − 2·cosine`).

**Regla para elegir métrica: usa la que recomienda la model card del modelo.** No hay mejor métrica
universal; es una propiedad del modelo, no una decisión arquitectónica. `text-embedding-3-small`
entrega vectores **normalizados**, así que coseno y dot son intercambiables.

Las tres, en Python estándar sin numpy (esto es lo que va en nuestro `similarity.py` y `compare.py`):

```python
import math

def cosine_similarity(a, b):
    if len(a) != len(b): raise ValueError("same dim")
    dot = sum(x*y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x*x for x in a)), math.sqrt(sum(y*y for y in b))
    if na == 0 or nb == 0: raise ValueError("zero-norm")
    return dot / (na * nb)
```

## Lo que un embedding NO resuelve (honestidades)

- **No entiende números, fechas ni IDs.** "presupuestos de 2024" → filtra por metadata `year`, no
  por similitud vectorial. Los números son tokens cualesquiera; el modelo no hace aritmética.
- **Débil en coincidencias exactas de palabras raras** (nombres propios) → BM25 lo hace mejor. De
  ahí la *hybrid search* (sesión 10).
- **Maldición de la dimensionalidad**: en muchas dimensiones las distancias entre pares aleatorios se
  concentran. Ver similitudes de **0.2–0.5 entre textos no relacionados es normal**: el "cero" no
  aparece. **Calibra umbrales sobre tu propio dataset**, no asumas que "> 0.7 = muy similar".
- **El modelo importa más que la métrica.** Cambiar de coseno a dot (con modelo normalizado) no
  cambia nada; cambiar English-only ↔ multilingüe sí cambia todo.

> 💡 Esto se ve en nuestro [SANITY_CHECK.md](../../../app/embedding_pipeline/SANITY_CHECK.md): la
> pareja cercana salió 0.596 (¡justo bajo el 0.6 orientativo!) y una pareja genérica 0.54 — los
> umbrales absolutos engañan; lo que importa es que cercano ≫ no-relacionado (0.19).
