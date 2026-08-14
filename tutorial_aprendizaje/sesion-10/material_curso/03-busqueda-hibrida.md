# Lección 3 — Búsqueda híbrida (23 min)

> Notas fieles de la lección (Antonio Pérez). Resumen didáctico, no transcripción.

## El problema

Consulta: "integración de pagos con **Stripe**, con suscripciones y webhooks de
facturación". La búsqueda semántica devuelve proyectos con pasarelas de pago genéricas —
todos del campo semántico correcto. Pero el presupuesto que integró **exactamente Stripe**
hace año y medio (oro puro para estimar) aparece en la **posición 14**. ¿Por qué? Para el
embedding, "Stripe" ≈ "pasarela de pago": el nombre propio, el término exacto que
distingue el documento perfecto de los parecidos, **se diluye** en el vector. La búsqueda
semántica es **miope para lo literal** — y eso lo tenía resuelto la generación anterior de
búsqueda: el **matching exacto de términos**. La híbrida consiste en **no elegir**:
ejecutar ambas y fusionar.

## Dos familias, dos puntos ciegos

- **Léxica** (buscadores clásicos): opera sobre términos literales; palabras raras
  discriminan mucho. **No entiende paráfrasis** ("cobros recurrentes" ≠ "suscripciones"
  para ella).
- **Semántica**: opera sobre significado; cruza paráfrasis sin esfuerzo. **Diluye lo
  literal** (nombres, siglas, versiones, códigos: Stripe, SAP, ISO 27001, PostGIS).

En estimación conviven ambos tipos de consulta, a menudo en la **misma** consulta → no
elegir mejor entre familias: **dejar de elegir**.

## Full-text en PostgreSQL (la pieza que ya tienes)

Si los vectores viven en Postgres, **no metas Elasticsearch todavía**: Postgres trae
full-text maduro → cero infraestructura nueva, cero sincronización, las dos búsquedas a
una consulta SQL de distancia.

- **`tsvector`**: el texto tokenizado, en minúsculas, sin stopwords y con *stemming* (las
  raíces colapsan: "integraciones/integración/integrar" → misma raíz). Depende del
  **idioma** → config `'spanish'` para corpus en español (los términos que el diccionario
  no reconoce, "Stripe"/"webhook", pasan casi intactos = justo lo que buscamos).
- **`tsquery`**: la consulta con la misma normalización. `websearch_to_tsquery` acepta
  sintaxis natural de buscador y tolera entradas imperfectas → la opción sensata para
  texto libre de usuario.
- **Índice GIN** (índice invertido: de término → documentos) + `ts_rank` para puntuar.
- Se monta con una **columna generada** (Postgres mantiene el `tsvector` sincronizado sin
  triggers) + su índice GIN.

```sql
ALTER TABLE budget_chunks
  ADD COLUMN content_tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('spanish', content)) STORED;
CREATE INDEX ix_budget_chunks_content_tsv ON budget_chunks USING gin (content_tsv);
```

Dos honestidades: (1) `ts_rank` **no es BM25** (el estándar de facto), es algo más tosco;
hay extensiones con BM25, pero para un corpus de empresa la diferencia es ruido frente a
tener rama léxica vs no tenerla. (2) Elasticsearch sigue teniendo su sitio (corpus
enormes, analizadores custom, búsqueda difusa) — la posición es "no añadas un segundo
almacén hasta que el primero se te quede pequeño".

## El problema de juntar dos rankings

La distancia coseno y `ts_rank` viven en **escalas incomparables** → sumarlas es sumar
metros con kilos. Normalizar y pesar "funciona en la demo y se rompe en producción": la
distribución cambia con cada consulta, y mantener la calibración es trabajo permanente que
nadie pidió. **Solución elegante: ignorar las puntuaciones y usar solo las posiciones.**

## Reciprocal Rank Fusion (RRF)

```
rrf_score(d) = Σ_listas  1 / (k + rank_i(d))        (rank 1-based, k≈60)
```

Con k=60: un doc 2º en semántica y 5º en léxica → 1/62 + 1/65 ≈ 0,0315; un doc 1º en
semántica pero ausente en léxica → 1/61 ≈ 0,0164. **El que ambas consideran bueno supera
al campeón de una sola**: RRF premia el **consenso**. Para el presupuesto de Stripe, ese
es el rescate exacto (la léxica lo sube por el término, la semántica lo mantiene digno por
el tema, la fusión lo sube al top). La **k** es el único mando: pequeña → dominan las
primeras posiciones; grande → fusión más "democrática". 60 viene del paper original y es
robusto; tocarlo primero es optimización prematura.

Implementación = función pura que recibe una **lista de rankings** (no exactamente dos):
RRF no sabe cuántas fuentes fusiona → pieza de fusión **universal** del pipeline.

## Orquestación

Las dos ramas son consultas independientes a la misma BBDD → se lanzan en **paralelo**
(`asyncio.gather`): la latencia de la híbrida es la de la rama más lenta, no la suma.
Mismo **contrato** que cualquier búsqueda (entra consulta, sale lista ordenada de chunks)
→ cambiar vectorial↔híbrida es cambiar una pieza detrás de una config. Coste operativo
modesto: una consulta SQL extra (en paralelo), una columna generada que engorda la tabla,
un índice GIN. El coste real: una pieza más que entender/configurar/depurar.

## Cuándo gana la híbrida (y cuándo no)

- **Gana claro**: consultas con **identificadores exactos** (tecnologías, productos,
  siglas, normas, clientes) — pan de cada día en estimación; y consultas cortas/específicas.
- **Apenas mueve**: consultas puramente conceptuales y bien parafraseadas (la semántica ya
  bordaba). RRF degrada con elegancia: si ambos rankings coinciden, el fusionado también.
- **Vigilar**: idiomas mezclados (español con términos ingleses) → el `tsvector` procesa
  bien una parte; suele no ser grave (los términos técnicos ingleses funcionan como
  identificadores exactos), pero explica resultados desconcertantes.

Y como siempre: si compensa **en tu sistema, con tus consultas**, se mide contra una
referencia fija y deciden los números.

## Conexión con nuestra entrega (S10)

Nuestra implementación coincide casi punto por punto:
[`hybrid.py`](../../../app/embedding_pipeline/hybrid.py) (RRF puro k=60 sobre lista de
rankings + orquestador) y la columna generada + GIN en la
[migración 0002](../../../alembic/versions/0002_fulltext_tsvector.py).
**Diferencias conscientes:** (1) config `'english'` en vez de `'spanish'` (nuestro corpus
es inglés); (2) usamos `plainto_tsquery` convertido a **OR** en vez de
`websearch_to_tsquery`: con nuestros chunks cortos y consultas largas, el AND por defecto
dejaba la rama léxica **vacía** (bug que cazó la medición) → el OR hace que la léxica
contribuya. Y confirmamos empíricamente el matiz "cuándo NO gana": en nuestro corpus la
híbrida sin rerank incluso **empeoró** (0,80 vs 0,92) por ruido léxico — el reranking la
rescató.
