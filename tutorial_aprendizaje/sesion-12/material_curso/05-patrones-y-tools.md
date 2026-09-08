# Lección 5 — Patrones de agentes y diseño de tools de calidad (21 min)

> Notas fieles (Antonio Pérez). Resumen didáctico, no transcripción.

"Agente" no es una cosa. Dos mitades: la **forma** del agente (ejes de diseño) y la **palanca** que
dirige su comportamiento dentro de esa forma (el diseño de tools).

## Los tres ejes de la forma
- **Un solo paso vs iterativo**: ¿cuántas vueltas? Un paso (casi un pipeline con una decisión) para
  lo simple; iterativo para problemas cuya forma no conoces de antemano. Decisión de **coste vs
  necesidad** — si se resuelve en un paso, un paso. La iteración no es el valor por defecto.
- **Reactivo vs proactivo**: ¿decide según lo último observado, o anticipa hacia un objetivo? El
  reactivo es simple y robusto (no se rompe cuando la realidad no encaja) pero puede ser miope; el
  proactivo es eficiente si el camino es predecible, frágil si no. Para transcripciones (traen
  sorpresas), la reactividad suele ganar, con una pizca de proactividad (descomponer al principio).
- **Plan fijo vs planificación dinámica**: ¿cuándo se decide el plan? Fijo = auditable, rígido;
  dinámico = adaptable, imprevisible.

Los ejes **no son ortogonales** (proactivo↔plan fijo; reactivo↔dinámico). No son casillas de un
catálogo: son lentes para pensar la misma decisión. El estimador: **iterativo, mayoritariamente
reactivo, con planificación ligera y dinámica**.

## Enrutar la forma por caso (precede a todo)
No elijas una forma para todas las entradas: **elige la forma por caso**. La mayoría de
transcripciones son simples → una clasificación barata al principio manda las simples al pipeline de
un paso y solo las complejas al agente iterativo. Pagas la autonomía **solo cuando el problema la
exige**. La pregunta deja de ser "qué forma tiene mi agente" y pasa a ser "qué forma merece cada
entrada".

## Las tools dirigen al agente
Fijada la forma, lo que el agente decide bien o mal depende **casi por completo de las tools**:
cuáles existen y cómo las describes (el modelo lee nombres/descripciones/schemas, **no tu código**).
**Principio que ahorra depuración:** cuando el agente se comporta mal (elige mal, inventa argumentos,
mezcla componentes), casi siempre el fallo está en **la descripción o el conjunto de tools**, no en
el modelo. El modelo hizo lo que tus descripciones decían.

## La descripción es un prompt que se itera
Se escriben, se prueban, se observan resultados, se ajustan. Una descripción vaga
("Searches historical budgets.") deja al agente sin saber que debe buscar **un componente a la vez**.
La versión que arregla lleva **la restricción, el contraejemplo y la razón** dentro de la descripción
("ONE component at a time; never combine unrelated components like an ERP integration and a data
migration, because mixed results cannot be compared"). La diferencia entre estimar bien o producir
números sin sentido vive en un campo de texto.

## El conjunto de tools (no solo cada tool)
Demasiadas con fronteras solapadas → el modelo duda; muy pocas y genéricas → hace malabares con
argumentos. Punto dulce: **conjunto pequeño con fronteras nítidas** (una por operación). Namespacing
si crecen. Señal de alarma: si explicas *cuándo no* usar una tool en favor de otra, las fronteras
están mal trazadas.

## Optimizar = mirar las trazas
Método empírico: ejecuta el agente sobre transcripciones representativas, **lee las trazas** (qué tool,
qué argumentos, en qué orden, dónde falló), rastrea cada anomalía a su causa (descripción vaga, frontera
mal puesta, resultado ruidoso, error mudo), arregla y re-ejecuta. Ejemplo: si llama a
`calculate_estimate` antes de buscar todos los componentes, la causa es que su descripción **no declara
la precondición** ("only call this after budgets have been searched for every component") → lo arreglas
con una frase, sin tocar el modelo. **La calidad de tus trazas determina tu capacidad de optimizar.**

## Idea
Forma = decisiones de control de flujo; tools = ingeniería de interfaces y prompts. Ninguna es ML: no
consigues un agente mejor esperando un modelo mejor, sino **eligiendo la forma adecuada y afinando las
tools hasta que las trazas tienen el aspecto que deben**.
