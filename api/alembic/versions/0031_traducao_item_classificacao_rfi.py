"""itens/classificacoes/rfi_itens: idioma_original + cache de traduções sob demanda (traducoes)

Branch v2: generaliza pra Item/Classificacao/RfiItem o mesmo mecanismo que Procedimento já tinha
(migração 0026) -- ver api/app/traducao.py::campos_no_idioma.

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABELAS = ("itens", "classificacoes", "rfi_itens")


def upgrade() -> None:
    for tabela in _TABELAS:
        op.add_column(tabela, sa.Column("idioma_original", sa.String(length=5), nullable=True))
        op.add_column(
            tabela,
            sa.Column("traducoes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        )


def downgrade() -> None:
    for tabela in _TABELAS:
        op.drop_column(tabela, "traducoes")
        op.drop_column(tabela, "idioma_original")
