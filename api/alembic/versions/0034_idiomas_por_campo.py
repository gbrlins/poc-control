"""idiomas: language each AI/person-written text was written in, per field (itens, classificacoes, rfi_itens, pocs, sessoes, poc_prerequisitos)

Null means pt: every text stored before this migration was pt-BR. See app/idioma.py.

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# itens/classificacoes/rfi_itens já tinham `traducoes` (0031-0033): só ganham a marca de idioma.
_SO_IDIOMAS = ("itens", "classificacoes", "rfi_itens")
# Resumo executivo, pontos da sessão e pré-requisitos aparecem nos relatórios, então ganham as duas colunas.
_IDIOMAS_E_TRADUCOES = ("pocs", "sessoes", "poc_prerequisitos")


def upgrade() -> None:
    for tabela in (*_SO_IDIOMAS, *_IDIOMAS_E_TRADUCOES):
        op.add_column(tabela, sa.Column("idiomas", postgresql.JSONB(), nullable=True))
    for tabela in _IDIOMAS_E_TRADUCOES:
        op.add_column(tabela, sa.Column("traducoes", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    for tabela in reversed(_IDIOMAS_E_TRADUCOES):
        op.drop_column(tabela, "traducoes")
    for tabela in reversed((*_SO_IDIOMAS, *_IDIOMAS_E_TRADUCOES)):
        op.drop_column(tabela, "idiomas")
