# Lección 4 — Detección y mitigación de alucinaciones (21 min)

> Notas fieles (Antonio Pérez). Resumen didáctico, no transcripción.

## La alucinación con coartada

Que la cita **resuelva** (integridad referencial de la lección 3) no dice nada sobre si esa
fuente **contiene** lo que se le atribuye. El modelo puede citar un id válido de un fragmento
que habla de otra cosa. La cita está impecable, la afirmación es falsa: **alucinación con
coartada**, la más peligrosa porque pasó todos los filtros estructurales. Detectarla ya no es
comprobar ids: es comprobar **significado**.

## Tres formas de alucinar
1. **Fabricación**: una cifra que no está en ninguna fuente (el modelo la inventa/rellena).
2. **Atribución falsa**: la cifra existe, pero no en la fuente que se le adjudica (el id cita
   otro componente/proyecto). Como la cita resuelve, los filtros estructurales no la ven.
3. **Extrapolación no fundamentada**: el modelo razona más allá de las fuentes ("un módulo
   complejo rondará las 160h") — un salto que suena experto pero no está en los datos.

Las tres comparten lo incómodo: producen salidas **plausibles**.

## Detectar: lo barato primero, lo caro después
- **Anclaje numérico (determinista, casi gratis)**: cada cifra debe rastrearse a las cifras de
  las fuentes citadas. Si cita fragmentos que dicen 40 y 90, se permite **interpolar** dentro
  del rango (un 65 es mezcla defendible); una cifra **fuera del rango** de todo lo citado es
  extrapolación → se marca. Sin soporte numérico alguno = fabricación. Un `if` caza fabricación
  pura y extrapolación **sin gastar un token**.
- **Verificación semántica (juez LLM)**: para la atribución falsa (un 40h citando un fragmento
  de otra cosa que "cuela" en el rango) hace falta mirar el significado. Un verificador
  instruido para ser **estricto** y **dudar en contra** (ante la duda → no soportado). Es
  **circular** (un LLM juzga a otro LLM); se reduce el riesgo con: **esquema estrecho**
  (`supported: bool`), **modelo distinto y más barato** que el generador (no comparten puntos
  ciegos), y el **sesgo hacia "no soportado"**. Un verificador permisivo es peor que ninguno.
- **Consistencia (cara)**: regenerar la misma cifra N veces; **dispersión alta = adivina**.
  Cuesta N generaciones → solo para líneas de alto impacto/baja confianza. **Trampa**: la
  dispersión confunde "el modelo adivina" con "los datos genuinamente discrepan" — un
  componente que va de 40 a 90 según alcance produce muestras dispersas **con razón**. Solo es
  sospechosa cuando las fuentes coinciden y el modelo no.

## Mitigar: prevenir, validar, abstenerse
- **Prevenir** (lo más barato/efectivo): instrucciones que prohíban explícitamente inventar
  cifras, exijan marcar `grounded=false` en vez de estimar a ojo, y no extrapolar. Reduce el
  volumen que llega a la detección. Rendimientos decrecientes: no resuelvas en el prompt lo que
  toca verificar.
- **Validar** (red post-generación): combinar las 3 señales en una decisión **graduada** por
  línea: `grounded` (anclada + juez OK), `insufficient` (sin ancla + juez rechaza → no emitir
  cifra), o degradar confianza si las señales son mixtas.
- **Abstenerse**: `status="insufficient"` **no es un fallo**, es hacer lo correcto. "No tengo
  datos suficientes" vale infinitamente más que un número inventado que alguien usará para
  comprometer un plazo. Convierte una mentira confiada en una pregunta útil.

## Trade-offs honestos
- La detección **nunca es completa** y añade latencia/coste → capas de barata a cara,
  selectivas. Asumir que las cazarás todas es, en sí, una alucinación.
- El juez es un LLM: suelo de fiabilidad que no superas con más LLM. Cuando el coste del error
  es alto, la última verificación es **humana**.
- La consistencia castiga la **incertidumbre honesta** si no la calibras.
- Abstenerse de más vuelve el sistema **inútil** ("datos insuficientes" en medio corpus). Para
  estimaciones, un falso "grounded" suele ser más caro que un falso "insufficient", pero ambos
  cuestan.

## Conexión con nuestra entrega (S11)
Nuestro sistema ya hace la parte **estructural** (verify_citations → dangling) y la
**abstención** (`grounded=false` ⇒ hours=0, sin inventar). Lo que **no** implementamos aún: el
**anclaje numérico** (comprobar que las horas están en el rango de las cifras citadas) ni el
**juez semántico**. Son la evolución directa, y explican parte de la faithfulness baja de
RAGAS (que es, precisamente, la "versión a escala" de esta detección).
