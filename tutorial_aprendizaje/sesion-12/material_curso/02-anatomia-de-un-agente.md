# Lección 2 — Anatomía de un agente: qué ocurre dentro del bucle (22 min)

> Notas fieles (Antonio Pérez). Resumen didáctico, no transcripción.

"Un bucle" no te dice qué pasa dentro de cada vuelta, y ahí se gana o se pierde el control.
**No puedes depurar lo que no sabes nombrar.** Los órganos del bucle:

## El esqueleto: reason → act → observe → repeat (ReAct)
Viene de **ReAct** (Yao et al.): entrelazar razonamiento y acción es mejor que separarlos (el
razonamiento sin acción alucina; la acción sin razonamiento no sabe qué hacer). En origen era
*prompting* con formato `Thought / Action / Observation`; hoy, con modelos de razonamiento, buena
parte del `Thought` **ocurre nativa dentro del modelo** (tokens de razonamiento que no ves) → para
observabilidad capturas los **reasoning summaries**. El esqueleto necesita **condición de parada**
(respuesta final, o `MAX_STEPS`, o presupuesto agotado): un bucle sin guarda es un bug esperando.

## Razonamiento
Interpretar la situación y elegir la siguiente acción. Vive dentro del modelo; pierdes control fino
sobre la traza salvo que captures los resúmenes deliberadamente.

## Planificación
Decidir la **forma del conjunto** (descomponer en pasos). Dos momentos: **plan por adelantado**
(auditable, rígido) vs **planificación continua** (adaptable, difícil de presupuestar). Con modelos
capaces suele ser **emergente**; forzar un plan explícito es una palanca para auditar.

## Acción
El **único** punto que toca el mundo exterior. Mecánicamente es **function calling**: el modelo
emite una intención, **tú ejecutas**. Aquí vive la seguridad: **mínimo privilegio** — solo las
acciones necesarias; las **irreversibles** pasan por validación o por un humano. `search_budgets`
es de solo lectura (barata de equivocarse); escribir/enviar/mover dinero es otra cosa.

## Observación
Lo que devuelves al modelo tras la acción = su **ground truth** por paso. La **calidad de la
observación gobierna la siguiente decisión**: estructurada y con lo justo (5 relevantes, no 200 en
crudo). **Los errores son observación, y la más importante**: un error informativo ("1 coincidencia
débil, baja confianza") deja al agente reformular; un `error` mudo lo deja ciego.

## Handover
Saber **apartarse**. Dos direcciones: hacia un **humano** (human-in-the-loop: se detiene y pide
criterio cuando la confianza es baja o la acción es cara/irreversible — p. ej. la migración legacy
sin referencias → marcar `needs_review` en vez de inventar), o hacia **otro agente** (delegar;
base de los sistemas multi-agente). Necesita **contrato explícito** (qué estado se transfiere, quién
decide, cómo vuelve). En el estimador: el servicio IA devuelve `status=needs_review` + lo parcial;
el backend lo enruta a una persona.

## El estado que crece (el coste escondido)
El bucle mantiene un **estado** que crece en cada vuelta (decisión + observación) = la **traza**.
Ese estado se **reenvía al modelo** en cada vuelta → cada llamada es **más cara que la anterior**
(la 8ª paga por reenviar las 7 observaciones previas). En agentes largos hace falta **adelgazarlo**
(resumir observaciones viejas, guardar ids en vez de payloads).

## Idea
Nombra las partes y el agente deja de ser una caja negra: razonamiento = lógica de decisión;
planificación = descomposición; acción = llamada con efectos; observación = valor de retorno;
handover = escalado/delegación; bucle = control de flujo con guarda. Nombrarlas es lo que te deja
**instrumentar, testear cada órgano y poner límites donde duelen**.
