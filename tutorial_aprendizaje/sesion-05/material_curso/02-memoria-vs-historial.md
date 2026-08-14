# 02 — Memoria conversacional vs historial (estrategias para CAG)

> Material del curso LIDR · AI Engineering · Sesión 5 (Antonio Pérez). (≈26 min) · **Núcleo del ejercicio.**

## La distinción
- **Historial conversacional** = el array de mensajes (system/user/assistant…) que viaja a la API en cada llamada. Estructura **bruta**, cronológica. Responde a *"¿qué dijo el usuario en el turno 7?"*.
- **Memoria conversacional** = el conjunto de **hechos destilados** sobre el dominio ("el proyecto se llama BookFlow", "stack: Rails+React+PostgreSQL", "rechazó microservicios"). Responde a *"¿qué sabemos del proyecto?"*. Cada hecho tiene un origen pero **es independiente del turno**: sobrevive aunque el turno original se descarte.

**Por qué separarlas:** (1) **coste/latencia** — el historial crece linealmente, la memoria no; (2) **resistencia al truncado** — la memoria sobrevive a la ventana deslizante (no "olvida" el nombre del proyecto); (3) **auditabilidad** — los hechos están en una estructura inspeccionable.

## El estado conversacional en el estimator
```python
class ProjectMetadata(BaseModel):       # los HECHOS (sobrevive al truncado)
    project_name: str | None = None
    assumed_team_size: int | None = None
    mentioned_technologies: list[str] = Field(default_factory=list)
    agreed_scope: str | None = None
    explicit_constraints: list[str] = Field(default_factory=list)
    rejected_options: list[str] = Field(default_factory=list)

class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    history: list[Message] = Field(default_factory=list)   # los TURNOS
    project_metadata: ProjectMetadata = Field(default_factory=ProjectMetadata)
    created_at: datetime; updated_at: datetime
```
En cada turno: (1) inyecta `project_metadata` + ventana de `history` en el system prompt; (2) llama al LLM; (3) actualiza **ambos** (añade par user/assistant al historial; extrae hechos nuevos a la memoria).

## Inyección de memoria en el system prompt (Jinja2)
Bloque `<project_metadata>` con **render condicional** (cada campo solo si tiene valor — evita "Project name: None"). Instrucción clave: *"treat the project_metadata as established facts; do not contradict them unless the user explicitly revises them"* (sin esto, el modelo renegocia hechos ya cerrados).

## Actualizar la memoria tras cada turno — dos vías
- **Heurística** (regex/vocabulario): coste 0, latencia despreciable, predecible; pero **frágil** (asume formulaciones concretas, acaba siendo un mini-NLP).
- **LLM extractor** (2ª llamada con prompt específico → JSON del `ProjectMetadata`): **robusto**, multilingüe, captura matices; pega: una llamada extra por turno (céntimos, 500-1500 ms) y riesgo de que invente un hecho. Reutiliza el patrón de datos estructurados de la sesión 4.
- **Cómo elegir:** dominio acotado/formulaico → heurística; abierto/multilingüe → extractor. Si hay presupuesto: extractor + validación heurística posterior.

## La gestión del historial vuelve (sesión 2)
Tres estrategias: **ventana deslizante** (últimos N), **resumen acumulativo**, **híbrida con anclas** (resumen + ventana + turnos críticos que nunca se descartan). **Consecuencia clave:** al tener `project_metadata` separado, la **ventana deslizante simple deja de ser arriesgada** — los hechos no se pierden al caer un turno. Ventana con `MAX_TURNS=6` + metadata actualizada es razonable para producción inicial.

## Cuándo olvidar (3 políticas, 3 ubicaciones)
1. **Revisión explícita** del usuario ("ya no usamos Rails, vamos con Node" → actualiza technologies + rejected_options). Vive en la lógica de actualización.
2. **TTL por sesión** (24 h sin actividad → archiva; al reanudar, ofrece nueva sesión). Vive en el ciclo de vida.
3. **Reset explícito** (`POST /sessions` crea una limpia). Es un endpoint REST.

## Persistencia (lo que NO entra aún)
En producción las sesiones viven en Redis/PostgreSQL gestionado por el backend de negocio; el servicio IA carga el estado por `session_id`. En esta fase: **dict en memoria del proceso** (simple, no escala, se pierde al reiniciar). La separación history/metadata sobrevive intacta al introducir persistencia (solo cambia el backend de almacenamiento).

## Anti-patrones
- Memoria como **string libre** en el system prompt (turno 20 = inconsistencias).
- Confiar en que el LLM "se acordará" (no tiene estado entre llamadas; si el turno cayó de la ventana, el hecho desaparece salvo memoria explícita).
- **Mezclar** memoria e historial en una sola estructura (la factura llega al truncar o migrar schema).

## Recursos
- Material sesión 02 (arquitectura de conversaciones) · Pydantic (Models/Validators)
