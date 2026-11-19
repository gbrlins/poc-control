"""rfi_itens.traducoes: cache of the AI justification translated for display (pt original stays in `justificativa`)

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("rfi_itens", sa.Column("traducoes", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("rfi_itens", "traducoes")
