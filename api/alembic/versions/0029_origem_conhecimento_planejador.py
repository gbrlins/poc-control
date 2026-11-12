"""origem_conhecimento: add 'planejador' value (AI-guided draft from a planner test, no PoC item yet)

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-12

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADD VALUE não pode rodar dentro de uma transação em todas as versões do Postgres (ver 0016).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE origem_conhecimento ADD VALUE IF NOT EXISTS 'planejador'")


def downgrade() -> None:
    # O Postgres não tem DROP VALUE; o valor fica (inofensivo), mesma decisão da migração 0016.
    pass
