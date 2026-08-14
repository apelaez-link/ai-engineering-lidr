# Lección 1 — Reranking: cuando el top-k vectorial no es suficiente (24 min)

> Notas fieles de la lección (Antonio Pérez). Resumen didáctico, no transcripción.

## El problema central

La búsqueda vectorial (bi-encoder) es **excelente encontrando candidatos y mediocre
ordenándolos**. Ejemplo del proyecto: para una consulta de "plataforma de e-commerce",
puede devolver en primera posición un presupuesto de "app de pagos" — están cerca en el
espacio vectorial (comparten vocabulario), pero para *estimar* el e-commerce ese
presupuesto es casi inútil (el esfuerzo está en catálogo/inventario/admin, no en pagos).

La solución **no** es cambiar de modelo de embeddings ni afinar el chunking: es **añadir
una segunda etapa** que haga bien lo que la primera hace mal.

## Por qué el bi-encoder ordena mal

Codifica cada texto **por separado** y lo comprime en un vector fijo. Eso lo hace
barato (los documentos se vectorizan una vez en la ingesta; buscar = comparar contra
vectores precalculados con un índice ANN). Pero la compresión se paga en el ranking fino:
1. **El vector promedia**: un presupuesto que menciona pagos "de pasada" y otro que va
   *sobre* pagos pueden quedar a distancia parecida — el vector no distingue "habla
   principalmente de esto" de "lo menciona entre diez cosas".
2. **Consulta y documento nunca se miran**: la similitud coseno es geometría entre dos
   resúmenes comprimidos, no una lectura conjunta. El modelo no puede razonar "esto pide
   e-commerce y esto trata de pagos; se parecen pero no es lo que pide".

Resultado práctico: entre los **top-50** los relevantes casi siempre están, pero **el
orden dentro de esos 50 es poco fiable** — y al RAG le va la vida en ese orden.

## Cross-encoders: leer los dos textos a la vez

Un **cross-encoder** concatena consulta + documento y los procesa **juntos**: la
atención opera sobre ambos a la vez, y la salida es directamente **una puntuación de
relevancia del par** (no un vector). Captura lo que el bi-encoder destruyó al comprimir.
En benchmarks de ranking, superan sistemáticamente a los bi-encoders en precisión de
ordenación. **Precio:** nada que precalcular → una inferencia por par consulta-documento;
puntuar todo el corpus por cada consulta es inviable.

- bi-encoder = impreciso y rápido; cross-encoder = preciso y lento. Ninguno solo resuelve.

## Recall-then-rerank (el patrón)

1. **Recall (amplio y barato)**: la búsqueda vectorial trae top-N (p. ej. 50). No pedimos
   orden fino, pedimos que los relevantes **estén** en el conjunto.
2. **Precision (fino y caro)**: el cross-encoder puntúa esos N pares y reordena → top-k
   (p. ej. 5).

Los dos números tienen criterio propio:
- **N (recall)** controla el *techo*: si el relevante no entra en el top-N vectorial,
  ningún reranker lo rescata (reordena, no recupera). En corpus pequeños/heterogéneos,
  30–75 suele bastar; vigilar en qué posición vectorial estaban los relevantes dice si
  el margen sobra.
- **k (final)** lo dicta el consumidor (el LLM): 5 presupuestos bien elegidos > 15
  mediocres (el generador también sufre con ruido).

## Modelos: local vs hospedado

- **Local (sentence-transformers)**: `ms-marco-MiniLM` (clásico, **inglés**), pequeño y
  rápido en CPU. Para español/multilingüe: `mmarco-mMiniLMv2` (ligero) o
  `BAAI/bge-reranker-v2-m3` (más potente, más pesado). A favor: coste marginal cero, los
  datos no salen, sin red. En contra: PyTorch engorda la imagen, memoria permanente,
  calidad no puntera.
- **Hospedado (Cohere Rerank)**: multilingüe, mejor calidad, integración trivial. En
  contra: coste por consulta, dependencia de red en el camino crítico, y los documentos
  viajan a un tercero (con presupuestos de clientes, esto es conversación previa).
- **Posición del profesor**: para sistema interno + corpus en español + datos sensibles,
  empezar con **cross-encoder multilingüe ligero en local**; saltar a hospedado solo si
  la calidad se queda corta de forma **medible**.

## Implementación (claves de producción)

- El modelo se **carga una vez** en el arranque (cargarlo por consulta = desastre de
  latencia). Singleton de ciclo de vida; el healthcheck espera a que cargue.
- El reranker **recibe y devuelve el mismo tipo** (lista de chunks → lista más corta y
  mejor ordenada) → etapa **opcional y componible**: activar/desactivar es un booleano
  de config → comparar su impacto es un experimento, no una refactorización.
- **Logging** de tamaños entrada/salida + modelo (auditar por qué se eligieron esos docs).
- En un servicio asyncio, la inferencia del cross-encoder (cientos de ms, cómputo local)
  **bloquea el event loop** → despacharla a un thread pool (`asyncio.to_thread`).

## Latencia y cuándo NO rerankear

Se paga **siempre** en el camino crítico. Órdenes de magnitud (lote 50): MiniLM CPU
decenas–cientos de ms; modelo potente sin GPU hasta segundos; API externa 100–500 ms +
red. La pregunta correcta no es "¿cuánto tarda?" sino "**¿qué fracción de mi presupuesto
de latencia consume y qué me devuelve?**".

No rerankear si: (1) el ranking vectorial **ya es suficiente** (corpus pequeño y bien
diferenciado); (2) el cuello está **antes** (los relevantes no entran en el recall → es
problema de recall/chunking/embeddings, no de orden); (3) el **presupuesto de latencia no
da**. Señal de que SÍ toca: los relevantes están entre los candidatos **pero no arriba**.

## Conexión con nuestra entrega (S10)

Construimos exactamente este wrapper en [`reranker.py`](../../../app/embedding_pipeline/reranker.py)
(`CrossEncoderReranker`, `ms-marco-MiniLM` inglés porque nuestro corpus es inglés, carga
perezosa, recall-then-rerank top-15→top-5). Y la medición confirmó el punto (3): en
nuestro corpus el ranking vectorial **ya está en el techo**, así que el rerank no aporta
precisión y solo añade latencia. Justo el caso "cuándo NO rerankear".
