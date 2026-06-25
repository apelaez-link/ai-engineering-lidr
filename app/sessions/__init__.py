"""Paquete de MEMORIA CONVERSACIONAL del estimador (sesión 05).

Hasta la sesión 04 el estimador era TRANSACCIONAL: cada petición era un mundo
aparte, sin memoria de lo hablado antes. En la sesión 05 lo convertimos en
CONVERSACIONAL: cada interacción pertenece a una "sesión" que recuerda los turnos
anteriores (historial con ventana deslizante) y va acumulando los HECHOS conocidos
del proyecto (project_metadata) que se inyectan en cada nuevo prompt.

Este paquete expone los tres bloques de ese sistema de memoria:
  - models.py: las estructuras de datos (ProjectMetadata, ConversationHistory, Session).
  - store.py: un almacén en memoria de sesiones (volátil, sin BBDD en esta fase).
  - metadata_extractor.py: un extractor LLM (Instructor) que destila hechos del turno.
"""

from app.sessions.models import ConversationHistory, ProjectMetadata, Session

__all__ = ["ConversationHistory", "ProjectMetadata", "Session"]
