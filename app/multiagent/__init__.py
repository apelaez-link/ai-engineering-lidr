"""Sistema multi-agente con supervisor (sesión 14): equipo coordinado A MANO.

El grafo lineal de la S13 se convierte en un EQUIPO: un supervisor que enruta y varios
workers especializados, cada uno con PRIVILEGIO MÍNIMO (solo sus tools), coordinado con
`StateGraph` + `Command` (construido a mano, sin `create_supervisor`). Y una persona en
el bucle (`interrupt()`) que aprueba/rechaza las estimaciones de riesgo antes de cerrar.

Submódulos:
  - state:       MultiAgentState (estado del equipo) con reducers acumuladores.
  - privileges:  AGENT_PRIVILEGES (qué tool puede usar cada agente) + enforcement + auditoría.
  - build:       el supervisor, los 4 workers, el nodo human_review (interrupt) y el cableado.
  - router:      POST /multiagent/estimate (arranque) y POST /multiagent/resume/{thread_id}.
"""
