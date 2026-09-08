# Lección 1 — De pipeline a agente: cuándo tu RAG necesita una capa de decisión (23 min)

> Notas fieles (Antonio Pérez). Resumen didáctico, no transcripción.

## La pregunta no es "cómo", es "por qué"
Nuestro estimador ya funciona con un **pipeline fijo** (reformular → recuperar → generar):
predecible, barato, testeable, rápido. Un agente **no es una mejora gratuita**: es una decisión
arquitectónica con coste, y la mayoría de las veces la respuesta correcta es **no añadirlo**. El
pipeline es el estado por defecto; la pregunta es qué tiene que romperse para salir de él.

## Dónde se rompe el pipeline
Transcripción simple ("landing con formulario") → un componente, una búsqueda, una estimación: el
pipeline lo clava. Transcripción compleja (portal + integración ERP + app móvil + migración
legacy) → **no sabes de antemano cuántos componentes hay, cuántas búsquedas, en qué orden**.
Dos malas salidas dentro del pipeline: una búsqueda gigante que devuelve un revoltijo incomparable,
o un árbol de `if/else` a mano que no escala. Lo que falta no es más retrieval ni mejor generación:
es **capacidad de decisión en tiempo de ejecución**.

## Tres niveles (Anthropic / Barry Zhang)
- **Tarea**: una sola llamada al modelo (resumir, clasificar, extraer).
- **Workflow**: varias llamadas encadenadas en un flujo **que tú defines** (nuestro RAG es esto).
- **Agente**: **el modelo dirige su propio proceso** — decide la siguiente acción según lo que
  observa, hasta que considera que terminó. Tú posees el objetivo y las barreras; no cada rama.

La frase: *con un workflow, la fontanería la controlas tú; con un agente, la controla el modelo.*
La única novedad es la línea `model.decide(...)` (quién elige el siguiente paso). El resto es un
bucle `while` con guarda, control de flujo de toda la vida.

## Qué compras y qué pagas
**Compras exclusivamente orquestación adaptativa**: resolver problemas cuyo árbol de decisión no
puedes pre-mapear. NO compras mejor retrieval, ni mejor generación, ni inteligencia nueva.
**Pagas**: latencia (más idas y vueltas), coste (exploración = tokens; ~10¢ ≈ 30-50k tokens),
**no-determinismo** (mismo input, caminos distintos → testing difícil), **errores que se
componen** (un fallo en el paso 2 contamina 3 pasos más), y **deuda de observabilidad** (hay que
trazar decisiones, no solo entradas/salidas).

## Criterios de decisión
¿Puedes pre-mapear el árbol? → workflow. ¿Forma variable no enumerable? → territorio de agente.
¿El valor justifica el gasto? (alto volumen/bajo valor → workflow; bajo volumen/alto valor →
agente). ¿Coste del error y puedes verificarlo? (si es caro y difícil de detectar, la autonomía
es un pasivo → tools de solo lectura, validación, human-in-the-loop). ¿El modelo es bueno en tu
dominio? El caso canónico que cumple todo: **agentes de código** (ambiguo, valor obvio, modelos
buenos, y **verificable con tests**).

## Cómo aplica al estimador
El pipeline sigue siendo el **camino por defecto** (transcripciones simples). El agente entra como
**capa de decisión POR ENCIMA**, no como sustituto, y las piezas del pipeline se **promueven a
tools** (`search_budgets`, `calculate_estimate`, `validate_estimate`) — **no reimplementas nada**.
Arquitectura de **dos vías con enrutado barato**: un clasificador decide simple→pipeline /
complejo→agente. Todo vive dentro del **servicio IA**; el backend de negocio sigue enviando
transcripción y recibiendo estimación estructurada (mismo contrato).
