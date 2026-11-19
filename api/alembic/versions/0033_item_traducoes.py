"""itens.traducoes: cache of the item texts (title, description, criterion, category) translated for display

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("itens", sa.Column("traducoes", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("itens", "traducoes")
