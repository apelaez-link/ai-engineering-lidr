# 01 — De interfaz conversacional a interfaz de producto

> Material del curso LIDR · AI Engineering · Sesión 4 (Antonio Pérez). (≈19 min)

## El problema del chat
Dos usuarios estiman el mismo proyecto: un PM senior escribe un brief de 12 líneas y recibe algo útil; un Head of Sales escribe "estimar un CRM para una pyme" y recibe una respuesta vaga. **Mismo modelo, mismo system prompt, resultados radicalmente distintos.** El problema no es el modelo: es que **hemos delegado el prompting al usuario** y la calidad del producto depende de algo que no controlamos. Eso no es un producto, es una herramienta para usuarios avanzados.

## El chat es un default, no una decisión de diseño
Aparece un widget de chat no porque sea la mejor interfaz, sino porque lo vimos en ChatGPT. Amelia Wattenberger (*Why Chatbots Are Not the Future*): la información sobre **qué pedir y cómo** se puede "hornear en la interfaz" en lugar de cargarla en cada usuario. Karpathy (*Software Is Changing Again*): los productos IA que funcionan son de **autonomía parcial** con UI cuidada (Cursor, Perplexity, Linear AI), no chats. El chat puro solo gana cuando el espacio es genuinamente abierto y exploratorio.

## ¿Dónde vive el prompt?
- **Arquitectura de chat:** el prompt vive en el textarea del frontend; lo escribe el usuario; el backend es un proxy.
- **Arquitectura de producto:** el prompt vive en el **backend**; el usuario solo aporta **parámetros** (tipo de proyecto, nivel de detalle, formato). El backend los inyecta en una plantilla versionada.

Consecuencias de tener el prompt en el backend: lo **versionas** (deploy para todos a la vez), lo **testeas** (es código), lo **optimizas por coste** (routing de modelos), y le **quitas la responsabilidad al usuario**. *El prompt es un artefacto de software, no un mensaje.*

## El espectro de interfaces (no es binario)
1. **Chat puro** (ChatGPT) — problema abierto/exploratorio.
2. **Chat con parámetros** (Perplexity con modos) — conversacional + parámetros explícitos.
3. **Formulario o acción** (Linear AI, Cursor) — sin textarea; botones y selectores; el prompt está abstraído.
4. **UI generativa** (Vercel AI SDK) — el LLM elige qué componente renderizar.

La pregunta no es "¿chat sí o no?" sino "¿dónde encaja esta feature?". Depende de cuánta variabilidad legítima hay, cuánta consistencia necesitas y cuánto puedes enseñar desde la interfaz. **El estimator pertenece al tercer cuadrante (formulario):** salida consistente, parámetros finitos, el usuario no debería tener que promptear bien.

## Qué significa para el estimator
El formulario captura **parámetros** (no el prompt). Se mapean a un objeto tipado (`EstimationRequest` con `description`, `project_type`, `detail_level`, `output_format`). Una plantilla los inyecta. El LLM recibe siempre la misma estructura, solo cambian los valores. Tres consecuencias: misma calidad para mismos parámetros; mejoras del prompt que llegan a todos al instante; el problema se parte en piezas que sabes resolver (schema, endpoint, validación, test), con la "magia" del LLM contenida en una sola llamada al final.

> La salida **sigue siendo texto libre** por ahora. Estructurarla con JSON Schema es la capa siguiente (lección 03).

## Recursos
- Amelia Wattenberger — *Why Chatbots Are Not the Future*
- Vercel — *AI SDK 3.0 with Generative UI*; Nielsen Norman — *Generative UI*
- Andrej Karpathy — *Software Is Changing (Again)* (vídeo)
