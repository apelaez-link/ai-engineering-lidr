# Lección 5 — Multi-índice y routing (19 min)

> Notas fieles (Antonio Pérez). **Fuera del alcance del ejercicio de la S10.** Resumen didáctico.

## El problema: un corpus que se vuelve heterogéneo

Los RAG reales engordan. El sistema ya guarda **tres familias** de documentos: presupuestos
(estructurados, telegráficos), transcripciones (lenguaje oral, divagante) y documentación
técnica (densa, de referencia). Ante "¿cuánto costó la integración con SAP?", el documento
que responde es un **presupuesto**, pero un índice único devuelve un top-5 contaminado con
transcripciones donde alguien habló de SAP y docs técnicas de conectores. El índice único
responde "¿qué se parece?" cuando la pregunta era "¿qué **presupuesto** se parece?".

## Por qué el índice único se degrada con la mezcla

- **Texturas semánticas distintas**: transcripción difusa vs presupuesto denso no se
  embeben igual; las distancias no son comparables en utilidad.
- **El tipo dominante inunda**: si hay 10× más chunks de transcripciones, el top-k tendrá
  la proporción que dicta el **volumen**, no la utilidad.
- **Cada familia quiere su preprocesamiento** (chunking por turnos vs por partidas vs por
  secciones) → un índice único fuerza un chunking de compromiso mediocre para todos.
- **La operación sufre**: reindexar transcripciones no debería tocar presupuestos.

Respuesta: **particionar** en colecciones especializadas.

## Particionar en PostgreSQL

- **Opción A — columna discriminadora** (`document_type` + `WHERE`): menor fricción; sirve
  si las familias **comparten esquema** y muchas consultas quieren buscar en todas.
- **Opción B — una tabla por familia** (`budget_chunks`, `transcript_chunks`…): más piezas;
  a cambio, cada una con su esquema, su índice HNSW sobre población homogénea, y reindexar
  una es local. **Regla**: si los **esquemas de metadatos divergen** → tablas separadas; si
  son variaciones de lo mismo → columna discriminadora. Los metadatos son la confesión del
  diseño (columnas NULL para una familia = son entidades distintas a disgusto).

## El router: quién decide dónde buscar (jerarquía de coste)

- **Nivel 0 — no tener router**: muchas consultas llegan con destino implícito. El flujo de
  estimación **siempre** busca presupuestos → capturarlo en el **contrato de la API**
  (parámetro de colección o endpoints distintos). Gratis, determinista, trazable. *"¿De
  verdad el servicio IA tiene que adivinar lo que el backend ya sabe?"*
- **Nivel 1 — reglas deterministas**: patrones de vocabulario ("¿cuánto costó…?" →
  presupuestos; "¿qué dijo el cliente…?" → transcripciones). Frágiles pero gratis y
  transparentes; buen primer filtro.
- **Nivel 2 — LLM clasificador**: para lo que las reglas no resuelven. Esquema cerrado
  (`StrEnum` de colecciones → el modelo no inventa una que no existe), **salida = lista de
  destinos** (no un destino con confianza 0,55: si duda, busca en ambas), campo `reason`
  auditable. Modelo pequeño.
- **Fallback honesto**: si nadie decide, **buscar en todo** (en paralelo → latencia de la
  más lenta). Degradación elegante: en el peor caso se comporta como el índice único —
  nunca peor.

## Combinar colecciones (con cuidado)

Las puntuaciones de colecciones distintas **no son comparables** (cada una su textura) →
fusión por **posiciones** o por **cuotas**, nunca por puntuación cruda. Muchas veces la
respuesta correcta es **no fusionar**: presentar agrupado por procedencia ("esto dicen los
presupuestos; esto se habló en reuniones"), porque el consumidor hace cosas distintas con
cada familia. Cada chunk viaja con su **etiqueta de procedencia** (permite atribuir/auditar).

## La semilla de algo más grande

El patrón "un coordinador examina una petición y la delega en el especialista adecuado" es
el **embrión de los sistemas con agentes**. Nuestro router es una clasificación acotada
(esquema cerrado, sin razonamiento abierto ni herramientas); esa contención es deliberada,
pero el patrón mental se reutilizará ampliado más adelante.

## Cuándo NO particionar

Si el corpus es funcionalmente homogéneo; si una colección concentraría el 95% de las
consultas (el router sería un peaje que casi siempre da la misma respuesta); "para cuando
crezcamos" (deuda contra una necesidad hipotética). **Señal legítima**: resultados de una
familia contaminando consultas de otra, de forma recurrente y **medible**.
