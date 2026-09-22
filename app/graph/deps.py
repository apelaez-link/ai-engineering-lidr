"""Dependencias inyectadas en los nodos del grafo (sesión 13).

Los nodos son funciones del estado, pero necesitan EFECTOS (tocar la BBDD para buscar,
embeber la query, saber qué modelo usar). En vez de meter esos objetos en el estado
—que el checkpointer serializaría y no puede: una sesión de BBDD no es JSON— los
pasamos por CLOSURE: `build_estimation_graph(deps)` define los nodos cerrando sobre este
GraphDeps. Así el estado queda limpio y serializable, y las dependencias viven aparte.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.models_db import FULLTEXT_CONFIG


@dataclass
class GraphDeps:
    """Todo lo que los nodos necesitan del exterior (una instancia por ejecución).

    Los nodos LLM (extract/classify/generate) resuelven modelo y api_key con el mismo
    helper que el resto del repo (`_resolve_primary_model`, litellm/instructor sobre el
    proveedor preferido, gpt-4o-mini por defecto), así que no hace falta pasar el modelo
    aquí. Estas deps son solo lo que NO sale de la config: la sesión de BBDD y el embedder.
    """

    session: AsyncSession
    embedder: OpenAIEmbedder
    k: int = 5
    candidate_pool: int = 50
    rrf_k: int = 60
    fulltext_config: str = FULLTEXT_CONFIG
