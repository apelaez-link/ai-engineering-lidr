# Lección 6 — Cuánto cuesta un agente (18 min)

> Notas fieles (Antonio Pérez). Resumen didáctico, no transcripción.

Un agente hace el mismo trabajo que un pipeline y puede costar **varias veces más**: no es un
defecto, es el **precio estructural de la autonomía**. "Es más caro" no es un número; hay que
convertirlo en algo **medible**.

## De dónde sale el sobrecoste (4 fuentes)
1. **Más llamadas** al modelo: una por vuelta del bucle (8 vueltas vs 1-2 del pipeline).
2. **El contexto crece en cada vuelta = el factor DOMINANTE.** Cada iteración reenvía todo lo
   acumulado (transcripción + decisiones + cada observación). La 8ª llamada cuesta como la 1ª + 7
   rondas de observaciones arrastradas. Los tokens de **entrada** (los que más se facturan en
   volumen) crecen vuelta a vuelta → coste **no lineal** en nº de pasos.
3. **Tokens de razonamiento**: el modelo delibera en cada vuelta, y se facturan (como salida).
4. **Exploración y reintentos**: reformular, deshacer — correcto, pero cuesta tokens que el pipeline
   no gasta.

## La cuenta del ~5-6×
Pipeline ≈ 2 llamadas, contexto acotado (~8.000 tokens). Agente sobre transcripción compleja ≈ 6-8
vueltas: entrada que sube 2k→4k→6k→~9k (arrastra todo), promediando ~40.000 de entrada + ~8.000 de
salida/razonamiento ≈ **48.000 vs 8.000 → ~6×**, y **casi todo el sobrecoste está en los tokens de
entrada que engordan**. A escala: 1M tareas/mes a 5× tokens ≈ ~1,5M$/año de más. El multiplicador
depende del caso → **sin medirlo, presupuestas a ciegas**.

## Cómo medirlo
Cada respuesta trae `usage` (tokens de entrada, salida, y desglose de razonamiento). Un **`CostLedger`**
que acumule por vuelta da visibilidad total (`ledger.add(response.usage)` tras cada llamada).
⚠️ Los **tokens de razonamiento se facturan como salida y ya están dentro de `output_tokens`** — no
los sumes aparte (duplicarías); llévalos por separado solo para ver qué fracción es deliberación.
Mide además: **coste por paso** (revela el crecimiento del contexto), la **distribución (p95, no la
media** — la cola larga de un agente confundido es lo que arruina el presupuesto), la **comparación
vs pipeline** sobre las mismas entradas (el ratio que justifica la autonomía), y **qué tool infla el
contexto** (registra el tamaño de cada observación).

## Cómo controlarlo (palancas, por impacto)
1. **Enrutar** (la mayor, y está *antes* del agente): no mandes al agente lo que un pipeline resuelve.
2. **Adelgazar el contexto** (mayor palanca dentro del bucle): resumir observaciones viejas, descartar
   irrelevantes, guardar **ids en vez de payloads**; que `search_budgets` devuelva 5 referencias
   limpias, no 200 filas.
3. **Acotar la cola**: `MAX_STEPS` + **presupuesto por ejecución** (si supera un umbral de tokens/coste,
   córtala y trátala como revisión).
4. **Ajustar modelo y razonamiento** al trabajo (no toda decisión necesita el máximo esfuerzo; modelo
   más barato para sub-tareas acotadas). El nivel de razonamiento es un **dial de coste directo**.
5. **Cachear** lo determinista (búsquedas equivalentes entre ejecuciones).

## Idea
El coste es **medible hasta el token, atribuible por paso y controlable con ingeniería corriente**
(instrumentar, presupuestar, enrutar, cachear). Marco de decisión: el agente no es "mejor" que el
pipeline, es otro **intercambio coste/capacidad**. La pregunta no es si funciona (casi siempre
funciona), sino si el **valor que aporta justifica el multiplicador que acabas de medir**. Estimación
de alto valor → 5× es una ganga; tarea de bajo valor y alto volumen → el pipeline te servía mejor.
