# 01 — Integración de contexto dinámico desde fuentes externas

> Material del curso LIDR · AI Engineering · Sesión 5 (Antonio Pérez). (≈27 min)

Hasta ahora el contexto era **estático** (vive en código: templates Jinja2, ejemplos hardcoded, parámetros tipados): predecible, versionable, testeable. El **contexto dinámico** se obtiene en runtime desde sistemas externos (ficheros del usuario, web, BBDD). Tres reglas a interiorizar:

1. **Es input, no programa** — delimítalo en el prompt y nunca dejes que se interprete como instrucciones (riesgo de prompt injection).
2. **Tiene coste real por petición** — se reincluye en cada llamada (a diferencia del estático con token caching). Un PDF de 30 páginas por turno duplica el coste de la sesión.
3. **Introduce latencia que el usuario nota** — PDF 1-3 s, búsqueda web 2-5 s, BBDD otro round-trip.

## 1. Archivos adjuntos — dos caminos
- **Camino A (multimodal directo):** subes el PDF a la **Files API** (Anthropic/OpenAI) y lo referencias en el bloque de contenido. El modelo ve diagramas, cero código de extracción, latencia de carga una sola vez (el file_id se reusa). Pegas: **lock-in** al proveedor multimodal, más tokens, menos control (todo o nada).
- **Camino B (extracción local):** extraes texto en tu servicio antes de la llamada (`pypdf`/`PyMuPDF`; `Docling`/`MarkItDown` para layout complejo → markdown; `python-docx` para Word) y envías solo texto, delimitado con tags:
```python
from pypdf import PdfReader
from io import BytesIO
def extract_text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    return "\n\n".join(f"--- Page {i} ---\n{p.extract_text() or ''}"
                       for i, p in enumerate(reader.pages, 1))
```
Ventajas: independiente del proveedor, control fino (filtrar páginas, redactar, recortar a budget), **prepara el terreno para el chunking de RAG**. Pegas: más código que mantener y pérdida de info visual. **No implementes los dos**; es decisión arquitectónica.

## 2. Búsqueda web
- **Herramienta nativa del proveedor** (`tools=[{"type":"web_search"}]`): simple, integrada con el razonamiento; pega: lock-in.
- **Servicio independiente** (Tavily/Exa/Firecrawl): resultados optimizados para LLM, independiente del proveedor; cableas el function calling tú.
- **SERP API** (SerpAPI/Serper): máximo control, máximo mantenimiento; rara vez compensa.
- **Cuándo activarla:** solo cuando el modelo no pueda responder con su conocimiento y la pregunta sea sensible al tiempo (versiones recientes, precios SaaS, benchmarks). Para lo demás (patrones, riesgos típicos) añade ruido.

## 3. Consultas a la BBDD del backend de negocio
- **NO** des al servicio IA acceso directo a la BBDD del negocio (acoplamiento de schema, permisos amplios, lógica duplicada).
- **SÍ**: expón una **herramienta** (function calling) cuya implementación hace una **llamada HTTP autenticada** al backend de negocio, que resuelve la consulta contra su BBDD aplicando sus reglas y devuelve un payload limpio:
```
LLM → Servicio IA (Python) → [HTTP auth] → Backend de negocio → su BBDD
```
Preserva las 3 capas: el servicio IA no conoce el schema, el backend mantiene su autoridad, la BBDD operacional se accede solo desde donde debe. (Cuando llegue RAG, la BBDD vectorial vive cerca del servicio IA — pero es la BBDD de *conocimiento*, no la operacional.)

## 4. Combinar y disciplinas
Los tres pueden coexistir en una petición vía **agentic loop** (el LLM razona, decide qué tool usar, recibe resultados, repite). Dos disciplinas obligatorias: **budget de tokens** (trunca/resume al superar) y **trazabilidad** (cada tool es un span; conéctalo con structlog/Logfire de la sesión 3).

**Regla operativa:** arranca con el **mínimo contexto necesario**, mide la calidad, y añade dinámico solo con evidencia de que el sistema lo necesita. "Más contexto" no es gratis: más tokens, más latencia, más superficie de injection, más complejidad de debugging.

## Recursos
- Anthropic — Files API, web search tool · OpenAI — Responses API (file_search, web_search)
- pypdf / PyMuPDF / Docling / MarkItDown / python-docx · Tavily / Exa / Firecrawl
