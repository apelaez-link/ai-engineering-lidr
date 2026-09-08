# Lección 4 — El bucle agéntico paso a paso (18 min)

> Notas fieles (Antonio Pérez). Resumen didáctico, no transcripción. **Es la implementación de referencia del ejercicio.**

Construir el agente **a mano, sin framework** — no porque los frameworks sean malos, sino porque
montar el bucle en crudo es la única forma de entender qué automatizan (y de tomar el control cuando
haga falta). Un agente de estimación funcional cabe en **~50 líneas**.

## Las 4 piezas
- **Tools**: capacidades ejecutables (`search_budgets`, `calculate_estimate`, `validate_estimate`), cada una envuelve algo que el servicio IA ya sabe hacer.
- **Modelo**: el orquestador (gpt-5, esfuerzo medio) — decide qué tool usar.
- **Bucle**: llamar → ejecutar tools → devolver resultados → repetir, hasta respuesta final o `MAX_STEPS`.
- **Estado**: el contexto que se acumula vuelta a vuelta = la **traza** inspeccionable.

## El despacho de tools (registro)
```python
TOOL_REGISTRY = {"search_budgets": search_budgets, "calculate_estimate": calculate_estimate,
                 "validate_estimate": validate_estimate}
async def execute_tool(name, args):
    fn = TOOL_REGISTRY.get(name)
    if fn is None: return {"error": f"unknown tool: {name}"}
    try: return await fn(args)
    except Exception as exc: return {"error": str(exc)}   # un fallo de tool NO revienta el bucle
```
El registro **desacopla** qué tools existen de cómo funciona el bucle: añadir una tool = un schema
+ una entrada, el bucle no cambia. El `try/except` devuelve el error **como observación** (el modelo
puede leerlo y reformular) — decisión de diseño, no defensa.

## El bucle
```python
response = await client.responses.parse(model="gpt-5", reasoning={"effort":"medium"},
    instructions=SYSTEM_PROMPT, input=[{"role":"user","content":transcript}],
    tools=TOOLS, text_format=Estimate)
for _ in range(MAX_STEPS):
    calls = [it for it in response.output if it.type == "function_call"]
    if not calls: break                                   # el modelo ya tiene su respuesta final
    results = await asyncio.gather(*(execute_tool(c.name, json.loads(c.arguments)) for c in calls))
    tool_outputs = [{"type":"function_call_output","call_id":c.call_id,"output":json.dumps(r)}
                    for c, r in zip(calls, results)]
    trace += [...]                                        # acción + args + observación por vuelta
    response = await client.responses.parse(model="gpt-5", previous_response_id=response.id,
        instructions=SYSTEM_PROMPT, input=tool_outputs, tools=TOOLS, text_format=Estimate)
else:
    return AgentResult(status="max_steps_exceeded", trace=trace)
return AgentResult(status="done", estimate=response.output_parsed, trace=trace)
```
Decisiones: 1ª llamada **fuera** del bucle; cada vuelta recoge **todas** las `function_call`; se
ejecutan en **paralelo** (`asyncio.gather`); se devuelven todas juntas con su `call_id`; el estado se
encadena con `previous_response_id` (pero **reenvías `instructions`**, que no se arrastra); la traza
se acumula; y **todo bajo `range(MAX_STEPS)`** con el `else` del `for` capturando la no-convergencia.

## Comportamiento adaptativo (por qué el bucle)
Traza real: paso 1 busca ERP (4 matches), paso 2 busca migración (1 match débil), **paso 3 reformula
la migración** (3 matches) antes de calcular sobre datos pobres, paso 4 `calculate_estimate`, paso 5
`validate_estimate`. Ese reintento **no lo programaste**: emergió de que el modelo vio el resultado de
su propia acción. Es el agente ganándose su sitio.

## Salida estructurada determinista
Todas las llamadas pasan `text_format=Estimate` (modelo Pydantic). El agente puede recorrer caminos
distintos cada vez, pero **la forma de la salida es siempre la misma**: la no-determinación vive
dentro del bucle; **el contrato de salida es determinista**.

## Detrás de un endpoint
El bucle vive en el servicio IA tras `POST /estimate` (FastAPI). El backend de negocio hace una
llamada HTTP y recibe `{status, estimate, trace}`; **no ve** el bucle, ni `function_call`, ni `call_id`,
ni cuántas vueltas dio. Esa frontera te deja reescribir el agente sin tocar el backend.

## Qué enseña construirlo a mano
El **manejo de errores es tuyo** (try/except + `MAX_STEPS` + status de salida); la **observabilidad
no viene gratis** (la traza es tu instrumento; enriquécela con tiempos/tokens/reasoning summary); y
**entiendes lo que un framework haría por ti** (este bucle + estado + reintentos + instrumentación +,
en los elaborados, orquestación como grafo → S13). Adoptar un framework pasa a ser decisión informada.
