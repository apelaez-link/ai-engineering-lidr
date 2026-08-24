# Lección 6 — Evaluación de calidad con RAGAS (19 min)

> Notas fieles (Antonio Pérez). Resumen didáctico, no transcripción. **La lección clave de la Parte 2 del ejercicio.**

## La pregunta que el sistema no sabe responder sobre sí mismo

Los guardarraíles dicen si **esta** respuesta es de fiar. No dicen si el **sistema** es bueno,
ni si mejora o empeora. Has tomado decenas de decisiones (prompt, modelo, ensamblado de
contexto, reranker, versión de embeddings) y cada cambio es **una apuesta a ciegas**: cambias
el prompt "porque parece mejor", despliegas, y descubres semanas después por una queja que
metiste una regresión. **RAGAS quita la venda**: convierte la calidad en **4 números**
comparables entre versiones. No dice si una respuesta es *verdad* (imposible), pero sí si la
versión de hoy es mejor que la de ayer, y **dónde** pierde calidad.

## Las 4 métricas (2 de recuperación, 2 de generación)
- **Faithfulness** (generación): qué proporción de las afirmaciones de la respuesta se **infiere
  del contexto** recuperado. Es la versión a escala de la detección de alucinaciones.
- **Answer relevancy** (generación): si la respuesta **aborda la pregunta** (sin irse por las
  ramas ni rellenar).
- **Context precision** (recuperación): cuántos fragmentos recuperados son relevantes y si los
  buenos están **bien posicionados arriba** (evalúa reranker + búsqueda).
- **Context recall** (recuperación): si se recuperó **todo** el contexto necesario para la
  respuesta de referencia. Necesita `ground_truth`.

**Se leen juntas** (ahí está el diagnóstico): faithfulness baja pero precision/recall altos =
problema de **generación** (buen contexto mal usado); faithfulness alta pero recall bajo = el
modelo va bien con lo poco que le llega, pero el **retrieval** no le da lo necesario.

## Qué necesita RAGAS + el golden set como techo
Por caso: **question, answer (la de tu sistema), contexts (los recuperados), ground_truth**
(la referencia de experto). Las 2 de generación van sin referencia; las de contexto (sobre
todo recall) necesitan `ground_truth`. **Lo más subestimado: el golden set es el TECHO de tus
métricas.** RAGAS calcula números sobre lo que le des; si el set es pequeño, sesgado o con
referencias malas, produce números **confiados y sin sentido**. Un buen golden set cubre el
espectro real: casos claros, ambiguos, **con fuentes que se contradicen** (para ver si entrega
rango y no número falso), y **casos que deben acabar en abstención** ("no hay datos
suficientes"). Si no incluyes un caso que debe abstenerse, no mides si el sistema sabe
abstenerse: premias que conteste siempre. Los **adversariales no son opcionales**.

## Implementación (esqueleto)
Proceso por lotes: cada caso pasa por el pipeline real (retrieval + generación), recoges las 4
piezas en un `Dataset` y llamas a `evaluate(dataset, metrics=[faithfulness, answer_relevancy,
context_precision, context_recall])`. RAGAS usa por dentro un **LLM juez** + un modelo de
**embeddings**; se configura con tu clave OpenAI, `text-embedding-3-small` y un chat como juez
(evalúa en español sin problema). **Aviso honesto del propio profe:** la API de RAGAS **cambia
mucho entre versiones** (nombres de columnas, clases de dataset, cómo se pasan los modelos) →
**fija la versión** y comprueba los nombres exactos contra ella.

## Offline (puerta de regresión) vs producción
- **Offline**: antes de desplegar un cambio, pasas el golden set por la candidata y comparas
  sus 4 métricas con la actual. Si faithfulness o recall caen, **no despliegas** → cazas la
  regresión antes de producción. Necesita `ground_truth` → solo offline.
- **Producción**: **no hay respuesta de referencia** para tráfico vivo → **no puedes calcular
  context recall**. Sí las **sin referencia** (faithfulness, answer relevancy) sobre una
  muestra, más las señales operativas de los guardarraíles (tasa de abstenciones, de citas
  colgantes, de líneas degradadas). Alerta sobre **deriva a la baja**, no sobre valores
  absolutos.

## Trade-offs honestos
- El juez es un LLM → métricas **ruidosas**. 0.82 no es "82% verdadero"; es un número
  **comparable**. Úsalas como **tendencias y comparaciones A/B**, no como notas absolutas.
- El **golden set es el techo** y un techo bajo no se ve (números igual de confiados). Invertir
  en un golden set amplio y representativo **es** la evaluación.
- **Ley de Goodhart**: optimizar una métrica sola estropea las otras (perseguir faithfulness →
  el sistema se abstiene más, cae la relevancia). Las 4 se leen juntas.
- La deriva en producción no siempre es regresión (puede ser que entren consultas más
  difíciles). Cruza la deriva con qué cambió de verdad.
- Evaluar **cuesta** (muchas llamadas al juez × tamaño del set): es un **lote offline**, no un
  guardarraíl en línea.

## Conexión con nuestra entrega (S11)
Es **exactamente lo que montamos**: golden set (el de la S10 + `ground_truth`), `evals/
generation/run.py` con las 4 métricas y juez gpt-4o-mini → tabla comparable. Aprendizajes
vividos: fijamos **ragas 0.4.3** (la API cambia), y hay que llamar a `evaluate()` **fuera** de
un bucle asyncio. Nuestra lectura de los números (la "nota"): **faithfulness 0.38 con
context_precision 0.91** = el diagnóstico "problema de generación, no de recuperación" de esta
lección — el contexto es bueno (precision alta) pero el texto de respuesta (resumen/total/
líneas insufficient) no está verbatim en él. Y nos falta cubrir el golden set con más casos
adversariales/de abstención, que la lección marca como imprescindibles.
