# 00 — Productos IA avanzados (introducción)

> Material del curso LIDR · AI Engineering · Sesión 4 (Antonio Pérez). Recuperado de la plataforma.

En la sesión 03 el sistema empezó a parecer un producto (abstracción, eficiencia, interfaz utilizable). Ahora se cuestiona **la decisión menos pensada de los productos con IA: la interfaz**.

Casi todos arrancan con un chat (textarea + botón). Parece natural, pero traslada al usuario el peso de **saber promptear**, y la calidad pasa a depender de algo que no controlas. En esta sesión damos la vuelta a esa decisión y convertimos el estimator en un producto real con **cinco capas de ingeniería** que separan un demo de algo desplegable con confianza:

- **El chat como antipatrón** — cuándo perjudica, qué patrones de UI funcionan cuando el espacio de tareas es acotado, cómo decidir entre chat y formulario tipado.
- **Prompts como artefactos de software** — archivos versionados, separación estructura/datos, tests en CI sin coste de API.
- **Datos estructurados** con JSON Schema.
- **Guardrails** de input y output + validación semántica.
- **Cacheo semántico** (entiende intención, no strings literales).

El objetivo no es solo mejorar la interfaz: es **ganar control sobre el comportamiento** (reducir variabilidad, aumentar consistencia, que el resultado deje de depender de cómo escribe el usuario). El modelo deja de ser el centro y pasa a ser una pieza dentro de una arquitectura de producto.

## Contenidos del módulo
1. De interfaz conversacional a interfaz de producto
2. Plantillas de prompts y prompting desde backend
3. Extracción de datos estructurados
4. Guardrails y validación de outputs
5. Cacheo semántico de respuestas

**Ejercicio (pre-sesión):** del chat a interfaz de producto. Las **partes 3-5 (JSON estructurado, guardrails, cacheo semántico) se hacen en el directo**, no en el ejercicio.
