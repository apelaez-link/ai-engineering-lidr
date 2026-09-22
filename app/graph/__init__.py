"""Orquestación con LangGraph (sesión 13): el flujo de estimación como un GRAFO.

Reexpresamos el pipeline de S9-S12 como un grafo de estados explícito:

    START → extract_requirements → classify_components → search_budgets
          → generate_estimate → validate_and_consolidate → END

De puertas afuera nada cambia (transcripción → estimación + estado); el grafo vive
dentro. El salto respecto al bucle a mano de la S12 es que ahora el flujo es EXPLÍCITO
(nodos + aristas), con estado TIPADO y un REDUCER acumulador, persistencia
(checkpointer) y observabilidad (Logfire), que son justo lo que un framework aporta.

Submódulos:
  - state:         EstimationState (TypedDict) + reducers (Annotated[..., operator.add]).
  - deps:          GraphDeps — dependencias (sesión BBDD + embedder) inyectadas en los nodos.
  - build:         los 5 nodos (funciones puras) + el cableado del StateGraph.
  - observability: configuración de Logfire + helper de span por nodo.
  - router:        el endpoint POST /graph/estimate.
"""
