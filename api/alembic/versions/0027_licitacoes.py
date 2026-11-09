"""licitacoes + licitacao_termos_busca: monitor de editais do PNCP (beta)

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-09

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Lista inicial, extraída do vocabulário já usado em app/categorias.py (produtos/conceitos de cada
# uma das 8 áreas do portfólio SUSE). Ajustável depois pela tela de admin em /licitacoes -- isto é
# só o ponto de partida.
_TERMOS_INICIAIS = [
    ("virtualização", "VIRT"),
    ("virtualização de servidores", "VIRT"),
    ("hipervisor", "VIRT"),
    ("hiperconvergência", "VIRT"),
    ("Harvester", "VIRT"),
    ("Kubernetes", "K8S"),
    ("orquestração de contêineres", "K8S"),
    ("contêineres", "K8S"),
    ("containers", "K8S"),
    ("Rancher", "K8S"),
    ("RKE2", "K8S"),
    ("K3s", "K8S"),
    ("armazenamento definido por software", "STR"),
    ("storage definido por software", "STR"),
    ("Longhorn", "STR"),
    ("segurança de contêineres", "SEC"),
    ("NeuVector", "SEC"),
    ("análise de vulnerabilidade", "SEC"),
    ("observabilidade", "OBS"),
    ("Prometheus", "OBS"),
    ("Grafana", "OBS"),
    ("monitoramento de infraestrutura", "OBS"),
    ("sistema operacional Linux", "OS"),
    ("SUSE Linux Enterprise", "OS"),
    ("SLES", "OS"),
    ("suporte Linux", "OS"),
    ("edge computing", "EDGE"),
    ("computação de borda", "EDGE"),
    ("inteligência artificial", "IA"),
    ("MLOps", "IA"),
]


def upgrade() -> None:
    op.create_table(
        "licitacao_termos_busca",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("termo", sa.String(200), nullable=False, unique=True),
        sa.Column("categoria_codigo", sa.String(10), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "licitacoes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("numero_controle_pncp", sa.String(50), nullable=False, unique=True),
        sa.Column("orgao_nome", sa.String(255), nullable=False),
        sa.Column("orgao_cnpj", sa.String(20), nullable=False),
        sa.Column("unidade_nome", sa.String(255), nullable=True),
        sa.Column("uf", sa.String(2), nullable=True),
        sa.Column("municipio", sa.String(255), nullable=True),
        sa.Column("objeto", sa.Text(), nullable=False),
        sa.Column("modalidade_codigo", sa.Integer(), nullable=False),
        sa.Column("modalidade_nome", sa.String(100), nullable=True),
        sa.Column("valor_estimado", sa.Numeric(14, 2), nullable=True),
        sa.Column("data_publicacao", sa.Date(), nullable=False),
        sa.Column("data_abertura_proposta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_encerramento_proposta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ano_compra", sa.Integer(), nullable=False),
        sa.Column("sequencial_compra", sa.Integer(), nullable=False),
        sa.Column("termos_encontrados", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("link_pncp", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_licitacoes_data_publicacao", "licitacoes", ["data_publicacao"])

    termos_table = sa.table(
        "licitacao_termos_busca",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("termo", sa.String),
        sa.column("categoria_codigo", sa.String),
    )
    op.bulk_insert(
        termos_table,
        [{"id": uuid.uuid4(), "termo": termo, "categoria_codigo": codigo} for termo, codigo in _TERMOS_INICIAIS],
    )


def downgrade() -> None:
    op.drop_index("ix_licitacoes_data_publicacao", table_name="licitacoes")
    op.drop_table("licitacoes")
    op.drop_table("licitacao_termos_busca")
