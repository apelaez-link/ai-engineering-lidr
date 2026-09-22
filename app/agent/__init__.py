"""Capa de agentes (sesión 12): un agente construido A MANO, sin framework.

Un agente = un bucle (razona → actúa → observa → repite) que llama a un LLM que
DECIDE, ejecuta tools y PARA cuando ha terminado. Se construye a mano para ver de qué
está hecho; los frameworks (LangGraph, sesión 13) envuelven exactamente esto.

El agente es una CAPA DE DECISIÓN por encima del pipeline de S9-S11: sus tools envuelven
piezas que ya existen (el retrieval híbrido de S10) o son deterministas (el cálculo).

Submódulos:
  - schemas: la salida estructurada final (AgentEstimate) y la traza (TraceStep, AgentRun).
  - tools:   las tools del agente (schemas planos de la Responses API + implementaciones).
  - loop:    el bucle agéntico a mano sobre client.responses.parse (function_call/output).
  - router:  el endpoint POST /agent/estimate.
"""
