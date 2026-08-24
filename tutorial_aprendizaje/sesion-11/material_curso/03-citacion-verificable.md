# Lección 3 — Citación y atribución verificable (19 min)

> Notas fieles (Antonio Pérez). Resumen didáctico, no transcripción. **Es el núcleo del ejercicio.**

## Un identificador no es una citación

La estimación llega con ids de fragmentos: `["fin-2024-07#c3", ...]`. Buen principio, pero un
id que el humano no puede resolver ni el sistema verificar **no es una citación: es
decoración**. Da sensación de rigor ("mira, cita fuentes") sin lo único que importa: poder
**ir a la fuente y comprobar** que el número es de verdad. En estimaciones eso es la
diferencia entre "confía en mí" y "compruébalo tú mismo".

## Qué hace verificable a una citación (3 propiedades comprobables)
1. **Resuelve**: el id apunta a una fuente que existe y que estuvo en el contexto recuperado.
   Si el modelo cita algo que nunca estuvo en el contexto, cuelga del vacío.
2. **Localiza**: no apunta a un documento de 40 páginas, sino a la **línea concreta** que
   respalda la afirmación ("proyecto X (2024), línea: Módulo de pagos (Stripe), 40h").
3. **Es trazable hasta el origen**: hay un camino, del número al presupuesto original, que
   cualquiera con permiso puede recorrer (idealmente con un clic).

## Del id a la citación resoluble
Se proyecta la metadata del chunk en una `Citation` legible: `chunk_id`, `document_id`,
`document_title` (con significado humano), `project_year`, `locator` (la línea exacta),
`char_span` (offsets, si se capturaron). **Dependencia honesta:** solo puedes citar **a nivel
de línea si capturaste el localizador en la ingesta**. Si no, lo máximo es citar a nivel de
documento. La citación verificable de línea **no se decide al generar: se habilita antes**, en
cómo guardaste tus fuentes.

## Integridad referencial: ninguna cita colgante
Los modelos, aun instruidos, a veces inventan un id con buena pinta que nunca estuvo. Una
**cita colgante** es el fallo más peligroso porque **tiene el mismo aspecto que una legítima**.
Por eso NO se confía al modelo: se **verifica en código** tras generar (recorrer las líneas,
comprobar que cada `chunk_id` citado ∈ ids recuperados → separar `resolved` de `dangling`,
loguear los colgantes). Política ante una colgante (de más a menos estricta): rechazar y
reintentar / degradar el componente a "sin fuente verificable" / como mínimo, no dejar salir la
estimación. **Nunca ignorarla.** Ojo al límite: la integridad referencial es **estructural**
(la fuente existe y estuvo en contexto), **no semántica** (no confirma que la fuente *diga* lo
que se le atribuye) → eso es la lección 4.

## Formatos: estructura primero, presentación después
La citación estructurada es la **fuente de verdad**; inline / notas al pie / enlaces son
render encima. Compromisos: inline compacto pero ensucia y es ambiguo con varias fuentes;
notas al pie escalan pero obligan a saltar; enlaces = máxima verificabilidad pero abren
**confidencialidad** (los presupuestos suelen ser confidenciales). **Frontera de
responsabilidad:** el servicio IA emite `document_id` + `locator` (datos neutros), **no
URLs**; es el backend de negocio (Rails en la referencia) quien resuelve a un enlace **según
los permisos del usuario**. Si no tiene permiso, no se ofrece enlace y la cita se queda en su
forma textual verificable.

## Trade-offs honestos
- Citar a nivel de línea es una **promesa que se paga en la ingesta**. Sin localizador, cita a
  nivel de documento y sé honesto con la granularidad (una cita de línea inventada es peor).
- El enlace es la mejor verificación y la más frágil (rutas estables, permisos); un enlace que
  expone un confidencial hace más daño que no tenerlo.
- **Demasiada citación cansa** y deja de leerse; a nivel de **componente** suele ser el
  equilibrio, reservando el detalle línea a línea para auditar.

## Conexión con nuestra entrega (S11)
Es exactamente lo que implementamos: `SourceReference(chunk_id, document_id, evidence)` +
`verify_citations()` que separa **grounded / dangling / insufficient** (integridad
referencial), con log por `request_id`, y el caso colgante probado a propósito en
`tests/generation/test_verify.py`. Diferencia: nosotros usamos como `evidence` la cifra
verbatim ("Estimated hours: 160"); **no** capturamos `char_span`/`locator` a nivel de offset
(citamos a nivel de chunk trazable). El enlace con permisos (Rails) queda fuera de alcance.
