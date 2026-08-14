# Lección 6 — Filtrado contextual y temporal (18 min)

> Notas fieles (Antonio Pérez). **Fuera del alcance del ejercicio de la S10.** Resumen didáctico.

## El punto ciego de la similitud

Consulta: "portal de cliente con área privada, gestión documental y firma electrónica".
La búsqueda encuentra un presupuesto casi calcado, primera posición indiscutible… **de
2019** (frontend en AngularJS, proveedor de firma que ya no existe, tarifas de otra época).
Como referencia de *qué partidas* tiene un portal, orienta; como referencia de *cuánto
cuesta hoy*, es **peligroso** — y el LLM generador no tiene forma de saberlo. El embedding
codifica **lo que el texto dice, no cuándo se escribió, ni con qué tecnología, ni si sigue
siendo verdad**. Esas dimensiones viven en los **metadatos** — la técnica de recuperación
con mejor relación coste-beneficio (la única cuyo coste de ejecución es **negativo**:
filtrar antes de buscar abarata todo lo que viene después).

## Filtros duros: reducir el universo antes de buscar

Condiciones sobre metadatos que **excluyen** antes de que la similitud opine (el `WHERE` de
toda la vida conviviendo con `embedding <=> :q`). **Trampa clave**: los índices ANN (HNSW)
**no entienden de `WHERE`** — navegan el grafo sobre el universo completo y el filtro se
aplica **después**. Si pides 50 con un filtro que cumple el 5% del corpus, puedes acabar
con 2 resultados o **cero** sin error visible. Mitigaciones: `hnsw.iterative_scan`
(pgvector ≥0.8, sigue pidiendo candidatos hasta reunir los solicitados tras el filtro) e
**índice parcial** (HNSW solo sobre las filas que cumplen). Hábito de fondo: al combinar
filtros con ANN, **verifica la cardinalidad de lo que vuelve y déjala en los logs** ("el
filtro vació el resultado en silencio" es de los fallos más desconcertantes).

Segunda condición: **los metadatos tienen que existir y bien**. La fecha viene gratis;
tecnología/sector/tamaño hay que **extraerlos en la ingesta** (reglas o LLM de extracción
estructurada), **una vez por documento**. Un filtro duro sobre un metadato mal extraído es
**peor que ningún filtro** (excluye con confianza al mejor candidato). Filtros duros solo
para metadatos de confianza; lo dudoso, como mucho, pondera.

## El tiempo: el metadato que nunca es opcional

En un histórico de presupuestos, **lo reciente vale sistemáticamente más** (precios
caducan, stacks rotan). Dos familias:
- **Ventana dura** (solo últimos N años): simple, pero brutal en el borde (3 años 11 meses
  compite; 4 años 1 mes no existe). Peligrosa con corpus escaso.
- **Decaimiento continuo** (penalización progresiva, exponencial): un parámetro con lectura
  de negocio, la **semivida** (cada cuántos días pierde la mitad del peso).

```python
def temporal_weight(document_date, half_life_days=900):
    age_days = (date.today() - document_date).days
    return 0.5 ** (max(age_days, 0) / half_life_days)
```

Con semivida 900 días: hace 1 año conserva ~76%; de 2019 ~15% (sigue existiendo,
degradado; ya no le gana la 1ª posición a un equivalente reciente). La semivida se **elige
con juicio de dominio**, no se optimiza con fórmula. Se combinan: ventana generosa como
seguridad + decaimiento dentro.

## Ponderación dinámica (con advertencia seria)

Que el peso de cada metadato **dependa de la consulta** (si menciona una tecnología, la
coincidencia tecnológica pesa; si es banca, sube el sector). Se aplica como
**multiplicadores sobre la ordenación final**, definidos en **config**. Advertencia: es
donde el exceso de ingeniería acecha mejor disfrazado — cada peso es un número mágico que
justificar/recalibrar/depurar; 7 boosts interactuando = nadie sabe por qué un doc quedó
tercero (opacidad artesanal, peor que la del embedding). Progresión conservadora: primero
filtros duros + decaimiento (dos decisiones explicables); ponderación dinámica solo donde
haya **evidencia medida**. *"Si no puedes explicar en una frase por qué un boost vale 1,3 y
no 1,5, no estaba listo para producción."*

## Ensamblar el pipeline: el orden es el mensaje

Principio: **lo barato y excluyente al principio; lo caro y fino al final; lo blando al
cierre.**
1. **Reformulación y routing** (operan sobre la consulta, deciden qué/dónde).
2. **Filtros duros** empotrados en la consulta (reducen el universo antes de que nada caro
   lo recorra).
3. **Búsqueda** (dos ramas) + **fusión** sobre el universo ya filtrado.
4. **Reranking** al final del tramo caro (la etapa más costosa por documento, solo sobre
   los supervivientes).
5. **Ponderaciones blandas** (temporal, contextual) como último ajuste sobre los finalistas.

Asimetría deliberada: **filtros duros lo más temprano** (ahorran trabajo a todo lo que
sigue); **ponderaciones blandas lo más tarde** (ajustar sobre el conjunto pequeño, donde
equivocarse es barato). Invertirlo produce los clásicos: rerankear docs que un filtro iba a
tirar (dinero quemado), o ponderar tan pronto que expulsas candidatos antes de que el
reranker los valore (información destruida). Y: **no todas las consultas necesitan todas las
etapas** — cada una activable/observable por config (para medir su aporte y para que la
consulta simple no pague el peaje de la compleja).

## Idea para llevarse

La similitud responde "¿de qué habla?"; la relevancia real necesita además "¿de cuándo es,
de qué tecnología/sector, y cuánto me fío?" → **metadatos**. Filtro duro (abarata, elimina
lo que nada posterior arregla) + ponderación blanda (afina sin destruir candidatos) +
tiempo (ventana por razón categórica, decaimiento por erosión). Todo con la condición que
sostiene el edificio: **metadatos extraídos con calidad en la ingesta**.
