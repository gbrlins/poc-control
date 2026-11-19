"""classificacoes.traducoes: cache of the AI justification translated for display

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("classificacoes", sa.Column("traducoes", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("classificacoes", "traducoes")
