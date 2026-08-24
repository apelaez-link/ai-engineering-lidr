# Lección 2 — Síntesis de múltiples presupuestos: combinar fuentes que se contradicen (19 min)

> Notas fieles (Antonio Pérez). Resumen didáctico, no transcripción.

## El problema: no coinciden

Para estimar "pagos" recuperas 3-4 presupuestos parecidos y sus cifras **no coinciden**:
fintech 2024 = 40h, e-commerce 2023 = 90h, fintech reciente = 55h. Los tres relevantes, bien
recuperados, bien destilados, y se contradicen. Un generador ingenuo hace una de tres cosas,
todas malas: **promedia en silencio** ("62h"), **coge la primera**, o **inventa** un
intermedio plausible que no es de ninguna fuente. Las tres dan una cifra **plausible**;
ninguna da una cifra **defendible**.

## Sintetizar no es elegir un número
Es entender **por qué** discrepan, decidir **cuánto pesa** cada fuente, y producir algo
**honesto** sobre lo que sabe y lo que no. La discrepancia casi siempre tiene una razón que
está en los datos: el de 40h tenía la pasarela ya integrada (cifró solo la conexión); el de
90h la hizo desde cero y es antiguo; el de 55h es reciente y comparable. **La discrepancia es
información**: te dice que la estimación depende de una variable (¿pasarela integrada?) que el
cliente no mencionó. Aplastarla en "62h" tira lo más valioso. Conservarla — "55–90h desde
cero; ~40h si la pasarela ya está integrada" — es una estimación **usable** (le dice al jefe
de proyecto qué preguntar antes de comprometerse). Objetivo doble: **número/rango defendible**
+ **razón explícita** de la discrepancia.

## Pesar las fuentes con criterio
El retrieval ya calculó 3 señales por fragmento: **relevancia** (reranker), **recencia**
(decaimiento temporal), **similitud** (vector). Se combinan en un peso único **auditable**:
`0.5*relevancia + 0.3*recencia + 0.2*similitud`. Regla dura: **3 señales, no 7**. Cada factor
extra es un número mágico que defender; si no puedes explicar en una frase por qué relevancia
pesa 0.5 y no 0.4, ese coeficiente no estaba listo.

## Agregar ANTES de generar (dos etapas)
- Opción simple: pasar todo al modelo y que razone de una vez → número de **caja negra**,
  difícil de auditar.
- Opción robusta: **separar aritmética de juicio**. En código calculas un **ancla
  determinista** por componente (mediana ponderada, rango low/high, flag de contradicción) y
  luego el modelo **razona sobre esos agregados** en vez de inventar la aritmética.
  - **Mediana ponderada, no media**: robusta a outliers (un presupuesto de alcance muy
    distinto no arrastra el ancla).
  - **Contradicción = dispersión alta ENTRE fuentes fuertes** (no dispersión a secas): si la
    cifra discordante viene de una fuente de peso bajo, es outlier ignorable; si dos fuertes
    discrepan, es contradicción real que hay que sacar a la luz. Umbral ejemplo: spread >50%.

## Generar la síntesis: rango, razón y fuentes
El schema obliga a que cada componente sea un **rango** (colapsa a punto cuando hay
confianza; se abre cuando hay contradicción) + `rationale` que explica la discrepancia +
`source_chunk_ids` + `contested`. Las **instrucciones** son donde se gana la honestidad:
prohibir el **promedio ciego**, exigir explicar el desacuerdo, **quedarse dentro del rango
[low,high]** del agregado salvo razón explícita, y no citar fuentes no provistas.

## Trade-offs honestos
- Una pasada (simple, opaca) vs dos etapas (ancla trazable, más maquinaria + riesgo de que el
  modelo se salga del ancla → lo vigilan las instrucciones). Para comprometer dinero, gana la
  **auditabilidad**.
- La ponderación es tan buena como sus señales: si el reranker o la semivida están mal
  calibrados, el ancla es "confiadamente incorrecta". Pesar **amplifica** señales malas.
- Mediana con N=2-3 es tosca: el valor está más en el **rango y la explicación** que en el
  estadístico central. Umbral de contradicción = **política**, no verdad; ajústalo por
  cuántas alertas son accionables.
- **El rango incomoda al producto** y hay que defenderlo: colapsar un desacuerdo real en un
  punto de falsa precisión es mentir con apariencia de rigor.
- Sintetizar **no fabrica información**: 4 fuentes débiles no dan buena estimación por mucho
  que las peses. La confianza de la salida refleja la calidad de la entrada.

## Conexión con nuestra entrega (S11)
Nuestro generador ya produce líneas con `sources` + marca "insufficient" cuando no hay
soporte, pero **no** implementa el ancla determinista ni los rangos por contradicción (nuestro
`hours` es un punto). Es la evolución natural: añadir `low/high` + `contested` + mediana
ponderada. Encaja con el enunciado ("la S11 es baseline; se extiende en el directo").
