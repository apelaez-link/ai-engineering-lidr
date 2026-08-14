# Lección 4 — Expansión y descomposición de consultas (22 min)

> Notas fieles (Antonio Pérez). **Fuera del alcance del ejercicio de la S10** (que solo
> pide híbrida + reranking), pero parte de la teoría de la sesión. Resumen didáctico.

## El otro lado del mostrador: la consulta misma

Todas las mejoras anteriores actúan **después** de la consulta (índices, rankings,
filtros). Esta mira a la consulta. Dos problemas que ninguna mejora del lado de los
documentos arregla:
1. **La consulta multi-tema**: una transcripción de 40 min mezcla catálogo + app móvil +
   facturación + admin. Su embedding es el **promedio** de todo → un vector "cerca de todo
   y de nada" que recupera "proyectos grandes con muchas cosas" (lo peor para estimar, que
   se hace **por partidas**).
2. **La lotería de la formulación**: el cliente dice "que los comerciales vean sus números
   desde el móvil"; el presupuesto relevante decía "dashboard de KPIs responsive". Mismo
   concepto, vocabularios distintos. Los embeddings cruzan paráfrasis, pero **no son
   inmunes**: una formulación desafortunada recupera peor. Que la calidad dependa de la
   suerte al redactar es fragilidad inaceptable en producción.

## Dos técnicas que parecen una

- **Expansión (multi-query)**: genera **varias formulaciones de la MISMA intención** y
  busca con todas. Seguro contra la lotería: en vez de un boleto, juegas cuatro.
- **Descomposición**: parte una consulta que mezcla **varias intenciones** en
  sub-consultas independientes, una por tema. Cada una tiene un embedding **nítido** y
  recupera de su tema — como se estima de verdad.

La pregunta que las distingue: **¿la consulta pide una cosa que puede decirse de muchas
maneras, o muchas cosas dichas a la vez?** Aplicar la equivocada no es neutro (expandir
multi-tema = 4 boletos del sorteo equivocado; descomponer mono-tema = sub-temas artificiales
que recuperan ruido).

## Generar las variantes: LLM con la correa corta

Un LLM reformula/trocea con criterio, pero la versión de producción exige dos disciplinas:
- **Salida estructurada** (Pydantic/esquema), no texto libre a parsear con regex. Las
  sub-consultas son entrada de la siguiente etapa.
- **Instrucciones que acotan, no que inspiran**: el riesgo es que "mejore" demasiado
  (inventar requisitos no mencionados, traducir términos del dominio a sinónimos
  genéricos, fabricar 8 sub-consultas donde había 2 temas). Reglas tipo "máx 4
  sub-consultas", "cada una autocontenida", "**preserva los términos exactos del dominio,
  nunca los sustituyas por sinónimos**", "no añadas requisitos que la descripción no
  menciona". El límite (máx 4) vive **en el esquema** (garantiza) **y en las
  instrucciones** (orienta). Modelo **pequeño y rápido** (tarea humilde y acotada, en el
  camino crítico).

## Fusionar según el objetivo (el matiz clave)

- **Expansión** buscaba lo mismo → fusión que **premia el consenso** (estilo RRF): flota
  el doc que todas las formulaciones respetan.
- **Descomposición** buscaba cosas distintas → premiar consenso **sabotea** el objetivo
  (el tema con más presupuestos inundaría). Fusión que **garantiza cobertura por tema**:
  cuotas (los 2 mejores de cada sub-consulta) o **round-robin** intercalado. Con
  **deduplicación** (un presupuesto que cubre dos temas aparece en dos rankings; sin
  dedup consumiría dos plazas). Las N búsquedas en **paralelo** (`asyncio.gather`).

## El precio y cuándo no aplicar

Meten una **generación de LLM en el camino crítico, antes de buscar**: latencia (200 ms–1
s, el sumando más caro), tokens (calderilla × cada consulta), carga (N búsquedas). Mitigar:
modelo más pequeño que funcione, limitar a 3-4 variantes, **cachear** reformulaciones. Y
la mayor mitigación: **no aplicar cuando no toca** (consulta corta, nítida, mono-tema →
reformularla es pagar latencia para revolver un ranking que estaba bien). Heurística
humilde (longitud/estructura: transcripciones largas se descomponen; consultas cortas
pasan directas) + dejarlo en logs.

## Idea para llevarse

La consulta es **la mitad de la ecuación de relevancia**, y la que peor llega. Expandir
multiplica formulaciones y fusiona por consenso; descomponer separa intenciones y fusiona
garantizando cobertura. Ambas se aplican **con criterio, no por defecto**.
