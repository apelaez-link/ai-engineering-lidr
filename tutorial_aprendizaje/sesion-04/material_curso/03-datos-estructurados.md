# 03 — Extracción de datos estructurados

> Material del curso LIDR · AI Engineering · Sesión 4 (Antonio Pérez). (≈22 min) · **Tema del directo.**

## El problema
El usuario pidió "tabla por fases" pero el LLM devuelve **prosa**. La UI necesita columnas `phase, weeks, cost_eur, confidence_pct`. Para sacar los números: un parser regex (frágil), otro LLM extractor (caro/lento), o que lo lea el usuario (incoherente). **Esa pieza no debería existir.** Un producto serio no consume texto, consume **datos**.

## Texto libre vs JSON estructurado
En vez de adivinar qué devolvió el modelo, le **dices qué tiene que devolver**: defines el shape como un schema, lo envías en la llamada, y el proveedor garantiza que la respuesta lo cumple. Los fallos de parser son silenciosos (campo vacío en la UI); con schema, el error es explícito y temprano. *El LLM deja de ser una caja de texto y pasa a ser una función con tipo de retorno.*

## JSON Schema + Pydantic como pieza central
El schema viaja con la petición. En Python no lo escribes a mano: **Pydantic lo genera** con `model_json_schema()`.
```python
class Phase(BaseModel):
    name: str
    duration_weeks: int = Field(ge=1, le=52)
    cost_eur: int = Field(ge=0)
    confidence_pct: int = Field(ge=0, le=100)
    assumptions: list[str]

class EstimationResult(BaseModel):
    summary: str
    total_duration_weeks: int = Field(ge=1)
    total_cost_eur: int = Field(ge=0)
    confidence_pct: int = Field(ge=0, le=100)
    phases: list[Phase]

    @model_validator(mode="after")
    def total_must_match_sum_of_phases(self):
        if abs(sum(p.duration_weeks for p in self.phases) - self.total_duration_weeks) > 1:
            raise ValueError("total_duration_weeks does not match phases")
        return self
```
**Una definición, tres usos:** contrato con el LLM, documentación OpenAPI de tu API, y tipo de la variable en tu código (single source of truth). Los `model_validator` cubren también coherencia interna (no solo estructura) — base de los guardrails (lección 04).

## Tres caminos al mismo sitio
- **OpenAI — Structured Outputs** (vía nativa): pasas el modelo Pydantic en `text_format`/`response_format`; adherencia 100%.
- **Anthropic — tool use forzado** (vía idiomática): defines una tool cuyo `input_schema` es tu shape y fuerzas `tool_choice`.
- **Otros** (Mistral, Gemini, local): vía agregador (LiteLLM).

## Instructor (la abstracción que usamos)
Coge tu modelo Pydantic, detecta el proveedor y empaqueta la llamada con el mecanismo correcto. Interfaz única, retorno siempre tipado:
```python
import instructor
from openai import OpenAI
client = instructor.from_openai(OpenAI())
result = client.chat.completions.create(
    model="gpt-4o-mini", response_model=EstimationResult,
    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
)  # result es ya un EstimationResult; sin parsear JSON
```
Cambiar de proveedor = `instructor.from_anthropic(Anthropic())`. Si el LLM no respeta el schema, Instructor **reintenta** automáticamente antes de fallar.

## Decisión arquitectónica
El servicio IA **siempre devuelve el shape rico** (`EstimationResult`), no la presentación. El `output_format` es una pista para el prompt, pero el schema que sale es siempre el mismo. La presentación (tabla, PDF, slack) vive en el frontend/backend de negocio. Frontera datos/presentación limpia.

## Recursos
- OpenAI — *Introducing Structured Outputs* · Anthropic — *Tool use overview*
- Pydantic — *Models*, *Validators* · Instructor — docs · JSON Schema — *Getting Started*
