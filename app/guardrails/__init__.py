"""Guardrails de entrada y salida del estimador (sesión 04).

Lección "Guardrails y validación de outputs". Un guardrail es una comprobación
que envuelve la llamada al LLM para que el sistema sea seguro y predecible. Hay
TRES POLÍTICAS clásicas de actuación cuando un guardrail se dispara:

  1. EXCEPTION (bloquear): la petición/respuesta es inaceptable, se aborta con un
     error. Lo usamos en la validación de ENTRADA (moderación e inyección de
     prompts): si la entrada es maliciosa, no llamamos al LLM.

  2. FIX / RETRY (corregir y reintentar): la salida es recuperable; pedimos al LLM
     que la corrija. Lo aplicamos en la validación de SALIDA vía Instructor: si
     una respuesta de baja confianza no está bien marcada, lanzamos ValueError y
     Instructor reintenta con el mensaje de error.

  3. FILTER (filtrar/transformar): la salida se sanea sin abortar ni reintentar;
     se sustituye por una versión segura. Lo modelamos en el PROMPT con el bloque
     <scope>: si el proyecto está fuera de alcance, el LLM debe devolver un summary
     "Out of scope: ..." con confidence_pct=0 en vez de inventarse una estimación.

Este paquete expone las funciones y excepciones de guardrails.
"""

from app.guardrails.input import InputModerationError, validate_input
from app.guardrails.output import validate_output

__all__ = ["InputModerationError", "validate_input", "validate_output"]
