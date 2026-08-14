# 05 — Actor-Critic-Boss: composición de roles que eleva la calidad

> Material del curso LIDR · AI Engineering · Sesión 5 (Antonio Pérez). (≈18 min) · **Tema del directo.**

**El techo:** hay una calidad que no se rompe solo refinando prompts. Una estimación de una sola pasada es buena en promedio pero inconsistente donde el error cuesta más (aritmética que no cuadra, riesgos omitidos, componentes en la justificación pero no en el desglose). El problema no es de **instrucción**, es de **verificación**: un humano genera, **revisa**, encuentra error, corrige, revisa de nuevo. Un único LLM en una llamada genera y se autovalida a la vez, y lo hace mal. *Self-Refine* (Madaan et al., 2023): separar generación de feedback en 2 llamadas mejora ~20% absoluto sin entrenamiento.

## Los tres roles
- **Actor** — genera la estimación inicial (la llamada que el estimator ya hace; template por tier + schema). Su salida deja de ser final y pasa a ser **candidato**.
- **Critic** — recibe el output del actor y lo **evalúa** contra criterios explícitos (¿completo? ¿aritmética cuadra? ¿riesgos coherentes con el alcance? ¿contradice el project_metadata? ¿faltan componentes?). NO genera una estimación nueva: produce **feedback estructurado**.
- **Boss** — recibe estimación + feedback y **decide**: acepta / devuelve al actor con instrucciones / sintetiza la versión final. **Limita las iteraciones** (coste/latencia).

## Por qué TRES y no dos
Si el crítico también decide, aparecen dos fallos de Self-Refine puro: **bucles infinitos** (el crítico siempre encuentra algo) y **sesgo de confirmación temprana** (el crítico, siendo el mismo modelo que el actor, defiende lo recién producido). Separar **evaluación** (crítico) de **decisión** (boss) rompe ambos. Paralelo humano: ingeniero (hace) / revisor (detecta) / tech lead (decide qué bloquea el merge).

## Anclaje en la literatura
- **Actor** = Generator/Optimizer (Anthropic *Building Effective Agents*; Madaan *Self-Refine*).
- **Critic** = Evaluator/Self-Verifier (Shinn et al. *Reflexion*).
- **Boss** = Orchestrator/Supervisor (Anthropic *orchestrator-workers*).
ACB compone **Evaluator-Optimizer** + **Orchestrator-Workers** (los dos workflows de *Building Effective Agents*), sin frameworks.

## Cuándo compensa (≥2 condiciones)
- **Coste del error alto** (estimación base de un contrato).
- **Criterios de evaluación claros** (sin ellos el crítico no tiene material).
- **Latencia extra tolerable** (informe que se entrega cuando esté listo, no chat inmediato).
**Overkill** cuando: tarea simple, ya hay tests hard que cubren los fallos, el coste por petición es crítico, o los criterios son vagos. **Regla:** aplícalo solo a los **caminos críticos** (la estimación final), no a todas las llamadas (ni a la extracción de metadata).

## Anti-patrones
- **Tres llamadas con el mismo prompt** (3× coste, 0 ganancia). Cada rol necesita un prompt estructuralmente distinto.
- **El crítico devuelve texto libre** → el boss lo malinterpreta. El feedback debe ser **estructurado** (issues con categoría/severidad/campo afectado — Pydantic, como la sesión 4).
- **Iteraciones sin límite** → una petición difícil consume 5-6 ciclos. El boss opera con **presupuesto máximo (2-3)**; al agotarse, sintetiza la mejor respuesta disponible. *Producción se prefiere a perfección.*

## Recursos
- Anthropic — *Building Effective Agents* · Madaan et al. — *Self-Refine* (2023) · Shinn et al. — *Reflexion* (2023)
