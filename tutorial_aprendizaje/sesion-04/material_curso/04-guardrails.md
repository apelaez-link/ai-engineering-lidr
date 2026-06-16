# 04 — Guardrails y validación de outputs

> Material del curso LIDR · AI Engineering · Sesión 4 (Antonio Pérez). (≈26 min) · **Tema del directo.**

## La forma no garantiza el contenido
El bloque anterior garantiza que la respuesta cumple el schema. **La forma, no el contenido.** Cuatro casos que pasan la validación pero rompen el producto:
1. **Prompt injection** en `description` ("Ignore all previous instructions...").
2. **Fuera de scope**: "reformar el baño" → el sistema devuelve una estimación de software convincente sobre algo que no debería responder.
3. **PII**: el usuario pega datos personales → se envían al proveedor y quedan en sus logs.
4. **Alucinación coherente**: una fase "Negotiation with NASA, 8 weeks" que suma bien y está en rango.

## Dos ejes, dos categorías
- **Sintáctico** (forma): tipos, rangos, enums, coherencia interna. Lo cubre Pydantic, barato.
- **Semántico** (significado): ¿es seguro, tiene sentido, está en scope, no inventa? No hay regla universal; requiere otro modelo, más caro.
- Cruzado con **input** / **output** → matriz de 4 cuadrantes. Eugene Yan: *syntactic vs semantic errors*, guardrails como **defensive UX**.

## Pipeline: defense in depth (5 capas)
1. **Validación sintáctica del input** (Pydantic sobre EstimationRequest).
2. **Validación semántica del input** — Moderation API de OpenAI (gratis, ~50-100 ms) + heurísticas (patrones de prompt injection, PII por regex).
3. **Robustez del prompt** — no es guardrail estricto pero es lo más barato y eficaz: dar permiso a decir "no sé", definir el scope en el system prompt, few-shot de respuestas correctas/incorrectas. Para el estimator: "If the description is out of scope, set summary to an out-of-scope message and confidence_pct=0".
4. **Validación sintáctica del output** (schema, lección 03).
5. **Validación semántica del output** — `model_validator` con lógica de negocio (confianza baja → marcar), Guardrails AI (PII filtrada, toxicidad), y para casos críticos **LLM-as-judge** (segunda llamada a un modelo barato).

Las llamadas de Moderation/Guardrails devuelven un **score**, no un booleano: el **threshold es decisión de producto**.

## Tres políticas de fallo (declararlas explícitamente)
- **Exception** — aborta con error (400/422). Para violaciones graves: PII, injection clara, toxicidad.
- **Fix con retry** — pide al modelo que corrija y reintenta. Para errores recuperables (JSON malformado, suma que no cuadra). Es lo que hace Instructor por defecto.
- **Filter / degrade** — devuelve una respuesta segura por defecto (out-of-scope con `confidence_pct=0`, `phases=[]`). Decisión de UX, no error.

Regla: cada guardrail declara cuál de las tres aplica. El error más común no es elegir mal, es **no decidir**.

## Aterrizaje (resumen de código)
```python
def validate_input(description: str) -> None:
    if client.moderations.create(input=description).results[0].flagged:
        raise InputModerationError("flagged by moderation")
    for pat in PROMPT_INJECTION_PATTERNS:        # "ignore previous", "you are now", "</project_description>"...
        if pat in description.lower():
            raise InputModerationError(f"possible injection: {pat!r}")
```
En el endpoint: `validate_input` antes de componer el prompt (política **exception** → 400). En `system.j2`: bloque `<scope>` (política **filter**). En `EstimationResult`: `model_validator` que exige out-of-scope explícito si `confidence_pct < 30` (política **fix con retry** vía Instructor).

## Coste y falsos positivos
Cada capa añade latencia/coste y produce falsos positivos (moderation flagea texto técnico, un detector bloquea a quien cita ejemplos). Regla: **logging primero, bloqueo después** — despliega en modo "log only" 1-2 semanas, ajusta thresholds, luego bloquea. Mantén métricas (tasa de disparos, falsos positivos).

> Conexión con la lección 05: los guardrails deben aplicarse **antes** del cache hit, o el cache servirá respuestas inseguras tan rápido como las seguras.

## Recursos
- Eugene Yan — *Patterns for Building LLM-based Systems* (Guardrails, Defensive UX), *What We Learned from a Year of Building with LLMs*
- Guardrails AI — *Quickstart* · OpenAI — *Moderation guide* · Anthropic — *Reduce hallucinations*
