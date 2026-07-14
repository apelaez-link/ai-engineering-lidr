# 04 — Chunking del proyecto: presupuestos JSON y transcripciones

> Material del curso LIDR · AI Engineering · Sesión 7 (Antonio Pérez). (≈26 min) · Aterriza el ejercicio.

El proyecto es **heterogéneo**: dos tipos de documento con propiedades radicalmente distintas.
Tratarlos con la misma estrategia deja calidad sobre la mesa.

- **Presupuestos JSON**: estructura jerárquica explícita, esquema predecible, **cada componente es una unidad lógica de negocio**.
- **Transcripciones de reuniones**: texto plano de 45 min, sin estructura, temas que se alternan y vuelven.

→ **Dos chunkers especializados** con una interfaz común, no un genérico con condicionales. El
ejercicio pre-sesión pide el **`JSONStructuralChunker`**; el de transcripciones (`TopicSegmentationChunker`) se ve en el directo sobre la misma base.

## Por qué los splitters genéricos fallan con JSON

Pasar un presupuesto entero a `RecursiveCharacterTextSplitter`:
1. Corta en mitad de una clave (`"client_metadata": {"sector":` | `"finance"...`) → ni JSON válido ni prosa. El embedding es ruido.
2. Aunque el corte caiga bien, se **pierde la jerarquía padre-hijo**: un componente "OAuth backend" sin saber cliente/sector/año compite con cientos de "auth" irrelevantes.
3. Serializar a texto plano pierde la jerarquía que el JSON capturaba.

La estrategia correcta es **estructural**: respeta la unidad lógica = el **componente**.

## El chunker JSON estructural (tres decisiones)

**Decisión 1 — Granularidad: un componente = un chunk.** Coincide con la unidad de razonamiento del
dominio: cuando piden un OAuth backend, eso es lo que queremos recuperar.

**Decisión 2 — Contenido: texto legible + header contextual del padre.** El `text` que se embebe NO
es el JSON crudo, es:

```
[Project: Mobile banking API with OAuth 2.0 authentication and PSD2 compliance]
[Client sector: finance | Year: 2024 | Main tech: ruby_on_rails]

Component: OAuth 2.0 authentication backend
Description: Implementation of OAuth 2.0 flows with JWT-based session management...
Tech stack: ruby_on_rails, postgresql, redis
Complexity: high
Estimated hours: 120
```

Las dos líneas entre corchetes son **contextual chunk headers**: es la versión **estática y barata
de Contextual Retrieval** (usamos el contexto del padre que ya está en el JSON, sin llamar a un LLM).
Microsoft Azure documentó **+15–25 puntos** de accuracy de QA solo con esto.

**Decisión 3 — Metadata: campos filtrables que NO se embeben.** `budget_id`, `component_id`,
`client_sector`, `main_technology`, `year`, `complexity`, `estimated_hours`. Sirven para **filtrar**
(en la sesión 8 con pgvector: búsqueda vectorial + `WHERE client_sector='finance' AND year>=2024`) y
para devolver info estructurada sin parsear el texto.

**`chunk_id` trazable**: `{budget_id}::{component_id}` (p.ej. `BUD-2024-014::AUTH-001`) — para citar
fuentes, auditar e invalidar chunks cuando cambie el padre. **`token_count`** con
`tiktoken.encoding_for_model("text-embedding-3-small")` para detectar chunks anormalmente grandes.

> **NO trocear descripciones largas** (dice el enunciado): confía en la estructura del JSON, un
> componente cabe como chunk. Si una descripción es excepcional, es un **dato para discutir en el
> directo** — nuestro chunker lo registra con un `log.warning` (umbral 1000 tokens), no lo parte.

Nuestra implementación: [`app/embedding_pipeline/chunker.py`](../../../app/embedding_pipeline/chunker.py)
sigue exactamente este esqueleto (`_build_parent_context`, `_render_component_text`, `_build_metadata`),
sobre modelos Pydantic (`Budget`) en vez de dicts crudos, con logging structlog.

## Transcripciones (teoría, es del directo)

Splitter de carácter con 512 tokens destroza una transcripción (cortes arbitrarios a mitad de
intervención). La estrategia correcta es **topic-based segmentation**: embeber intervenciones
consecutivas, detectar dónde la similitud cae bajo un umbral (~0.55, calibrable) y cortar ahí →
chunks = bloques temáticos coherentes. Mismo patrón de tres decisiones (granularidad = bloque
temático, header con metadata de reunión, metadata temporal/hablante).

> Detalle elegante: para la **segmentación interna** se usa un modelo local barato
> (`all-MiniLM-L6-v2`, 384d) porque hay que embeber muchas oraciones rápido; el índice de búsqueda
> **final** sigue siendo `text-embedding-3-small`. **Distintas piezas del pipeline pueden usar
> distintos modelos** de forma legítima.

## Metadata enrichment: la palanca subestimada

Ambos chunkers enriquecen de tres formas: (1) **headers contextuales** dentro del texto embebido
(pesan en la geometría); (2) **metadata estructurada** fuera del texto (filtros SQL en la sesión 8);
(3) **IDs trazables** (operacionalmente críticos para citar/auditar/invalidar).

**Regla — ¿texto o metadata?** Si cambia el significado semántico para una consulta natural
("auth para fintech" → el sector distingue), va en el **texto**. Si es discreto y sirve para filtrar
(`year`, `complexity`), va en **metadata**. A veces en ambos (el sector): no es redundancia
injustificada, cada copia cumple un rol.

## Composición en el servicio IA

Con dos tipos, un `document_type` en el body enruta al chunker correcto (routing explícito por
payload, más simple y auditable que la detección automática = agentic chunking). El backend de
negocio (Rails o el stack que sea) solo hace un POST REST; **qué chunker se aplica es decisión
interna del servicio IA**, no contrato con el backend.
