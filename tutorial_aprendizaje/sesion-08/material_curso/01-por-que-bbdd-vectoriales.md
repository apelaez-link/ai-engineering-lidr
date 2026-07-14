# 01 — Por qué existen las BBDD vectoriales y cuándo las necesitas

> Material del curso LIDR · AI Engineering · Sesión 8 (Antonio Pérez). (≈31 min)

Los vectores de la sesión 7 viven en la memoria del proceso: si reinicias, se pierden; reembeder
todo cuesta tiempo y dinero. Esta lección explica **por qué existe una categoría entera de software**
para esto y **cuándo** añadirla al stack se justifica (y cuándo es over-engineering).

## El problema que ningún sistema anterior resuelve

Una BBDD relacional está optimizada para "¿existe el registro id=42?" con índices B-tree (valores
ordenables). "¿Qué presupuestos son semánticamente parecidos a este brief?" se resuelve comparando
vectores de 1536 dimensiones y devolviendo los k más cercanos — **no hay B-tree para "cercanía en
1536 dimensiones"**.

Puedes hacerlo a mano (`ORDER BY cosine_distance LIMIT k`), pero eso obliga a calcular la distancia
con **cada** vector: búsqueda **exacta (KNN)**, coste lineal. 100 vectores, invisible; 100.000,
duele; millones, inviable para algo interactivo.

La salida no es calcular cosenos más rápido: es **cambiar la pregunta**. De "los k más cercanos
garantizados" a "los k que casi con certeza están entre los más cercanos" → **ANN (approximate
nearest neighbors)**. Estructuras especializadas (grafos navegables, particiones, cuantizaciones)
evitan tocar la mayoría de vectores y bajan de lineal a **logarítmico**. El precio: recall <100% (p.ej.
98%, indistinguible del 100% para un RAG que devuelve 5 chunks) y un coste de construir la estructura.
**Una BBDD vectorial = índices ANN sobre almacenamiento persistente, expuestos por SQL o API.**

## Cuatro propiedades que un array de Python no da

1. **Persistencia** — un proceso que muere se lleva los vectores; reembeder cuesta dinero real (cada
   llamada a la API se paga). Primera línea que cruzas al dejar de ser prototipo.
2. **Concurrencia** — con dos réplicas, cada una tiene su estado en memoria y divergen (ingesta en A,
   búsqueda en B no la encuentra). La solución es delegar coherencia a un sistema diseñado para ello.
3. **Consultas combinadas con datos relacionales** — casi nunca quieres "los 5 más cercanos" a secas,
   sino "…del sector fintech, de los últimos 2 años, con monto <100k". Esos filtros viven en columnas.
4. **Operaciones transaccionales (ACID)** — ingestar = crear 1 fila en `documents` + N en `chunks`; si
   el embedder falla en el chunk 5, quieres revertir, no quedarte a medias.

## Cuándo añadirla (y cuándo no)

- **< ~10.000 vectores, estáticos:** un array de numpy al arrancar basta. KNN exacto en ms. Añadir
  una BBDD vectorial aquí es **over-engineering** (la mayoría de tutoriales empujan a montar pgvector
  desde el día 1 sin justificarlo).
- **~10.000 – ~50M vectores:** la BBDD vectorial es la respuesta. Rango de la mayoría de productos
  B2B con IA, **incluido el proyecto**. La pregunta ya no es "¿la necesito?" sino "¿cuál?".
- **> 100M vectores:** sharding, replicación multi-región, índices que no caben en RAM (DiskANN).
  Fuera del foco del programa; casi nadie arranca aquí.
- **Cuarto caso — no la necesitas:** si buscas **matches exactos** (nombres de producto, IDs), la
  full-text de Postgres (`tsvector`) o un índice trigram lo hacen mejor y más simple. La búsqueda
  semántica vale cuando **los términos varían pero el significado no**.

El proyecto cae en el rango medio, y los briefs de cliente rara vez usan las palabras exactas de los
presupuestos → la búsqueda semántica es la primitiva correcta, y necesitamos las cuatro propiedades.

## KNN exacto vs ANN: lo que cambia en tu cabeza

Los sistemas que conocías son deterministas (id=42 → siempre el mismo registro). Los índices ANN
devuelven "los k que el índice **cree** más cercanos, con alta probabilidad". Reindexar con otros
parámetros puede cambiar ligeramente los resultados; subir `ef_search` sube recall y latencia.

Dos implicaciones: **(1)** el recall del índice **se mide** (se compara contra la búsqueda exacta
sobre queries representativas), no se asume — mecánica nueva del directo. **(2)** el debugging cambia:
si un resultado extraña, antes de culpar al modelo, verifica que el índice **no se esté ignorando en
silencio** — el antipatrón clásico (operador `<=>` de la query vs índice construido con
`vector_l2_ops`) hace que Postgres caiga a seq scan sin avisar, con latencia 600× peor.
