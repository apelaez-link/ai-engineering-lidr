# 00 — De prototipo a producto (introducción)

> Material del curso LIDR · AI Engineering · Sesión 3 (Antonio Pérez). Recuperado de la plataforma.

En la sesión anterior construiste la primera versión funcional del sistema: un endpoint
que respondía, pero aún lejos de algo utilizable en un entorno real. En esta sesión damos
un paso clave: **convertir ese backend en un sistema que empieza a comportarse como un
producto**. El foco ya no está en que "responda", sino en *cómo* responde, *cómo* escala
y *cómo* se integra en un contexto de uso real.

## Lo que vamos a construir

- **Wrapper de abstracción** — una capa sobre el LLM que permite cambiar de proveedor sin
  tocar lógica de negocio, con fallback automático si uno falla.
- **Cacheo inteligente** — transcripciones idénticas no repiten la llamada al modelo.
  Primera vez: 4 segundos. Segunda vez: instantáneo.
- **Streaming con SSE** — el usuario ve la estimación escribiéndose en tiempo real, no un
  spinner durante 15 segundos.
- **Trazabilidad completa** — cada llamada queda registrada con modelo, tokens, coste y latencia.
- **Interfaz web conversacional** — Streamlit como cara visible del estimador.

Son los patrones que separan un script de demo de un sistema preparado para producción —
y los usarás en cualquier proyecto con LLMs. Añadirás capas que no suelen aparecer en
tutoriales básicos pero que son imprescindibles en sistemas reales: **abstracción,
eficiencia, observabilidad y experiencia de usuario**.

El resultado no es solo mejor rendimiento, sino un **cambio de naturaleza** del sistema:
pasa de ser un experimento técnico a una base sólida sobre la que construir producto.

## Contenidos del módulo

1. 🎥 Introducción: de prototipo a producto
2. 🗒 Interfaces conversacionales, frameworks y librerías
3. 🗒 Abstracción de proveedores y estrategias de fallback
4. 🗒 Cacheo inteligente de respuestas
5. 🗒 Streaming y manejo de respuestas largas
6. 🗒 Observabilidad, logging y trazabilidad

**Ejercicio práctico:** interfaz conversacional con Streamlit para el Proyecto 1.
