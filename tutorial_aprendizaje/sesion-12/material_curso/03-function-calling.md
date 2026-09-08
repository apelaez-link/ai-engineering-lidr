# Lección 3 — Function calling en la práctica: tools, schemas y contrato (21 min)

> Notas fieles (Antonio Pérez). Resumen didáctico, no transcripción.

## El malentendido que hay que matar
**El modelo NO ejecuta tu código. Nunca.** Solo emite una petición estructurada ("quiero llamar a
`search_budgets` con estos argumentos") y **tú** decides ejecutarla. Function calling no es el modelo
ejecutando funciones; es el modelo **pidiéndote** que las ejecutes.

## El contrato (4 tiempos)
1. Tú **declaras** las tools (qué operaciones existen, qué forma tienen sus entradas).
2. El modelo **emite** una petición estructurada (nombre + argumentos) si decide que la necesita.
3. Tu código **ejecuta** (aquí sí se consulta la BBDD / se corre el cálculo).
4. Devuelves el **resultado**; el modelo sigue razonando con ese dato.

Es una **interfaz tipada de manual**: declaras schema, alguien pide conforme al schema, ejecutas,
devuelves. La única diferencia: quien llama es un **modelo** que elige según la conversación.

## Anatomía de una tool
**Nombre** (único; con namespace si crecen: `budgets_search`). **Descripción** (lo único que el
modelo lee para decidir cuándo/cómo usarla → la pieza de mayor apalancamiento). **Parámetros**
(JSON Schema: tipos, `enum`, requeridos). **`strict: true`** (los argumentos se ciñen al schema).
*El schema no solo valida: enseña* (un `enum` restringe; "una llamada por componente" en la
descripción evita que meta integración+migración en una búsqueda).

## El ida y vuelta en la Responses API
```python
response = client.responses.create(model="gpt-5", reasoning={"effort":"medium"},
                                    input=[{"role":"user","content":transcript}], tools=TOOLS)
for item in response.output:
    if item.type == "function_call":
        args = json.loads(item.arguments)
        result = execute_tool(item.name, args)         # tu código ejecuta
        response = client.responses.create(model="gpt-5", previous_response_id=response.id,
            input=[{"type":"function_call_output","call_id":item.call_id,"output":json.dumps(result)}],
            tools=TOOLS)
```
Tres cosas: la salida es **una lista de items tipados** (recorre `response.output`, no asumas que
el primero es la respuesta); cada `function_call` trae un **`call_id`** que debes referenciar en el
`function_call_output` (olvidarlo es el error #1); el estado se encadena con **`previous_response_id`**.
⚠️ En Responses el schema es **plano** (`type`/`name`/`description`/`parameters` al mismo nivel);
en Chat Completions va anidado bajo `function`. Copiar el formato de una a otra da error.

## Llamadas en paralelo
Una vuelta puede traer **varias** `function_call` (4 componentes → 4 `search_budgets`). Recoge
todas, ejecútalas con **`asyncio.gather`**, y devuelve **todos** los `function_call_output` (cada
uno con su `call_id`) en **una** continuación. Asumir "siempre una" se rompe con la primera
transcripción compleja.

## Portabilidad (Anthropic)
Mismo contrato, otra forma: en Anthropic la tool usa `input_schema` (no `parameters`), el modelo
devuelve bloques `tool_use` (no `function_call`), `stop_reason:"tool_use"`, y respondes con
`tool_result`. **Aísla el transporte en un adaptador** y mantén la lógica de tus tools independiente
del proveedor.

## Diseñar tools que el modelo use bien
- **La descripción es la interfaz**: escríbela para un lector que solo ve la firma. Si elige mal, casi
  siempre es la descripción, no el modelo.
- **Resultados de alto valor**: solo lo necesario, con ids estables (no un volcado de 200 filas).
- **Errores como observación informativa** (recuperación) vs `error` genérico (ceguera).
- **Valida argumentos antes de lo que duele** (`strict` garantiza forma, no sentido).
- **Granularidad**: una tool por operación con fronteras nítidas; si explicas en la descripción
  *cuándo no* usarla, quizá hace demasiado.

## Cómo aplica al estimador
Las tools **envuelven** capacidades que el servicio IA ya tiene (retrieval S10, cálculo, guardrails
S4). El backend de negocio no ve `function_call` ni `call_id`: envía transcripción, recibe estimación.
