# 03 — Pipeline de extracción multi-formato

> Material del curso LIDR · AI Engineering · Sesión 6 (Antonio Pérez). (≈25 min)

Con el catálogo cerrado, toca convertir el contenido físico de cada fuente en texto procesable.
El Proyecto 2 tiene cinco familias de formato: **JSON** (presupuestos), **TXT** (transcripciones),
**XLSX** (tarifarios), **DOCX** (plantillas) y **PDF** (contratos). Cada uno trae su maldición.

La tentación: instalar `unstructured`, llamar a `partition()` y darlo por resuelto. Correcto a
corto plazo, incorrecto a medio: `hi_res` es lento/caro, y delegar todo a una librería sin
arquitectura es cómo se construyen pipelines que nadie entiende dos meses después. El patrón
opuesto: **cada formato con su herramienta, todo confluye en un contrato común.**

## El contrato común: el `Document` canónico

Antes de elegir parser, define **qué produce `ingest/` para el resto del servicio**. La respuesta
es un objeto canónico (aparece como `Document`/`Chunk`/`Passage` en la literatura) con dos campos
esenciales: **contenido** + **metadatos**.

```python
class DocumentMetadata(BaseModel):
    # Los 3 primeros vienen del catálogo, obligatorios para todo Document:
    source_name: str          # casa con una entrada de data_catalog.yaml
    source_location: str
    ingested_at: datetime
    # El resto los rellena el parser cuando el formato lo permite:
    document_id: str
    document_title: Optional[str] = None
    document_created_at: Optional[datetime] = None
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    contains_pii: bool = False
    extra: dict = Field(default_factory=dict)   # válvula de escape consciente

class Document(BaseModel):
    content: str
    metadata: DocumentMetadata
```

Dos virtudes: **homogeneidad downstream** (el chunker no sabe si viene de un PDF escaneado o un
JSON) y **trazabilidad por construcción** (cada doc sabe su fuente, su sitio y, cuando se puede,
su página/sección — eso llega hasta la cita final al usuario).

## Arquitectura modular: `loaders → parsers → normalizers`

```
ingest/
├── loaders/      # CÓMO llego al fichero (filesystem, drive, http, s3). Entrega bytes.
├── parsers/      # QUÉ hay dentro (json, pdf, docx, xlsx, txt). Representación intermedia.
├── normalizers/  # CÓMO lo convierto al Document canónico.
├── catalog.py    # loader del data_catalog.yaml
└── orchestrator.py  # pega todo → Document[]
```

¿Por qué **tres** capas y no dos (parser → Document directamente)? **Testabilidad.** Los parsers
son lógica compleja con librerías pesadas; testearlos contra el contrato canónico obligaría a
rellenar metadatos del catálogo en cada test. Separar la normalización permite testear parsers
contra su representación intermedia (fácil de mockear) y normalizers contra el contrato.

## Estrategias por formato

- **JSON** (fácil, ya estructurado) — no hay que extraer texto sino **decidir la representación
  textual**. `json.dumps` entero → embeddings ruidosos (mezcla claves técnicas y valores).
  Mejor: **renderizar a markdown estructurado** (claves importantes → títulos, valores → prosa).
- **TXT** (trampa) — las transcripciones no son homogéneas: las de 2024+ traen
  `[hh:mm:ss] Speaker:`, las antiguas no. Tratarlas como bolsa de texto pierde **quién dijo qué**.
  Parser que detecta formato → turnos con metadatos `speaker`/`timestamp`.
- **XLSX** (el más traicionero) — parece tabular pero rara vez lo es: celdas combinadas, fórmulas,
  múltiples tablas, hojas ocultas, formato condicional. Regla: tabla pura → markdown table;
  estructura compleja → fuera del corpus o conversión manual previa.
- **DOCX** (amable) — `python-docx` recorre párrafos, tablas y headings con API limpia y
  estructura semántica explícita. Emite **un `Document` por sección** con el heading como
  `section_title` (el RAG recupera la sección concreta, no la propuesta entera).
- **PDF** (el infierno: formato de presentación, no de contenido). Tres opciones:
  `pypdf`/`pdfplumber` (texto plano, rápido, pierde tablas) · `pymupdf` (mejor layout, PDF
  digital limpio) · `unstructured` con `hi_res` (visión por ordenador para tablas/OCR; lo más
  lento y caro). **Regla del Proyecto 2:** `pypdf` por defecto, `hi_res` solo si el PDF tiene
  tablas o es escaneado — decisión tomada **una vez por fuente en el catálogo**, no por documento.

## `unstructured` como navaja suiza (y sus costes)

`partition()` detecta formato y devuelve `Element` heterogéneos. Ventajas reales (interface
único, 20+ formatos, buena detección). Costes de frente: **peso** (`unstructured[all-docs]` mete
cientos de MB: Tesseract, modelos, PyTorch), **latencia/coste** (`hi_res` un orden de magnitud
más lento), **opacidad** (depurar una tabla mal detectada es difícil: lo decide una red neuronal).
**Recomendación:** parsers nativos para formatos predecibles (JSON, TXT, XLSX simple, DOCX),
`unstructured` reservado para PDF cuando lo necesita y como fallback de formatos exóticos.

## Propagación de metadatos (fuente triple)

El orquestador combina: **catálogo** (lo que se sabe antes de tocar el doc: source_name, owner,
PII, decisión), **parser** (título, autor, página, sección), **pipeline** (`ingested_at`, versión
del parser, strategy usada).

```python
def ingest_source(source, loader, parsers) -> list[Document]:
    if source.decision != IngestionDecision.INCLUDE: return []   # respeta el catálogo
    parser = parsers.get(source.format)
    documents = []
    for file_ref in loader.list_files(source.location):
        for doc in parser.parse(loader.read(file_ref), source_hint=file_ref.path):
            # metadatos del catálogo DESPUÉS del parser: si un parser falsea
            # source_name, el orquestador lo sobrescribe. Defensa en profundidad.
            doc.metadata.source_name = source.name
            doc.metadata.contains_pii = source.sensitivity.contains_pii
            documents.append(doc)
    return documents
```

Detalles: `Parser` es un **`Protocol`** (structural typing, no herencia) → más flexible y
testeable; el orquestador respeta `decision` (una fuente `exclude`/`review` no se procesa).

## Trade-offs honestos

- **Parsers nativos vs `unstructured` universal** — cuenta los formatos del catálogo: <5–6 bien
  entendidos → nativos (rápidos, baratos, depurables); más o impredecibles → `unstructured`.
- **`hi_res` vs `fast` en PDF** — `hi_res` para todo "por seguridad" puede tardar/costar 20× sobre
  los 90 PDFs que son texto digital limpio. Clasifica los PDF en el catálogo (digital / con tablas
  / escaneado): trabajo manual de una vez, ahorro continuo.
- **Pérdida estructural aceptable** — decide **conscientemente** qué pierdes (imágenes DOCX,
  comentarios, anotaciones PDF). Para estimación es ruido; para revisión legal sería crítico. No
  es aceptable perder estructura **por descuido** en lugar de por diseño.
