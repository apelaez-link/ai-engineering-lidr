# 03 — Prompts adaptativos por perfil: el patrón "tier"

> Material del curso LIDR · AI Engineering · Sesión 5 (Antonio Pérez). (≈26 min)

**El problema:** un único system prompt da a todos la misma respuesta. Un developer quiere desglose por componentes técnicos; un director comercial quiere coste agregado + hitos + confianza. Con un prompt único, los usuarios vuelven a "promptear" ("dame solo el resumen ejecutivo") → reaparece el chat encubierto que combatimos en la sesión 4.

**El mito a desmontar:** adaptar por perfil NO requiere fine-tuning ni RLHF. La sofisticación de los productos IA bien hechos **no vive en el modelo, vive en el resto de la app**. La respuesta correcta y poco glamurosa: una columna `tier`, un `if/elif` que elige el template Jinja2, y un schema Pydantic por tier.

## Las 3 capas
1. **Persistencia** — el `tier` vive en la tabla `users` del backend de negocio (enum: `developer | pm | executive`). **No es autorización** (qué puede hacer); es **dimensión de producto** (qué experiencia recibe).
2. **Propagación** — el tier viaja al servicio IA: como **claim en un JWT** firmado (correcto a medio plazo, defensa en profundidad) o como **header simple** en red privada controlada. **Nunca** como parámetro libre del cliente.
3. **Materialización** — el tier selecciona **template + schema**:
```python
class DeveloperEstimate(BaseModel): components: list[...]; technical_risks: list[str]; ...
class ExecutiveEstimate(BaseModel): headline_cost_range: CostRange; confidence_level: Literal["low","medium","high"]; go_no_go_recommendation: str; ...

TIER_CONFIG = {
  "developer": {"template": "estimate_developer.j2", "schema": DeveloperEstimate},
  "pm":        {"template": "estimate_pm.j2",        "schema": PmEstimate},
  "executive": {"template": "estimate_executive.j2", "schema": ExecutiveEstimate},
}
```
El endpoint resuelve el config por tier, renderiza el template y fuerza el schema. **Eso es todo el patrón.**

## Diseñar los templates
Comparten estructura (rol, contexto CAG, transcripción) y se diferencian en instrucciones + formato. Usa **`{% include %}`** para los bloques compartidos (project_metadata, reference_estimates). Las **instrucciones se diferencian** (el developer enumera componentes/riesgos/asunciones; el executive lleva con un rango de coste + go/no-go), el **formato no se mezcla**. El schema actúa como **segundo guardrail**.

## Evolución de tiers (heurísticas)
- **Tres es buen número** para arrancar; añade más por evidencia, no por anticipación.
- **Tier compuesto = tier mal definido** (un "executive con detalle técnico" suele significar que al executive le falta un apéndice técnico). Refinar > multiplicar.
- **Nuevo tier = nuevo template + schema + golden cases.** Sin evals que validen que produce respuestas distintas y de calidad, es complejidad sin valor.

## Antipatrón paralelo: el tier que solo cambia el TONO
`{% if tier == "executive" %}responde en tono ejecutivo{% endif %}` con un **único schema**. Funciona en la demo, falla en producción: la **estructura** es la misma para todos (el ejecutivo sigue recibiendo desglose por componentes con palabras menos técnicas). **Adaptar a un perfil significa adaptar la estructura de salida, no solo el tono.** Si el tier no cambia el schema, es lock-in cosmético.

## El techo del patrón: tier → pipeline distinta
Un tier puede activar una **pipeline completa distinta** (ejemplo: OpenAI Deep Research → otro modelo, web search, modo background, informe largo con citas). En el estimator: un tier `research` con `pipeline: "deep_research"`, modelo `o3-deep-research`, tools, background, minutos y euros. El patrón escala desde "mismo motor, distinta presentación" hasta "motor completamente distinto".

## Anti-patrones
- El tier vive en el **frontend** (cualquiera manda `tier=executive`). Debe venir por canal no manipulable.
- **Un solo schema con branching de campos** (el schema deja de ser contrato).
- Templates por tier que **divergen sin disciplina** de parciales `{% include %}`.

> ⚠️ Nota del enunciado: el tier es para **explorar el concepto**, no implementarlo completo. En muchos casos iniciales añade complejidad innecesaria. Decidir **no** implementarlo en esta fase es válido.

## Recursos
- Anthropic — Building Effective Agents · OpenAI — Structured Outputs / Deep Research
