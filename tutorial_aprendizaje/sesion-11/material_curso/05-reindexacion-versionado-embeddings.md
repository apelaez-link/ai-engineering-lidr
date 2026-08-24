# Lección 5 — Reindexación y versionado de embeddings (17 min)

> Notas fieles (Antonio Pérez). Resumen didáctico, no transcripción.

## El fallo que no da error

Toda la calidad de las lecciones anteriores descansa en una premisa que rara vez se
cuestiona: que los vectores del índice **siguen representando** lo que dicen los documentos y
que **todos viven en el mismo espacio**. Esa premisa se erosiona sola (llegan documentos
nuevos, se corrigen antiguos, aparece un modelo mejor) y lo hace de la peor forma: **sin lanzar
un error**. Dos formas de pudrirse:
- **Deriva de contenido**: se corrige una cifra en el documento, pero el vector almacenado
  sigue siendo el del texto viejo. La búsqueda recupera "40h" cuando ya dice 60 → atribución
  falsa que no es culpa del modelo, sino del índice.
- **Mezcla de versiones** (más insidiosa): reembebes media colección con un modelo nuevo y
  dejas la otra mitad con el viejo. La similitud coseno entre un vector del modelo A y uno del
  B **no significa nada** (son espacios distintos), pero la BBDD los compara igual y devuelve
  un número plausible. Recuperación **silenciosamente rota**.

El coste de equivocarse no es una caída visible: es una **degradación invisible** que
descubres meses después por una queja.

## Versionar el índice: cada vector sabe cómo se hizo
Defensa contra la mezcla: cada vector graba **cómo se produjo** y las consultas **nunca cruzan
versiones**. "El mismo proceso" es más que el mismo modelo: es **modelo + dimensión +
normalización + config de preprocesado (chunking/limpieza)**. Se guarda una `key`
(`model:dims:normalized:preprocessing_id`) en una columna `embedding_version`, y toda consulta
la filtra:

```sql
WHERE embedding_version = :current_version
ORDER BY embedding <=> :query_vector
```

Ese `WHERE` **no es una optimización, es una garantía de corrección**: sin él, una migración a
medias contamina cada búsqueda.

## Cuándo y cómo reindexar
Regla: **¿cambió el documento o cambió el proceso?**
- **Incremental** (documento nuevo/corregido): barato, el caso común. Detectas obsolescencia
  con un **hash del contenido** guardado junto al chunk (si el hash actual ≠ el embebido, el
  vector está stale). Reutiliza el pipeline de ingesta existente. **Solo válido dentro de una
  versión** (insertar chunks nuevos junto a viejos de otra versión = la mezcla que evitamos).
- **Migración de versión** (cambia modelo/dimensión/chunking): reembeber **todo**, caro y poco
  frecuente.

## Migrar: nunca a medias (blue/green)
Construir el índice nuevo **al lado** del viejo, verificarlo y cambiar **de golpe**:
`build_shadow_index → verify_shadow_index → promote_active_version (atómico) → drop_old`.
Mientras se construye el sombra, las consultas siguen en la versión activa (el usuario no nota
nada). El cambio es **un paso atómico**; no existe instante en que las dos se mezclen. Si la
verificación falla (faltan docs, dimensiones no cuadran, consultas de prueba absurdas), se
**descarta** y no pasa nada. **Verificar antes de promover no es opcional**: si no, puedes
sustituir un índice bueno por uno roto en un solo paso.

## Trade-offs honestos
- El incremental es barato y una **trampa fuera de su versión** (usarlo cuando cambió el
  modelo = mezcla de versiones).
- Migrar cuesta dinero/tiempo (tantas llamadas como chunks + el sombra duplica espacio) → se
  planifica, no es rutina.
- La detección de obsolescencia es tan buena como tu **captura de cambios**: si un presupuesto
  se modifica en un sistema externo y nadie avisa, el hash no lo descubre → hace falta
  sincronización o rehasheo periódico.
- **Saltarse el versionado parece gratis hasta que no lo es**: "nunca cambiaremos de modelo" es
  de las frases más caras de un RAG. La columna `embedding_version` es un seguro baratísimo
  contra un fallo invisible carísimo — ponla desde el principio aunque solo tengas una versión.
- Reindexar por **calendario** malgasta (reembebe lo que no cambió) o se queda corto → átalo a
  **eventos de cambio**, no a un reloj.

## Conexión con nuestra entrega (S11)
Es la lección más "de producción" y **fuera del alcance de nuestro entregable** (no tocamos el
esquema de la S8). Pero es un aviso directo para el **Proyecto Final**: si al ingerir las
ordenanzas/IRIS versionas el índice (`embedding_version`) y guardas un hash del contenido,
te ahorras la contaminación silenciosa el día que cambies de modelo de embeddings. Anotado.
