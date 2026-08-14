"""fulltext search: columna tsvector generada + índice GIN sobre chunks (sesión 10)

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-14

Sesión 10 (búsqueda híbrida). Añade a `chunks` la mitad LÉXICA de la recuperación:
una columna `content_tsv` de tipo tsvector, DERIVADA de `content`, más un índice GIN
para que `@@` (match) y `ts_rank_cd` (ranking) sean rápidos.

Dos decisiones:

  1) Columna GENERADA (GENERATED ALWAYS AS ... STORED), no una columna que rellenemos
     a mano ni un trigger. Postgres la recalcula sola en cada INSERT/UPDATE de
     `content`, así que nunca se desincroniza del texto. Requiere que la expresión sea
     IMMUTABLE: `to_tsvector('english', content)` con la config puesta como CONSTANTE
     lo es (la variante de un solo argumento, que usa la config de la sesión, NO lo es
     y Postgres la rechazaría en una columna generada).

  2) Config 'english', no 'spanish'. El enunciado usa 'spanish' porque su dataset está
     en español; NUESTRO corpus de presupuestos está en INGLÉS (así lo generamos en la
     sesión 06/07: "Project: ...", "Component: ..."). Usar la config que casa con el
     idioma del texto es lo que hace que el stemming y las stop-words funcionen.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Config de text-search alineada con el idioma del corpus (inglés). Se centraliza aquí
# y en app/config.py (fulltext_language) para que migración y consultas no diverjan.
_TS_CONFIG = "english"


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE chunks
        ADD COLUMN content_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('{_TS_CONFIG}', content)) STORED
        """
    )
    op.create_index(
        "ix_chunks_content_tsv",
        "chunks",
        ["content_tsv"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_content_tsv", table_name="chunks")
    op.execute("ALTER TABLE chunks DROP COLUMN content_tsv")
