"""categorias (taxonomia fixa) em procedimentos/itens/rfi_itens + procedimento_id em rfi_itens

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-29

Taxonomia fixa de áreas do portfólio SUSE (app/categorias.py), para restringir a busca vetorial de
procedimentos por afinidade em vez de varrer a base inteira a cada item (classificacao/service.py),
e para o RFI poder citar um procedimento interno confirmado (rfi/service.py), igual ao que a
classificação de PoC já faz.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "procedimentos",
        sa.Column("categorias", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_procedimentos_categorias", "procedimentos", ["categorias"], postgresql_using="gin"
    )
    op.add_column("itens", sa.Column("categoria_codigo", sa.String(10), nullable=True))
    op.add_column("rfi_itens", sa.Column("categoria_codigo", sa.String(10), nullable=True))
    op.add_column(
        "rfi_itens",
        sa.Column(
            "procedimento_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("procedimentos.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("rfi_itens", "procedimento_id")
    op.drop_column("rfi_itens", "categoria_codigo")
    op.drop_column("itens", "categoria_codigo")
    op.drop_index("ix_procedimentos_categorias", table_name="procedimentos")
    op.drop_column("procedimentos", "categorias")
