# Lección 2 — Cómo saber si el reranking compensa: medición artesanal de relevancia (23 min)

> Notas fieles de la lección (Antonio Pérez). Resumen didáctico, no transcripción.

## "Parece que va mejor" no es un argumento

Añades reranking, lanzas tres consultas, "tienen mejor pinta" y cierras el ticket. Dos
semanas después alguien pregunta por qué cada estimación tarda medio segundo más y tu
respuesta ("la recuperación mejoró") no sobrevive a la siguiente pregunta: **¿cuánto?**
El objetivo de la lección: convertir "parece que va mejor" en *"la precisión subió de
0,48 a 0,80 a cambio de 250 ms por consulta"*. No hace falta framework ni equipo de
datos: **una tarde, criterio de dominio y una hoja de cálculo**. Eso es la **medición
artesanal**: pequeña, manual, y suficiente para la decisión que tienes delante.

## Por qué la intuición engaña midiendo relevancia

- **Consultas equivocadas**: a mano elegimos las fáciles (las que nosotros formularíamos
  bien); los usuarios escriben vagas, mezcladas, con su jerga.
- **Recordamos lo memorable, no lo representativo**: un rescate espectacular domina la
  percepción aunque en el resto no cambie nada.
- **Referencia que se mueve**: evaluar "a ojo" el martes vs el jueves = varas distintas.

Solución a los tres: **fijar de antemano un conjunto de consultas representativas con sus
respuestas correctas conocidas** y medir todas las configuraciones contra ese mismo
conjunto. Ese conjunto es el **golden set**.

## El golden set

Colección **pequeña** de consultas reales del dominio, cada una anotada a mano con los
documentos que de verdad son relevantes. En el proyecto: la consulta es la descripción de
un proyecto a estimar; la anotación es la lista de **presupuestos que un estimador
experimentado usaría de referencia** (no los "parecidos", los que usaría de verdad).

Tres decisiones (ninguna técnica):
- **Qué consultas**: cubrir el uso real, no el cómodo. Mezcla: 2-3 frecuentes/directas,
  un par **difíciles conocidas** (dominios colindantes tipo e-commerce/pagos), y ≥1 con
  **términos exactos** (tecnologías, siglas). Si el sistema ve transcripciones, alguna
  larga y desordenada.
- **Cuántas**: **entre 5 y 20**. El error que invalida la medición no es el tamaño, es
  que la muestra no se parezca al uso real. 5 representativas > 50 inventadas. Empieza
  pequeño (ampliar es trivial; tirar uno grande y malo, doloroso).
- **Quién anota y con qué criterio**: juicio de dominio (el estimador, no "quien sabe
  Python"). **Escribir el criterio en una frase** antes de anotar evita el desplazamiento
  silencioso. Relevancia en **binario** (relevante/no) — menos expresivo pero consistente.

## Precisión@k (la métrica de la servilleta)

Lo que importa son los **k primeros** que llegan al LLM. `precision@k` = de los k
devueltos, qué fracción es relevante según el golden set. Ejemplo: golden marca 4
relevantes; el sistema devuelve top-5 con 3 aciertos → **3/5 = 0,60**. Se promedia sobre
todas las consultas; ese promedio describe la configuración.

Matices: **elegir k con intención** (mide `precision@5` si pasas 5 docs al LLM, no
`precision@10`). La **exhaustividad (recall@k)** es el espejo ("de lo que valía, ¿cuánto
devolviste?"): si anotaste *todos* los relevantes (viable en corpus de empresa), es
gratis y detecta el relevante que no aparece. Métricas que premian el orden existen, pero
para decidir "¿entra la técnica?", precisión y recall sobre tus k reales bastan.

## La otra columna: latencia

Dos precauciones: **medir en caliente** (descartar la primera consulta tras arrancar —
paga costes fijos de carga) y quedarse con la **mediana** de 3-5 ejecuciones (resiste
picos; con muestras pequeñas la media se arrastra). Resultado = tabla: una fila por
config, columna de precisión, columna de latencia mediana.

## El arnés (poco glamuroso, a propósito)

- El golden set es un **archivo versionado** junto al código: cambiarlo debe pasar por
  revisión (cambiar la vara = cambiar el significado de todas las medidas anteriores).
- Un **script** recorre el golden set, ejecuta el pipeline y calcula las dos columnas.
- Vive en `scripts/`, **no** en las capas de la app: es herramienta de decisión puntual,
  no infraestructura (nada de endpoint/tests/abstracción). Convertirlo en "módulo de
  evaluación" prematuramente es exceso de ingeniería. La evaluación continua real (CI,
  histórico, métricas sobre generación) es otra pieza, más adelante.

## Marco de decisión: ganancia vs coste

Situar cada técnica en dos ejes: cuánta relevancia gana, cuánta latencia cuesta. La
lectura correcta usa el **denominador adecuado** (el presupuesto de latencia de la
experiencia completa): +255 ms sobre una generación de LLM de varios segundos es <5% y
convierte 2 de 5 docs de ruido en señal → obvio activarlo. La misma tabla en un
autocompletado de 300 ms → inasumible. **La técnica no es buena ni mala; es cara o barata
respecto a un presupuesto que fija el producto.**

Zona traicionera: **ganancia pequeña, coste pequeño**. El coste de una técnica no es solo
su latencia: es el modelo extra que operar, la dependencia que actualizar, el modo de
fallo nuevo. Una mejora de 0,02 rara vez paga ese peaje. La respuesta senior es **no
añadir la pieza** — y la tabla es lo que te deja decir "no" con fundamento.

## Límites (y por qué no pasa nada)

Un golden set de 10 consultas **no tiene potencia estadística**: diferencias de 0,05
pueden ser ruido de anotación → decidir solo con diferencias **grandes y consistentes**
(0,48→0,80). Arrastra el sesgo del anotador. Y **se detiene en la recuperación**: dice
qué llega al LLM, no qué hace el LLM con ello. Nada de esto la invalida: responde una
pregunta de diseño concreta con el rigor justo.

## Conexión con nuestra entrega (S10)

Es **exactamente** lo que montamos: golden set anotado a mano
([`golden_set.py`](../../../evals/retrieval/golden_set.py), 5 consultas con criterio y
rationale), `precision_at_k` puro
([`metrics.py`](../../../evals/retrieval/metrics.py)), runner que mide 4 configs con
latencia mediana de 3 ejecuciones ([`run.py`](../../../evals/retrieval/run.py)), y la
tabla ganancia-vs-coste que nos hizo decidir **NO** rerankear en este corpus (misma
precisión, 14× latencia). El script vive en `evals/`, no en la app — igual que recomienda
la lección.
