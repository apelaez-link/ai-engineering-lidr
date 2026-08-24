# Lección 1 — Content augmentation: preparar el contexto antes de generar (19 min)

> Notas fieles (Antonio Pérez). Resumen didáctico, no transcripción.

## El agujero entre recuperar y generar

Tras el retrieval tienes buenos candidatos (filtrados, reordenados por cross-encoder,
ponderados por recencia). El paso que casi nadie mira es **qué le pasas exactamente al
generador**. La respuesta honesta habitual: "los fragmentos tal cual". Y un fragmento de
presupuesto real no es una ficha limpia: trae cabeceras, condiciones de pago, módulos que
no vienen al caso, totales, IVA, notas. Al estimar "pagos", el 80% de lo que le das al
modelo es **ruido** para esa consulta. **Content augmentation** es la capa entre recuperar
y generar: convierte fragmentos crudos en **contexto destilado** (lo justo, en el orden
correcto, sin perder trazabilidad). No mejora el retrieval ni el prompt: mejora el material.

## Por qué el ruido es caro (3 costes medibles)
1. **Tokens**: el ruido son tokens que pagas; si media entrada es boilerplate, pagas doble.
2. **Atención**: el modelo no reparte la atención uniforme — lo del principio y el final
   pesa más que el medio. Si la línea que respalda la estimación queda sepultada, el modelo
   puede ignorarla aunque el retrieval la trajera.
3. **Alucinación**: más densidad de cifras irrelevantes = más fácil que agarre la
   equivocada (un "120h" de otro módulo). El ruido numérico es **combustible de alucinación**.

## La capa como pipeline componible
No es una técnica, son varias etapas con contrato uniforme (fragmentos entran, evidencia
destilada sale), cada una **activable/desactivable/medible** por separado:
`comprimir → extraer puntos clave → ordenar → ajustar a presupuesto de tokens`.
Dos claves de diseño: la augmentation necesita saber **qué estás estimando**
(`target_components`) — el retrieval es a nivel de consulta, la destilación es específica de
lo que vas a generar; y hay que **preservar el `chunk_id`** en cada pieza destilada (si el
compresor produce texto huérfano, destruyes la trazabilidad antes de generarla).

## Compresión: extractiva vs abstractiva
- **Extractiva** (quedarte con las líneas relevantes, sin reescribir): barata, sin llamada
  a modelo, y **no puede inventar** (solo copia). Para presupuestos (semi-estructurados)
  suele bastar. Detalle: si el filtro se queda sin nada, **devuelve el fragmento entero**
  (vaciar el contexto en silencio es el mismo error que un filtro de metadatos demasiado
  agresivo) → loguea `was_compressed`.
- **Abstractiva** (resumir con un LLM enfocado a la consulta): flexible (sinónimos, prosa
  larga, transcripciones), pero **añade un segundo punto de generación** → si el resumen
  alucina, la alucinación entra como si fuera fuente. Si la usas, **fuérzala a esquema**
  (extraer campos tipados, p. ej. `BudgetEvidence` con component/hours/cost/...), con `None`
  explícito cuando falta el dato (mejor un None honesto que una cifra de relleno).

## Ordenar y ajustar
- **Edge-loading**: coloca la evidencia más fuerte al **principio y al final**, la débil en
  el medio (donde el modelo menos mira). La señal de orden puede combinar relevancia +
  recencia, de forma **explícita y medible** (no una pila de multiplicadores mágicos).
- **Presupuesto de tokens**: si no cabe, descarta las piezas más débiles y **registra
  cuáles** (para poder rastrear un fallo hasta "dejé fuera la fuente que lo respaldaba").

## Trade-offs honestos
- Extractiva casi siempre gana en corpus de cifras; abstractiva solo para fuentes narrativas.
- Comprimir con LLM por fragmento puede **salir más caro** que pasar los crudos (N llamadas).
  Mídelo antes de asumir el ahorro.
- Tirar lo que no debías (sinónimos: "cobros" vs "pagos") degrada el recall **en esta capa**,
  más difícil de diagnosticar. Cada etapa que puede tirar info debe loguear qué tiró.
- **Sobre-compresión borra el matiz**: a veces el valor está en una nota ("40h pero con la
  pasarela ya integrada") que explica por qué la cifra no es trasladable. El punto óptimo se
  **mide** contra la calidad final.

## Conexión con nuestra entrega (S11)
Nuestra medición RAGAS dio **faithfulness baja (0.38)** justamente por esto: nuestro generador
recibe los chunks **crudos** (sin esta capa) y el texto de respuesta (resumen, total, líneas
"insufficient") no está verbatim en el contexto. La **content augmentation** es la mejora
directa: destilar los chunks a evidencia estructurada antes de generar subiría la fidelidad.
Es lo que el directo extiende sobre nuestro baseline.
