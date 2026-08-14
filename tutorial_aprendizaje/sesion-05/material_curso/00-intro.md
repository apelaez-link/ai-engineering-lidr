# 00 — Funcionalidades avanzadas (introducción)

> Material del curso LIDR · AI Engineering · Sesión 5 (Antonio Pérez). Cierra el módulo CAG.

En la sesión 04 pasaste de interfaces de chat a sistemas donde **tú** controlas el comportamiento. Pero el sistema sigue siendo **estático**: responde bien en una única interacción y bajo condiciones controladas. En producción no es así: los usuarios **no hacen una única petición**, el contexto **no está cerrado**, la información relevante **no vive solo en el prompt**, y la calidad **deja de ser evidente**.

La diferencia entre un prototipo que impresiona y un sistema que aguanta usuarios reales está en **cuatro piezas** (+ un patrón de orquestación):

1. **Enriquecer el contexto** con información del mundo real (adjuntos, fuentes externas).
2. **Gestionar la memoria** sin que se descontrole (memoria ≠ historial).
3. **Adaptar la salida** a cada perfil de usuario (patrón **tier**).
4. **Evaluar la calidad** cuando el output ya no se compara con un valor esperado (testing/evals).
5. **Actor-Critic-Boss**: componer roles para romper el techo de calidad.

El objetivo de la sesión: que el modelo **deje de ser el centro** y pase a ser una pieza dentro de una arquitectura de producto más amplia, que mantiene **coherencia, controla coste/latencia y evalúa su propia calidad**.

**Ejercicio (pre-sesión):** memoria conversacional + contexto enriquecido (memoria + adjuntos). Las piezas avanzadas (anclas, tier dinámico, Actor-Critic-Boss) se construyen **en el directo**.
