# 02 — Auditoría e inventario de datos empresariales

> Material del curso LIDR · AI Engineering · Sesión 6 (Antonio Pérez). (≈27 min)

La decisión está tomada (RAG + CAG residual). La tentación es escribir el primer loader. La
respuesta de esta lección: **construye el inventario antes de tocar nada.**

## El antipatrón: vectorizar primero, mirar después

El reflejo senior es ponerse a producir (sesgo a favor de la acción visible). En RAG ese
reflejo tiene **coste asimétrico**: los errores de saltarse la auditoría no aparecen el día 1,
aparecen el día 60. Tres modos de fallo, todos con la misma raíz (nadie miró los datos):

- **Mezcla silenciosa de versiones** — dos versiones contradictorias del mismo presupuesto, el
  RAG recupera la equivocada porque no hay metadato que las distinga.
- **Fuentes podridas** — documentos válidos en forma pero obsoletos en contenido; generan
  respuestas seguras a info incorrecta.
- **Gaps invisibles** — el sistema responde bien donde hay datos y **alucina plausible** donde
  no, porque nadie supo decirle qué categorías no cubre el corpus.

## Inventario de fuentes: el censo

Lista factual y verificable de qué fuentes existen. Campos mínimos por fuente: **nombre lógico**
(`historical_budgets`, no "los del Drive"), **localización física**, **owner técnico** (a quién
llamas si se cae), **owner de negocio** (a quién preguntas si el contenido es ambiguo),
**formato**, **volumen**, **método de acceso**, **periodicidad declarada** vs **observada**.

Esa última pareja revela problemas: una fuente "mensual" cuya última modificación es de hace 7
meses **no es mensual, es una fuente abandonada que alguien cree viva**. El censo se hace con un
script de inspección (factual) + campos manuales (subjetivos):

```python
@dataclass
class FilesystemSourceFacts:
    name: str; path: Path; file_count: int; total_size_mb: float
    latest_modified: datetime; formats_detected: set[str]

def inspect_filesystem_source(name: str, root: Path) -> FilesystemSourceFacts:
    """Solo hechos medibles desde disco; owner/sensibilidad los pone el humano."""
    files = [f for f in root.rglob("*") if f.is_file()]
    ...
```

## Evaluación de calidad por dimensiones

"Datos abundantes" ≠ "datos buenos". 100K registros inconsistentes son inservibles; 50 bien
estructurados son oro. Cuatro dimensiones (escala 1–5):

- **Completitud** — % de registros con todos los campos esperados.
- **Consistencia** — ¿el mismo concepto se representa igual? (`EUR` vs `euros` vs `€` es veneno
  para el retrieval: dos fragmentos del mismo cliente caen en regiones distintas del espacio vectorial).
- **Actualidad** — ¿qué fecha tiene el último dato? ¿se cumple la periodicidad?
- **Fiabilidad** — ¿autoritativa o derivada? Una hoja rellenada a mano < output de un sistema
  transaccional validado.

```python
@dataclass
class QualityAssessment:
    completeness: QualityScore; consistency: QualityScore
    actuality: QualityScore; reliability: QualityScore; notes: str

    @property
    def is_rag_ready(self) -> bool:
        # NO se promedia: una sola dimensión en 1-2 envenena el retrieval
        # aunque las otras sean excelentes. Cada una es condición NECESARIA.
        return all(s >= QualityScore.ACCEPTABLE for s in (...))
```

La regla `is_rag_ready` es deliberadamente estricta: `completeness=5, reliability=1` no es
"calidad 3", es "datos completos que pueden ser mentira" — lo peor para RAG.

## Linaje y *context erosion*

El **linaje** (de dónde vino el dato, qué lo transformó, quién lo tocó y cuándo) en RAG es
**condición de utilidad**, no buena práctica opcional. Cuando el RAG dice "este proyecto costó
80.000 €", el usuario necesita: ¿de qué documento viene? ¿cuándo? ¿qué autoridad tiene
(propuesta inicial / revisada / contrato firmado)?

La ***context erosion*** es la pérdida progresiva de ese contexto al mover el dato entre
sistemas: el contrato firmado el 15-mar sale con metadatos intactos → `presupuesto_v3.pdf` en
Drive → renombrado a `cliente_acme.pdf` → extraído a `.txt` → al llegar al RAG ya nadie sabe
si era propuesta o contrato. La información sigue ahí; el contexto que la hacía interpretable
**se evaporó**. El **catálogo** existe para preservar ese contexto por construcción.

## El catálogo mínimo viable: `data_catalog.yaml` versionado

Toda la info recolectada vive en un **YAML versionado en el repo**. Estructura plana por fuente:
`name`, `description`, `location`, `owner_technical/business`, `format`, `volume`, `refresh`
(declared / observed_last_update / observed_lag_days), `quality` (4 dimensiones),
`sensitivity` (contains_pii, pii_types, access_restrictions), `lineage` (upstream,
transformations), `decision` (**include / exclude / review**), `notes`.

El catálogo es un **artefacto de software**, no documentación muerta. Loader tipado con Pydantic:

```python
class CatalogSource(BaseModel):
    name: str; ...; decision: IngestionDecision; notes: Optional[str] = None
class DataCatalog(BaseModel):
    version: int; last_audited: str; sources: list[CatalogSource]
    def included_sources(self): return [s for s in self.sources if s.decision == "include"]
```

Tres ventajas de tenerlo como código tipado: **validación automática** (un PR que rompe el
schema no llega a prod), **acoplamiento explícito** (el pipeline itera `included_sources()` y
propaga `lineage`/`sensitivity` como metadatos de cada chunk), **trazabilidad** (el `git log`
del YAML es el historial de cómo evolucionó el corpus). Encima se monta un `generate_audit_report()`
que vuelca el catálogo a Markdown para stakeholders no técnicos (idealmente en CI).

## Trade-offs honestos

- **Catálogo formal (Atlan/DataHub/Collibra/Purview) vs YAML en repo** — las plataformas tienen
  sentido con cientos de fuentes y un equipo de governance. Para una/dos docenas de fuentes, el
  YAML versionado es lo correcto; migrar después es trivial, saltar directo a la plataforma da
  una herramienta cara y vacía.
- **Auditoría exhaustiva vs suficiente** — las fuentes son móviles; documenta solo las del
  primer release. El catálogo **crece con el proyecto, no antes que él**.
- **Excluir deliberadamente** — en RAG las fuentes malas no son ruido aleatorio (fácil de
  detectar) sino respuestas seguras a info incorrecta. Excluir con motivo registrado es
  **disciplina arquitectónica**, no desidia.
