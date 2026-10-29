"""exclusoes.tipo: String(10) -> String(20), "procedimento" (12 caracteres) não cabia

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-29

A coluna `exclusoes.tipo` (migração 0017) foi criada como String(10), suficiente para "poc"/"rfi"
mas não para "procedimento" (12 caracteres) -- truncava com erro de banco ao excluir um
procedimento. Descoberto rodando a suíte de testes de verdade (test_exclusao_db.py) na Raspberry.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("exclusoes", "tipo", type_=sa.String(20), existing_type=sa.String(10), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("exclusoes", "tipo", type_=sa.String(10), existing_type=sa.String(20), existing_nullable=False)
