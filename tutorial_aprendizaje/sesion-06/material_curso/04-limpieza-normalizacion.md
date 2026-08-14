# 04 — Limpieza, normalización y validación de datos

> Material del curso LIDR · AI Engineering · Sesión 6 (Antonio Pérez). (≈28 min)

`ingest/` ya produce `Document`s que cumplen el contrato Pydantic. Pero eso es solo el
**contrato de forma**, no dice nada del **contrato de contenido**. Dos `Document`s pueden cumplir
el schema y ser radicalmente incompatibles para el RAG: `"ACME Corp."` vs `"Acme Corp"` (entidades
distintas para los embeddings, retrieval falla en silencio); `total_amount: -50000` (pasa la
validación de tipo, rompe el análisis); fechas `"15/03/2024"` y `"2024-03-15"` (ambas strings
válidas, radicalmente distintas para filtrar). El Pydantic es la primera línea; esta lección monta
la segunda.

## Cuatro familias de "suciedad"

- **Heterogeneidad de formato** — la misma cosa de N maneras (`EUR`/`eur`/`€`/`euros`). Veneno:
  los embeddings tratan cada variante como token distinto; dos fragmentos del mismo cliente caen
  lejos en el espacio vectorial.
- **Duplicados con divergencias** — el mismo registro dos veces con valores distintos (ERP dice
  `80000`, copia manual dice `82500`). El RAG recupera el que indexe primero → respuestas que
  dependen de un orden de procesamiento que nadie controla. Diagnosticar en prod lleva semanas
  porque parece "ruido del LLM".
- **Valores nulos disfrazados** — `"N/A"`, `"-"`, `"unknown"`, `"TBD"`, `"pendiente"`, cadena vacía.
  Técnicamente válidos, se vectorizan como contenido real y el RAG los presenta con autoridad.
- **Valores fuera de rango** — `total: -50000`, fin antes que inicio, % > 100. Rara vez se
  recuperan (los embeddings los aíslan), pero cuando se recuperan generan respuestas con confianza
  alta sobre absurdos — lo que más caro paga en credibilidad.

## Dónde colocar la capa de limpieza

**Lo que NO hay que hacer:** parchear en cada capa (el chunker detecta un vacío, el embedder un
duplicado…). Si la limpieza está repartida: las reglas dejan de ser auditables, los tests se
vuelven imposibles (mockear validaciones de otra capa), y no hay **un único punto** donde un
fallo pueda detener el pipeline.

La capa de limpieza es un **módulo separado**, con tests y garantías propias. Posición natural
(recordando `loaders → parsers → normalizers`): **entre parser y normalizer**. Para formatos
tabulares (los presupuestos JSON), la representación intermedia es un **DataFrame de pandas** y la
limpieza opera sobre él. Los no tabulares (PDF/DOCX/TXT) usan otras técnicas (regex, encoding,
longitud mínima, detección de placeholders) pero el caso que ilumina el patrón es el tabular.

## Limpieza con pandas

```python
NULL_PLACEHOLDERS = {"", "n/a", "na", "-", "--", "unknown", "tbd", "pendiente"}

def clean_budget_records(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    # 1. nulos disfrazados -> NaN real
    out["client_name"] = (out["client_name"].astype(str).str.strip().str.lower()
        .where(lambda s: ~s.isin(NULL_PLACEHOLDERS), other=pd.NA))
    # 2. normalizar moneda
    out["currency"] = out["currency"].str.lower().map(
        {"eur":"EUR","euros":"EUR","€":"EUR","usd":"USD","$":"USD"}).fillna(out["currency"])
    # 3. fechas y 4. números con coerción PERMISIVA (inválido -> NaN, no excepción)
    out["signed_at"] = pd.to_datetime(out["signed_at"], errors="coerce", utc=True)
    out["total_amount"] = pd.to_numeric(out["total_amount"], errors="coerce")
    # 5. dedup por hash de contenido: quedarse con la última versión por budget_id
    out = out.sort_values("signed_at").drop_duplicates(subset=["budget_id"], keep="last")
    return out
```

Tres detalles: cada paso es **estrechamente acotado** (testeable en aislamiento); el paso 5 ataca
"duplicados con divergencias" (la regla "quédate con el último" debe documentarse en el catálogo);
las coerciones **permisivas** (`errors="coerce"`) **separan limpieza de validación** (aquí
transformo lo que puedo; qué hacer con los NaN lo decide la validación). Esta función **no decide
nada**: deja vacíos, fueras de rango y `NaT`.

## Pandera como contrato de datos

Pandera es a los DataFrames lo que Pydantic a las instancias: valida **columna a columna y fila a
fila**, y al fallar devuelve un reporte detallado de **qué filas fallan y por qué**.

```python
class BudgetRecord(DataFrameModel):
    budget_id: Series[str] = Field(str_matches=r"^BUDGET-\d{4}-\d{4}$")
    client_name: Series[str] = Field(nullable=False, str_length={"min_value":2,"max_value":200})
    total_amount: Series[float] = Field(ge=0, le=10_000_000, nullable=False)
    currency: Series[str] = Field(isin=["EUR","USD","GBP"])
    signed_at: Series[pd.Timestamp] = Field(nullable=False, le=datetime.now(timezone.utc))
    status: Series[str] = Field(isin=["draft","signed","rejected"])

    class Config:
        strict = True       # rechaza columnas no declaradas (cambios silenciosos del parser)
        coerce = False      # la limpieza previa ya coercionó tipos

    @pa.dataframe_check
    def positive_amount_for_signed(cls, df):   # regla CROSS-COLUMN
        return ~((df["status"] == "signed") & (df["total_amount"] == 0))
```

Tres elementos: **checks de campo** (cada uno es un invariante de negocio; el patrón de
`budget_id` es un contrato con upstream), **checks cross-column** (`@pa.dataframe_check`, lo que
un Pydantic por-instancia no puede expresar), **config estricta**. El schema Pandera es el
equivalente para datos del `data_catalog.yaml` para fuentes: vive en git, cambia en un solo sitio.

## Estrategia de fallo: reparar / cuarentena / descartar

Política **explícita y documentada**, no implícita en el código:

- **Reparar** — fallo recuperable sin pérdida semántica (`"15/03/2024"` con `dayfirst=True`,
  `"euros"` → `"EUR"`). Sin intervención humana.
- **Cuarentena** — fallo grave pero el registro podría ser útil tras revisión (`client_name` nulo
  con el resto completo; `total` ligeramente sobre el límite). No entra al RAG; se preserva en
  tabla aparte con su motivo, para arbitraje humano. El limbo.
- **Descartar** — contaminación clara (`budget_id` que no cumple patrón, `total` negativo o ×100
  el límite). Se elimina con log, sin reserva.

```python
def validate_with_policy(df, schema) -> ValidationResult:
    try:
        valid = schema.validate(df, lazy=True)   # lazy: recoge TODOS los errores, no el 1º
        return ValidationResult(valid=valid, ...)
    except pa.errors.SchemaErrors as exc:
        failure_cases = exc.failure_cases
        # política por tipo de fallo: structural -> descartar; resto -> cuarentena
        ...
        return ValidationResult(valid=..., quarantined=..., discarded=...,
                                report={"failure_breakdown": ...})  # métricas para observabilidad
```

`lazy=True` es lo que permite la política diferenciada (sin él solo conoces el primer error). El
`report` deja métricas que alertan cuando una fuente empieza a degradarse, mucho antes de que
llegue al RAG.

## Trade-offs honestos

- **Pandera vs Great Expectations** — Pandera: ligera, declarativa, schema = clase Python en git,
  zero infra. GE: datadocs HTML, profiling, integración Airflow/Dagster, más expresiva pero
  pesada. Para el Proyecto 2 → Pandera. GE cuando escalas a docenas de pipelines con stakeholders
  no técnicos.
- **Strict en prod vs permisivo en dev** — el schema debe ser **estricto desde el día 1**; lo que
  se relaja es la **política ante fallos** (cuarentena en dev, descartar en prod), no el contrato.
- **Cuánto normalizar sin perder señal** — bisturí, no motosierra. Normaliza lo claramente
  accidental (mayúsculas en monedas, espacios, separadores de fecha); deja para después lo que
  podría borrar señal semántica (`Apple` empresa vs `apple` fruta).
