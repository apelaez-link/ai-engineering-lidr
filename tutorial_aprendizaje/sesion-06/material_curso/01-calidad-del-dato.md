# 01 — Calidad del dato y decisiones de arquitectura

> Material del curso LIDR · AI Engineering · Sesión 6 (Antonio Pérez). (≈24 min)

No explica qué es RAG: explica **por qué tu CAG se rompe exactamente por donde se rompe** y
da un **marco de decisión** defendible ante un stakeholder. A estas alturas aplicar RAG es
lo fácil; lo difícil es saber **cuándo** aplicarlo, cuándo no, y cuándo combinarlo.

## El techo del CAG no es solo el context window

El CAG tiene un techo compuesto por **cuatro restricciones simultáneas**:

1. **Context window** — capacidad máxima de tokens por llamada. Restricción **binaria y obvia**.
2. **Coste por consulta** — crece linealmente con los tokens de entrada. **Continua**; suele
   ser la que mata el proyecto antes que la primera (3 céntimos/consulta es desplegable; 2 € no).
3. **Latencia** — procesar 100K tokens lleva segundos. Inviable para chat síncrono, irrelevante
   para batch nocturno. **Depende del producto, no de la arquitectura.**
4. **Degradación de atención** — la más subestimada. *Lost in the middle*: la info en mitad del
   contexto se recupera peor que en los extremos. Aunque el corpus **quepa**, no se procesa con
   la misma calidad que si inyectaras solo los fragmentos relevantes.

```python
from dataclasses import dataclass

@dataclass
class CAGViability:
    fits_in_context_window: bool      # ¿Cabe técnicamente?
    cost_per_query_acceptable: bool   # ¿Es viable económicamente?
    latency_acceptable: bool          # ¿Responde dentro del SLA?
    quality_holds_with_load: bool     # ¿La calidad aguanta el corpus completo?

    def is_viable(self) -> bool:
        return all([self.fits_in_context_window, self.cost_per_query_acceptable,
                    self.latency_acceptable, self.quality_holds_with_load])
```

**Conclusión empírica:** basta con que **uno** falle para que la arquitectura no sea viable.
Y casi nunca falla solo uno. *(Aquí conecta con nuestro ejercicio: el `REPORT.md` mide
exactamente estas curvas sobre nuestros datos.)*

## La calidad del dato es la verdadera variable de control

> *"No amount of clever chunking or fancy architecture can fix fundamentally bad data."*
> (Towards Data Science, lecciones de RAG en producción.)

Un RAG **no genera** información: la recupera y la presenta. Si recupera ruido, presenta ruido
bien formateado; si recupera info desactualizada, presenta desinformación con apariencia de
respuesta autorizada. **Lo traicionero:** el sistema parece funcionar al principio (corpus
pequeño, queries del equipo). La degradación aparece cuando el corpus crece, los usuarios
preguntan lo no anticipado, y los datos se vuelven incongruentes consigo mismos.

## El pipeline RAG: seis pasos, dos pipelines

Descomposición canónica (Databricks): **ingest → parse → chunk → embed → retrieve → generate**.
La trampa es creer que es un flujo lineal en tiempo real. **No lo es:**

- **Offline (1–4: ingest → embed)** — pipeline de **indexación**. Background, minutos/horas,
  sin usuario esperando. Puede usar modelos pesados (OCR, embeddings grandes, validadores).
- **Online (5–6: retrieve → generate)** — pipeline de **consulta**. Síncrono, presupuesto de
  latencia estricto (<3 s), solo accede a vectores+metadatos, **nunca** a datos crudos.

Materializar la separación cambia la estructura del servicio: **dos endpoints disjuntos** (un
`POST /index/run` asíncrono con `BackgroundTasks`, y un `POST /query` síncrono y bloqueante).
Mezclar responsabilidades es uno de los antipatrones más comunes (el servicio se cuelga
indexando 200 PDFs mientras procesa una consulta).

## El árbol de decisión: CAG / RAG / fine-tuning

Cuatro ejes: **volumen** del corpus vs ventana · **frecuencia de actualización** ·
**trazabilidad** (¿hay que citar fuente?) · **sensibilidad** (PII, control de acceso por usuario).

```python
def recommend_architecture(corpus, model) -> Architecture:
    context_usage = corpus.total_tokens / model.context_window
    if corpus.requires_source_attribution:        return PURE_RAG  # CAG no atribuye
    if corpus.requires_per_user_access_control:   return PURE_RAG  # todo va en cada llamada
    if context_usage > 0.7:                        return PURE_RAG  # no cabe con margen
    if corpus.update_frequency_days < 7:           return PURE_RAG  # re-inyectar todo es caro
    if corpus.update_frequency_days > 90 and context_usage < 0.3:  return PURE_CAG
    return HYBRID_CAG_RAG  # contexto estable y pequeño en CAG; dinámico y voluminoso en RAG
```

**Fine-tuning no es alternativa a RAG**, es una capa encima: para estilo propio, terminología
o formato que el modelo base no respeta. Si recuperas lo correcto pero el modelo lo presenta
mal → fine-tuning. **Nunca** como sustituto de un retrieval mal diseñado.

## El caso del Proyecto 2

Tres de los cuatro ejes empujan a RAG: actualización **alta** (reuniones semanales),
trazabilidad **crítica** (defender una estimación de 80.000 € ante el cliente exige
precedentes), sensibilidad **alta** (transcripciones con datos confidenciales). Pero hay
contexto **pequeño y estable** (glosario de tecnologías, plantillas, tarifas) para el que
el **CAG sigue siendo mejor**: más simple, barato y predecible que vectorizar. → **Híbrido.**

## Trade-offs honestos

- **El coste oculto de la trazabilidad** — citar no es gratis: metadatos por chunk, propagación,
  UI. Si tu producto puede no citar, todo se simplifica.
- **El coste real de operar RAG** — no es solo inferencia: embeddings, BBDD vectorial,
  pipeline de indexación, re-indexaciones. RAG puede ser **más caro** que CAG en corpus que
  caben. La elección **no se hace por coste; por viabilidad y funcionalidad**.
- **El CAG no muere, cambia de papel** — el sistema final es "RAG **además de** CAG":
  contexto estático (instrucciones, esquemas, glosarios) inyectado tal cual + contexto
  recuperado dinámicamente vía RAG.
