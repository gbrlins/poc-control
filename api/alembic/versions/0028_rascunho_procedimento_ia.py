"""procedimento_rascunho_id em classificacoes + gerado_por_ia em procedimentos

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-13

Rascunho de procedimento guiado gerado pela IA pra um item de PoC amarelo sem match validado (ver
app/classificacao/service.py::gerar_rascunho_procedimento). Distinto de
classificacoes.procedimento_id, que só é preenchido quando um procedimento já VALIDADO confirma o
item -- o rascunho fica em status=rascunho (invisível pra busca de outros itens, ver
_buscar_candidatos) até o próprio usuário validar manualmente (POST /api/procedimentos/{id}/validar).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "procedimentos",
        sa.Column("gerado_por_ia", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "classificacoes",
        sa.Column(
            "procedimento_rascunho_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("procedimentos.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("classificacoes", "procedimento_rascunho_id")
    op.drop_column("procedimentos", "gerado_por_ia")
