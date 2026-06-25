# 🎥 Directo sesión 5 — Q&A y consejos del mentor

> Recuperado de la página "Grabación y material sesión 5". Útil si no pudiste asistir al directo
> (los temas del directo: compresión de memoria con **anclas**, **tier dinámico** y **Actor-Critic-Boss**).
> La grabación y las slides (`Sesi_n_5_-_Funcionalidades_avanzadas.pptx`) están en la plataforma.

## Preguntas y respuestas del directo
- **Extractor de metadatos alucina tecnologías inexistentes** → revisar el prompting: incluir en el system prompt un **ejemplo exacto del formato** y constraints explícitas ("nunca nombres una tecnología que no haya aparecido en la transcripción"). Elimina la mayoría de alucinaciones a priori.
- **¿Medir el % de alucinación a nuestro nivel?** → Sí, factible con prompting + guardrails. Es lo que hace el **Golden Dataset**: defines la solución correcta esperada, la comparas con la real y sacas una métrica de corrección.
- **Anclas: ¿los tokens crecen?** → Un poco, pero las anclas son fragmentos pequeños (coste despreciable) y garantizan que lo importante nunca se pierde en los resúmenes. Merece la pena.
- **¿Anclas fijas o dinámicas?** → Se detectan **dinámicamente** durante la conversación; los **patrones** que definen qué es ancla (NDA, contrato firmado, deadline duro) son fijos.
- **Historial vs memoria conversacional** → Historial = mensajes en bruto (dentro de una sesión). Memoria = capa de gestión por encima (resúmenes, anclas, metadatos), orientada a persistir entre sesiones.
- **¿Tier dinámico cuando ya conoces los usuarios?** → Si los tienes en BBDD con su tier, el **estático** basta. El dinámico es para cuando no sabes a priori con quién hablas (prospección: inferir si es CTO, PM o ejecutivo por el tono).
- **¿Que el LLM sugiera anclas?** → Las anclas vienen **del usuario**, no del modelo (coger anclas de la respuesta del LLM introduce riesgo de alucinación). Puedes pedirle que sugiera, pero **decide el humano**.
- **¿Cómo gestionar la degradación al cambiar de modelo?** → Antes de tocar producción, corre **toda la suite de evals + golden cases en staging con un dump de producción**. El nuevo modelo debe mantener o mejorar los niveles; si degrada, no se sube. Aplica igual a cambios de arquitectura o reindexado.
- **¿Combinar actor monolítico y Actor-Critic-Boss?** → Sí: ACB para flujos críticos, monolítico para tareas simples/rápidas. Cada subflujo puede tener su arquitectura.
- **¿La arquitectura depende del usuario?** → Del **flujo de trabajo** (complejidad y criticidad de la tarea), no del usuario.
- **¿Tests por agente o del proceso completo?** → Evalúa el **proceso completo primero**; baja a agente-por-agente solo cuando ya estás al ~70% y quieres llegar al 80%. Evaluar cada tool individualmente suele ser sobre-ingeniería.

## Consejos del mentor
- En el system prompt **marca los límites**, no solo lo que quieres ("si no estás seguro, no lo metas").
- **Reserva el LLM** para donde aporta; lo determinista (regex/heurística) hazlo sin LLM (menos latencia/coste/incertidumbre).
- Usa **anclas** para proteger info crítica (NDAs, deadlines, compliance, presupuestos) en conversaciones largas.
- Pon **máximo de iteraciones** en Actor-Critic-Boss (>5 sin acuerdo = algo falla en el prompt/proceso, no en los agentes).
- Si ACB no converge, el fallo casi siempre está en el **proceso o el system prompt**, no en los agentes.
- Prueba los **cambios de modelo en staging con datos reales** antes de producción.
- Encuentra tu **punto dulce entre tests y velocidad**; evaluar cada tool individualmente suele ser sobre-ingeniería.
- **Combina arquitecturas según el flujo**, no uses la misma para todo.
- **Experimenta** con Actor-Critic-Boss después de la sesión: la intuición viene de tocar el código.
- El **Golden Dataset** es la forma de medir progreso real (casos pequeños, grandes, ambiguos, contradictorios).
