# 02 — Estado del mercado de BBDD vectoriales (2026)

> Material del curso LIDR · AI Engineering · Sesión 8 (Antonio Pérez). (≈40 min)

El mapa del mercado y la justificación honesta de **por qué pgvector** para el proyecto — incluyendo
cuándo esa decisión dejaría de ser correcta. La pregunta "¿qué BBDD vectorial?" se contesta **por
proyecto**, no una vez para toda la carrera.

## Los cuatro ejes que importan

1. **Modelo operativo** — self-hosted (control total, pero updates/backups/on-call tuyos) vs managed
   (pagas por no pensar, menos control). No hay mejor universal; depende de la madurez del equipo.
2. **Escala práctica** — no "cuántos caben" sino con latencia/recall/coste aceptables. Rangos 2026:
   <10M cualquiera vale; 10–100M el campo se estrecha; >1B solo sistemas diseñados para esa escala.
3. **Funcionalidades nativas** — búsqueda híbrida, filtrado por metadata, multimodal, sharding
   multi-región: si no vienen de serie, son ingeniería real de construir y mantener.
4. **Modelo de coste** — factura + coste de operación (DevOps/on-call) + **coste de migración** (cambiar
   de BBDD vectorial en producción no es un fin de semana).

## Las cinco opciones

- **pgvector** — extensión de Postgres (tipo `vector` + operadores + índices HNSW/IVFFlat). No es una
  BBDD nueva: es Postgres haciendo más. Con HNSW compite con dedicados hasta ~10M vectores (y
  pgvectorscale+DiskANN sube el techo). Ventaja **única**: cruzar búsqueda vectorial con datos
  relacionales en **una query atómica ACID**. Techo: cuando el índice no cabe en `shared_buffers`.
- **Qdrant** (Rust, open-source) — velocidad pura + **filtrado por metadata de primera clase**. Sin
  joins ni transacciones sobre datos relacionales. Sweet spot: cientos de miles a decenas de millones.
- **Weaviate** — **búsqueda híbrida nativa** (vector + BM25) + módulos de vectorización. Más opinado
  (esquema de clases, GraphQL). Gana cuando la híbrida es el centro del producto.
- **Milvus** — diseñado para **escala extrema** (>1B, distribuido, GPU). Sobredimensionado por debajo
  de 100M (etcd, MinIO, varios servicios). Define el techo del open-source.
- **Pinecone** — totalmente gestionado, "zero ops". Coste con 3 componentes + mínimo $50/mes; la
  factura real suele ser 2.5–4× la estimación del calculator. Competitivo hasta ~10M; a industrias
  reguladas (soberanía de datos) ni entra.

Todas dan p50 de 5–50 ms hasta 10M vectores bien sintonizadas: el QPS de los benchmarks **no** es lo
que decide; deciden los cuatro ejes.

## Por qué pgvector para el proyecto (cuatro razones)

1. **Alineamiento con el stack** — el backend de negocio ya usa PostgreSQL; el servicio IA habla con
   el mismo Postgres, sin añadir un componente nuevo (backups, monitorización, curva de aprendizaje).
2. **Joins transaccionales** — el proyecto cruza constantemente búsqueda con datos relacionales
   (clientes, sectores, fechas, montos): en pgvector es un `JOIN`+`WHERE` atómico; en las otras es
   coordinar dos sistemas.
3. **Búsqueda híbrida natural** — `tsvector`/`ts_rank` de Postgres combinan con la similitud vectorial
   sin bolt-on.
4. **Escala esperada** — cientos a miles de presupuestos × 10–50 chunks = decenas/cientos de miles de
   vectores: dos órdenes de magnitud por debajo de cualquier techo de pgvector.

## Cuándo dejaría de ser correcta

- Volumen **>50M** sostenido → evaluar Qdrant/Milvus (o pgvectorscale+DiskANN).
- Producto dominado por **match exacto** de nombres/SKUs → Weaviate o Elasticsearch.
- Equipo **sin experiencia en Postgres** pero con presupuesto SaaS y prioridad developer-velocity →
  Pinecone (por debajo de 10M).
- **Multi-región nativa con SLA estricto** → Pinecone/Astra. **Multimodal** de primera clase →
  LanceDB/Marqo.

Muchos proyectos empiezan en pgvector y migran cuando un eje cruza un umbral concreto. La migración
nunca es trivial, pero es viable si el diseño del esquema y de la capa de datos la contemplan — algo
que hacemos en el ejercicio.
