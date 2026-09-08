# Material del curso — Sesión 12: Introducción a agentes de IA

Notas fieles de las **6 lecciones** de la sesión 12 (Módulo 5, Orquestación de agentes).
Resúmenes didácticos en mis palabras (no transcripciones), con la conexión al estimador.

Hilo conductor: un **agente = un bucle** (razona → actúa → observa → repite) que se construye
**a mano, sin framework**, para entender qué automatizan los frameworks (LangChain/LangGraph, S13).
El agente es una **capa de decisión sobre el pipeline** de S9-S11; sus tools envuelven piezas que ya
tienes. Y el mensaje central del directo (Julián): **no vuelvas agéntico un flujo solo porque puedas.**

| # | Lección | Idea clave |
|---|---------|-----------|
| [01](01-de-pipeline-a-agente.md) | De pipeline a agente | tarea/workflow/agente; el agente solo compra orquestación adaptativa, y se paga |
| [02](02-anatomia-de-un-agente.md) | Anatomía de un agente | reason/plan/act/observe/handover + parada + estado que crece |
| [03](03-function-calling.md) | Function calling en la práctica | el modelo pide, tú ejecutas; Responses API = schema plano, `call_id`, paralelo |
| [04](04-bucle-agentico.md) | El bucle agéntico paso a paso | el agente en ~50 líneas (registro + `asyncio.gather` + `MAX_STEPS` + salida estructurada) |
| [05](05-patrones-y-tools.md) | Patrones y diseño de tools | ejes de forma + enrutar por caso; descripciones de tools = prompts que se iteran |
| [06](06-cuanto-cuesta.md) | Cuánto cuesta un agente | 4 fuentes (contexto creciente domina); medir con `usage`; enrutar/adelgazar/acotar |

> Guía de la sesión + resumen del directo + qué construir están en [`../README.md`](../README.md).
