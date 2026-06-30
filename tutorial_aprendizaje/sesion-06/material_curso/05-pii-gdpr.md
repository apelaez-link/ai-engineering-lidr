# 05 — PII, anonimización y GDPR en el pipeline de ingest

> Material del curso LIDR · AI Engineering · Sesión 6 (Antonio Pérez). (≈28 min) · **Cierra el Módulo 3.**

El corpus ya pasó inventario, extracción y validación. Pero contiene, sin excepción, datos
sensibles: nombres de clientes, emails, teléfonos, identificadores internos, condiciones
contractuales. Intuición a desmontar: *"el control de acceso de la app ya protege esos datos"*.
Funciona en BBDD relacionales, **no en RAG**, y el motivo es **estructural**: una vez que un dato
sensible está en el espacio vectorial, está disponible para cualquier consulta semántica que se
le acerque. **La protección tiene que ocurrir antes del embedding.**

## El problema real: filtración semántica vía RAG

En relacional, el atacante necesita una query a la columna protegida; los permisos la bloquean.
En RAG el ataque es **indirecto**: preguntas en lenguaje natural → búsqueda semántica → chunks al
modelo. Si el chunk contiene el dato (literal), el modelo lo usa. **No hay permisos en el vector.**
Tres modos:

- **Directa** — "¿qué clientes nos contrataron migraciones cloud?" → enumera "Sabadell, Inditex,
  Repsol" porque están literal en los chunks. Trivial de explotar y de prevenir.
- **Por agregación** — cada query parece inocua; el atacante combina varias para reconstruir.
  Defenderse exige pensar en **superficie de información agregada**, no en chunks sueltos.
- **Por inferencia** — la más peligrosa, sobrevive a la anonimización ingenua: reemplazas
  `"Juan García, CEO de Acme"` por `"[PERSON], CEO de [ORG]"` pero el contexto (sector, fechas,
  importes, geografía) + metadatos sigue identificando. La defensa es reducir la **combinatoria
  de pistas**.

Ninguno requiere acceso admin: bastan credenciales legítimas y preguntas. Por eso la
anonimización va **antes del embedding**, no como filtro en la respuesta.

## Marco GDPR mínimo

- **Datos personales** — definición amplia: cualquier info que identifique directa o
  **indirectamente** a una persona. Las transcripciones son trivialmente PII; un presupuesto que
  combina sector+importe+fecha+geografía también puede serlo si reduce a un único cliente.
- **Anonimización vs pseudonimización** — anonimización **irreversible**: ni el operador recupera
  el original (deja de ser dato personal). Pseudonimización: sustitución por valor ficticio con
  **mapping reversible** guardado aparte (sigue siendo dato personal). Para RAG **suele ganar la
  pseudonimización** porque **preserva la coherencia semántica**: `"Juan García"` → siempre
  `"Carlos Martínez"` en todo el corpus, no `<PERSON>` (que destruye estructura).
- **Derecho al olvido (art. 17)** — en BBDD es un `DELETE`; en RAG es arquitectónico: los chunks
  están vectorizados y dispersos. Sin mapping explícito, eliminar es imposible.
- **Minimización** — solo los datos estrictamente necesarios. ¿Necesita el estimador los nombres
  **reales**? No: necesita patrones (sector, alcance, tecnologías, complejidad), no la identidad.
  Eso justifica pseudonimizar agresivamente: no perdemos nada útil, eliminamos un riesgo.

## Microsoft Presidio: detección + anonimización

`analyzer` detecta entidades y posiciones; `anonymizer` aplica una operación sobre ellas.

```python
# Motor NLP en ESPAÑOL (por defecto Presidio solo trae inglés)
nlp_config = {"nlp_engine_name":"spacy","models":[{"lang_code":"es","model_name":"es_core_news_md"}]}
nlp_engine = NlpEngineProvider(nlp_configuration=nlp_config).create_engine()
analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["es"])
anonymizer = AnonymizerEngine()

results = analyzer.analyze(text=text, language="es")  # RecognizerResult: start, end, entity_type, score
anonymized = anonymizer.anonymize(text=text, analyzer_results=results,
    operators={"DEFAULT": OperatorConfig("replace", {"new_value":"[REDACTED]"})})
```

Detalles del setup: **configurar el modelo spaCy español es obligatorio** (sin él, los falsos
negativos en `PERSON`/`LOCATION` se disparan sobre texto español). La operación `replace` con
`[REDACTED]` es la más simple y **la peor para RAG** (destruye estructura) — solo demuestra el flujo.

### Recognizers custom del dominio

Los default no conocen los identificadores propios. Para el Proyecto 2: **budget IDs**
(`BUDGET-YYYY-NNNN`, no PII estricto pero revela info comercial) y **códigos de cliente**
(`CLI-1042`, mapean 1-a-1 a clientes).

```python
budget_id_recognizer = PatternRecognizer(supported_entity="BUDGET_ID", supported_language="es",
    patterns=[Pattern(name="budget_id", regex=r"\bBUDGET-\d{4}-\d{4}\b", score=0.95)])
analyzer.registry.add_recognizer(budget_id_recognizer)
```

`score` es decisivo: cuando varios recognizers se solapan, Presidio se queda con el de mayor
score (patrones específicos altos 0.9–0.95, genéricos bajos 0.4–0.6). El `supported_entity` es la
etiqueta que decide qué generador usa la pseudonimización. Para nombres sin patrón regular
("Banco Sabadell") → diccionario explícito mantenido en el catálogo.

## Pseudonimización reversible con Faker + mapping table

La pieza arquitectónica clave: sustituir por valores ficticios **consistentes** (Faker) +
**mapping table** que registra cada sustitución para revertirla.

```python
class ConsistentPseudonymizer:
    def __init__(self, mapping_store, locale="es_ES"):
        self.faker = Faker(locale); self.store = mapping_store  # store ENCRIPTADO, aparte
        self.generators = {"PERSON": self.faker.name, "EMAIL_ADDRESS": self.faker.email,
            "ORGANIZATION": self.faker.company, "BUDGET_ID": lambda: f"BUDGET-{...}", ...}

    def get_or_create_pseudonym(self, original, entity_type, source_name) -> str:
        if (existing := self.store.lookup(original, entity_type)): return existing.pseudonym
        pseudonym = self.generators.get(entity_type, self.faker.word)()
        self.store.save(PseudonymMapping(original, pseudonym, entity_type, self._now_iso(), source_name))
        return pseudonym
```

Cuatro decisiones: **consistencia por valor original, no por chunk** (`"Juan García"` siempre al
mismo pseudónimo, o el retrieval vuelve a romperse como con la heterogeneidad de formato);
**generadores por tipo** (nombre→nombre, preserva la señal del campo); **mapping store separado y
encriptado** con su propio control de acceso (es la respuesta a un auditor GDPR); **se persiste
`source_name`** (responde "qué fuentes mencionan a esta persona" sin recorrer el índice).

Integración: al final del pipeline (tras la validación, antes del chunking), el orquestador mira
`metadata.contains_pii` (propagado del catálogo) y, si es `True`, pseudonimiza. El resto del
pipeline downstream no sabe nada de Presidio/Faker.

## Derecho al olvido en RAG: 5 pasos

1. Consultar la mapping store por el nombre → todos los pseudónimos asociados.
2. Buscar en el índice los chunks con esos pseudónimos.
3. Eliminar esos chunks del índice vectorial.
4. Eliminar las entradas del mapping (si reaparece, nuevo pseudónimo sin relación).
5. Registrar en audit log (demuestra cumplimiento en plazo).

Sin la mapping table, los pasos 1, 2 y 4 son **imposibles** → incumplimiento permanente del art.
17. Por eso la mapping table no es un detalle: **sostiene el cumplimiento**.

## Trade-offs honestos

- **Irreversible vs reversible** — `<PERSON>` no tiene mapping store que filtrar, pero degrada el
  retrieval (caídas del 15–25% en pruebas internas). Para sistemas con compromiso de calidad →
  pseudonimización reversible casi siempre. Irreversible solo para corpus "públicos por defecto".
- **Falsos positivos en español** — Presidio funciona peor en español: `es_core_news_md` etiqueta
  "Mar", "Sol", "Cruz", "Alba" como `PERSON`. Mitigaciones: subir el umbral de score (0.5→0.7),
  blacklist de palabras conocidas, NER customizado si el volumen lo justifica.
- **Impacto en embeddings** — la pseudonimización consistente preserva la mayor parte de la señal,
  pero introduce algo de ruido (un nombre real lleva micro-info que uno falso no). Para estimación
  es despreciable; para asistentes personales hay que cuantificarlo. Regla: pseudonimizar primero,
  medir con queries representativas, decidir caso por caso.

## Cierre del Módulo 3

Seis decisiones acumulativas: justificar CAG→RAG (L1) · catálogo versionado (L2) · `ingest/` con
`Document` canónico (L3) · limpieza+validación con Pandera (L4) · anonimización con Presidio +
mapping table (L5). El resultado no es código brillante: es **un corpus que sostendría una
auditoría seria** — cada decisión versionada, cada exclusión con motivo, cada dato sensible con
mapping reversible, cada invariante con un schema que lo hace cumplir. Ese es el estado mínimo
desde el que tiene sentido vectorizar. **A partir de la Sesión 7: embeddings, chunking, modelos.**
