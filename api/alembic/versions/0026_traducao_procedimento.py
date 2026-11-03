"""procedimentos: idioma_original + cache de traduções sob demanda (traducoes)

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("procedimentos", sa.Column("idioma_original", sa.String(length=5), nullable=True))
    op.add_column(
        "procedimentos",
        sa.Column("traducoes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("procedimentos", "traducoes")
    op.drop_column("procedimentos", "idioma_original")
