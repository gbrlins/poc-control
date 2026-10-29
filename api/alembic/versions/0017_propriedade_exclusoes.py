"""propriedade (criado_por_id, responsavel_id) em pocs/procedimentos/rfis e a tabela de auditoria exclusoes

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-29

ADR 4 (poc-planner/docs/adr/ADR-0004-ownership-deletion.md). Só acrescenta colunas anuláveis e uma tabela. PoCs e
procedimentos existentes ficam SEM dono (ninguém os exclui até alguém assumir). As RFIs já registram quem as criou
(`criado_por_id`), então o dono delas começa sendo o criador.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fk_user(nome: str):
    return sa.Column(nome, postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def upgrade() -> None:
    for tabela in ("pocs", "procedimentos"):
        op.add_column(tabela, _fk_user("criado_por_id"))
        op.add_column(tabela, _fk_user("responsavel_id"))
    op.add_column("rfis", _fk_user("responsavel_id"))
    op.execute("UPDATE rfis SET responsavel_id = criado_por_id")

    op.create_table(
        "exclusoes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("excluido_por_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("contagens", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_table("exclusoes")
    op.drop_column("rfis", "responsavel_id")
    for tabela in ("procedimentos", "pocs"):
        op.drop_column(tabela, "responsavel_id")
        op.drop_column(tabela, "criado_por_id")
