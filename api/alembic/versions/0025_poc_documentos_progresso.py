"""itens.documento_id; pocs.processamento_iniciado_em/progresso/cancelamento_solicitado (fila de
múltiplos documentos por PoC, mesmo padrão do RFI -- 0023/0024)

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "itens",
        sa.Column(
            "documento_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("poc_documentos.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column("pocs", sa.Column("processamento_iniciado_em", sa.DateTime(timezone=True), nullable=True))
    op.add_column("pocs", sa.Column("progresso", postgresql.JSONB(), nullable=True))
    op.add_column(
        "pocs", sa.Column("cancelamento_solicitado", sa.Boolean(), nullable=False, server_default=sa.false())
    )

    # Backfill: toda PoC existente já tem no máximo um poc_documentos (criar_poc sempre gravou um
    # só até aqui) -- liga os itens já extraídos a esse documento.
    op.execute(
        "UPDATE itens SET documento_id = d.id FROM poc_documentos d WHERE d.poc_id = itens.poc_id"
    )


def downgrade() -> None:
    op.drop_column("pocs", "cancelamento_solicitado")
    op.drop_column("pocs", "progresso")
    op.drop_column("pocs", "processamento_iniciado_em")
    op.drop_column("itens", "documento_id")
