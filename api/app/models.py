import enum
import uuid
from datetime import date, datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.gemini import EMBEDDING_DIM


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gemini_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nome do modelo de texto do Gemini (ex.: "gemini-3.8-flash"). Livre, não um enum: a
    # disponibilidade de modelo depende do plano/chave de cada usuário (ver app/gemini_key.py).
    # Nulo = usa o default do servidor. NÃO afeta o modelo de embedding (EMBEDDING_DIM em
    # app/gemini.py está fixo no formato da coluna vector do pgvector).
    gemini_model: Mapped[str | None] = mapped_column(String(100), nullable=True)


class StatusProcedimento(str, enum.Enum):
    rascunho = "rascunho"
    validado = "validado"


class Procedimento(Base):
    __tablename__ = "procedimentos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    cliente_origem: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_origem: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[StatusProcedimento] = mapped_column(
        Enum(StatusProcedimento, name="status_procedimento"), default=StatusProcedimento.rascunho
    )
    versao: Mapped[int] = mapped_column(Integer, default=1)
    html_original: Mapped[str] = mapped_column(Text, nullable=False)
    # Taxonomia fixa (app/categorias.py) -- um procedimento pode cobrir mais de uma área (ex.: o
    # seed de Vault é K8S e SEC). Usado para restringir a busca vetorial por afinidade antes de
    # rankear por similaridade (classificacao/service.py::_buscar_candidatos).
    categorias: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    criado_por_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    criado_por: Mapped["User | None"] = relationship(foreign_keys=[criado_por_id])
    responsavel: Mapped["User | None"] = relationship(foreign_keys=[responsavel_id])
    chunks: Mapped[list["ProcedimentoChunk"]] = relationship(
        back_populates="procedimento", cascade="all, delete-orphan", order_by="ProcedimentoChunk.order_index"
    )

    @property
    def responsavel_email(self) -> str | None:
        """Pydantic (`from_attributes=True`) lê isso direto via getattr -- é o que permite
        `ProcedimentoListItem.model_validate(procedimento)` sem um builder manual, diferente de
        Poc/Rfi que já montam a resposta campo a campo."""
        return self.responsavel.email if self.responsavel else None


class ProcedimentoChunk(Base):
    __tablename__ = "procedimento_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    procedimento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("procedimentos.id", ondelete="CASCADE"), nullable=False
    )
    heading_level: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_title: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_heading_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

    procedimento: Mapped[Procedimento] = relationship(back_populates="chunks")


class StatusPoc(str, enum.Enum):
    ativa = "ativa"
    concluida = "concluida"
    suspensa = "suspensa"


class StatusExtracao(str, enum.Enum):
    extraindo = "extraindo"
    pronto = "pronto"
    erro = "erro"


class Poc(Base):
    __tablename__ = "pocs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    cliente: Mapped[str] = mapped_column(String(255), nullable=False)
    escopo: Mapped[str | None] = mapped_column(Text, nullable=True)
    resumo_executivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[StatusPoc] = mapped_column(Enum(StatusPoc, name="status_poc"), default=StatusPoc.ativa)
    status_extracao: Mapped[StatusExtracao] = mapped_column(
        Enum(StatusExtracao, name="status_extracao"), default=StatusExtracao.extraindo
    )
    erro_extracao: Mapped[str | None] = mapped_column(Text, nullable=True)
    fases: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    # Parâmetros técnicos desta PoC (produtos, rede, infra) quando a origem foi o JSON do
    # Planejar PoC — ver app/pocs/planner_import.py. Extraído direto da estrutura conhecida do
    # JSON (sem passar pelo Gemini) para não arriscar perder/alucinar IPs e hostnames.
    # Nunca contém credenciais. Usado no roteiro do dia (app/pocs/roteiro.py).
    parametros_tecnicos: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Nome do modelo do Gemini que de fato extraiu os itens (resolve_model(user) ou o default do
    # servidor) — exibido na UI pra confirmar qual modelo respondeu, sem precisar olhar os logs
    # do container na Raspberry.
    modelo_extracao: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Propriedade (ADR 4): o dono é `responsavel_id` -- só ele exclui e transfere; `criado_por_id` é só fato de auditoria.
    # Nulo = sem dono (todas as PoCs anteriores à migração 0017): ninguém exclui até alguém assumir.
    criado_por_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    criado_por: Mapped["User | None"] = relationship(foreign_keys=[criado_por_id])
    responsavel: Mapped["User | None"] = relationship(foreign_keys=[responsavel_id])
    documentos: Mapped[list["PocDocumento"]] = relationship(
        back_populates="poc", cascade="all, delete-orphan", order_by="PocDocumento.created_at"
    )
    itens: Mapped[list["Item"]] = relationship(
        back_populates="poc", cascade="all, delete-orphan", order_by="Item.fase, Item.ordem"
    )
    prerequisitos: Mapped[list["Prerequisito"]] = relationship(
        back_populates="poc", cascade="all, delete-orphan", order_by="Prerequisito.ordem"
    )
    sessoes: Mapped[list["Sessao"]] = relationship(
        back_populates="poc", cascade="all, delete-orphan", order_by="Sessao.data"
    )


class PocDocumento(Base):
    __tablename__ = "poc_documentos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    poc_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pocs.id", ondelete="CASCADE"))
    nome_arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    caminho_arquivo: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    poc: Mapped[Poc] = relationship(back_populates="documentos")


class StatusItem(str, enum.Enum):
    pendente = "pendente"
    em_andamento = "em_andamento"
    concluido = "concluido"
    bloqueado = "bloqueado"
    nao_aplicavel = "nao_aplicavel"


class CondicaoItem(str, enum.Enum):
    suse = "suse"
    cliente = "cliente"
    lateral = "lateral"
    parceiro = "parceiro"


# Resultado do teste e aderência, nos mesmos valores do SUSE PoC Planner (poc-planner/docs/adr/ADR-0001).
# `status` continua sendo o estado do fluxo de execução; `resultado` diz se o teste passou. Os membros usam
# o valor (não o nome) no banco porque "pass" é palavra reservada do Python (ver values_callable abaixo).
class ResultadoItem(str, enum.Enum):
    pending = "pending"
    scheduled = "scheduled"
    running = "running"
    pass_ = "pass"
    partial = "partial"
    fail = "fail"
    na = "na"


class PrioridadeItem(str, enum.Enum):
    must = "must"
    nice = "nice"


class AderenciaItem(str, enum.Enum):
    native = "native"
    config = "config"
    rancher = "rancher"
    third = "third"
    validate = "validate"
    gap = "gap"


class AderenciaOrigem(str, enum.Enum):
    manual = "manual"
    historico = "historico"
    web = "web"
    documento = "documento"


def _valores(enum_cls):
    return [m.value for m in enum_cls]


class Item(Base):
    __tablename__ = "itens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    poc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pocs.id", ondelete="CASCADE"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    criterio_aceite: Mapped[str | None] = mapped_column(Text, nullable=True)
    categoria: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Código da taxonomia fixa (app/categorias.py), distinto de `categoria` (texto livre vindo do
    # documento original) -- usado só para restringir a busca vetorial de procedimentos por
    # afinidade. Nulo quando o item não se encaixa claramente numa das áreas do portfólio SUSE.
    categoria_codigo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fase: Mapped[int] = mapped_column(Integer, default=1)
    ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    conducao: Mapped[CondicaoItem | None] = mapped_column(
        Enum(CondicaoItem, name="condicao_item"), nullable=True
    )
    status: Mapped[StatusItem] = mapped_column(Enum(StatusItem, name="status_item"), default=StatusItem.pendente)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    # Vindos do planejador (ADR 1). Nulos nos itens criados por Gemini a partir de um PDF/planilha.
    catalogo_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    planner_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resultado: Mapped[ResultadoItem | None] = mapped_column(
        Enum(ResultadoItem, name="resultado_item", values_callable=_valores), nullable=True
    )
    prioridade: Mapped[PrioridadeItem | None] = mapped_column(
        Enum(PrioridadeItem, name="prioridade_item", values_callable=_valores), nullable=True
    )
    aderencia: Mapped[AderenciaItem | None] = mapped_column(
        Enum(AderenciaItem, name="aderencia_item", values_callable=_valores), nullable=True
    )
    aderencia_origem: Mapped[AderenciaOrigem | None] = mapped_column(
        Enum(AderenciaOrigem, name="aderencia_origem", values_callable=_valores), nullable=True
    )
    # Texto livre até a ADR 4 trazer o dono de verdade (responsavel_id).
    responsavel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    poc: Mapped[Poc] = relationship(back_populates="itens")
    classificacao: Mapped["Classificacao | None"] = relationship(
        back_populates="item", uselist=False, cascade="all, delete-orphan"
    )
    notas: Mapped[list["Nota"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="Nota.created_at"
    )
    anexos: Mapped[list["Anexo"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="Anexo.created_at"
    )
    status_historico: Mapped[list["StatusHistorico"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="StatusHistorico.created_at"
    )


class FlagClassificacao(str, enum.Enum):
    verde = "verde"
    amarelo = "amarelo"
    vermelho = "vermelho"


class OrigemClassificacao(str, enum.Enum):
    auto = "auto"
    manual = "manual"


class Classificacao(Base):
    __tablename__ = "classificacoes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("itens.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    flag: Mapped[FlagClassificacao] = mapped_column(Enum(FlagClassificacao, name="flag_classificacao"))
    origem: Mapped[OrigemClassificacao] = mapped_column(Enum(OrigemClassificacao, name="origem_classificacao"))
    justificativa: Mapped[str | None] = mapped_column(Text, nullable=True)
    fontes: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    procedimento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("procedimentos.id", ondelete="SET NULL"), nullable=True
    )
    # Nome do modelo do Gemini que de fato classificou o item (só em classificações automáticas
    # — override manual não chama o Gemini, então fica nulo). Mesma motivação de Poc.modelo_extracao.
    modelo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    item: Mapped["Item"] = relationship(back_populates="classificacao")
    procedimento: Mapped[Procedimento | None] = relationship()


class VeredictoRfi(str, enum.Enum):
    atende = "atende"
    atende_parcial = "atende_parcial"
    nao_atende = "nao_atende"
    sem_evidencia = "sem_evidencia"


class Rfi(Base):
    """Análise de TR/edital contra o portfólio SUSE (ver app/rfi/). Não tem relação com Poc —
    é uma triagem de requisitos de um documento de licitação, não a execução de uma PoC."""

    __tablename__ = "rfis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    titulo: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    orgao: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    numero_processo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nome_arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    caminho_arquivo: Mapped[str] = mapped_column(String(500), nullable=False)
    # Reaproveita o enum status_extracao (já existe pra Poc) -- cobre só a fase de extração dos
    # itens; o progresso da busca web item a item é inferido no front a partir de quantos
    # RfiItem já têm veredito != null (ver RfiItem.veredito), sem precisar de um status novo.
    status_extracao: Mapped[StatusExtracao] = mapped_column(
        Enum(StatusExtracao, name="status_extracao"), default=StatusExtracao.extraindo
    )
    erro_extracao: Mapped[str | None] = mapped_column(Text, nullable=True)
    modelo_extracao: Mapped[str | None] = mapped_column(String(100), nullable=True)
    criado_por_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Duas chaves para users (criador e responsável): a relação do criador diz qual delas usa.
    criado_por: Mapped["User"] = relationship(foreign_keys=[criado_por_id])
    responsavel: Mapped["User | None"] = relationship(foreign_keys=[responsavel_id])
    itens: Mapped[list["RfiItem"]] = relationship(
        back_populates="rfi", cascade="all, delete-orphan", order_by="RfiItem.ordem"
    )


class RfiItem(Base):
    __tablename__ = "rfi_itens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rfi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfis.id", ondelete="CASCADE"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    categoria: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Código da taxonomia fixa (app/categorias.py) -- ver Item.categoria_codigo. Usado para
    # restringir a busca de procedimento interno antes da pesquisa web (app/rfi/service.py).
    categoria_codigo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    # Nulo até a busca web rodar pra este item (ver app/rfi/service.py::avaliar_item_rfi) -- é
    # assim que o front sabe que ainda está em processamento, igual ao polling que
    # classificar_pendentes já faz em app/classificacao/tasks.py.
    veredito: Mapped[VeredictoRfi | None] = mapped_column(Enum(VeredictoRfi, name="veredito_rfi"), nullable=True)
    justificativa: Mapped[str | None] = mapped_column(Text, nullable=True)
    fontes: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    origem: Mapped[OrigemClassificacao | None] = mapped_column(
        Enum(OrigemClassificacao, name="origem_classificacao"), nullable=True
    )
    # Preenchido quando um procedimento validado interno (não a web) confirma o atendimento --
    # ver app/rfi/service.py::avaliar_item_rfi. SET NULL se o procedimento for excluído depois.
    procedimento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("procedimentos.id", ondelete="SET NULL"), nullable=True
    )
    modelo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    rfi: Mapped[Rfi] = relationship(back_populates="itens")
    procedimento: Mapped[Procedimento | None] = relationship()


class Prerequisito(Base):
    __tablename__ = "poc_prerequisitos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    poc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pocs.id", ondelete="CASCADE"), nullable=False
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    atendido: Mapped[bool] = mapped_column(Boolean, default=False)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    poc: Mapped[Poc] = relationship(back_populates="prerequisitos")


class Sessao(Base):
    __tablename__ = "sessoes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    poc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pocs.id", ondelete="CASCADE"), nullable=False
    )
    data: Mapped[date] = mapped_column(Date, nullable=False)
    participantes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    agenda: Mapped[str | None] = mapped_column(Text, nullable=True)
    resumo_bruto: Mapped[str | None] = mapped_column(Text, nullable=True)
    pontos_resolvidos: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    pontos_falha: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    proximos_passos: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    poc: Mapped[Poc] = relationship(back_populates="sessoes")


class Nota(Base):
    __tablename__ = "notas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("itens.id", ondelete="CASCADE"), nullable=False
    )
    # Opcional: a nota nasce no item (aba Plano de testes) e só eventualmente é associada a
    # uma sessão depois — ver Andamento, que já agrupa pelo bucket "sem sessão vinculada".
    sessao_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessoes.id", ondelete="SET NULL"), nullable=True
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    item: Mapped["Item"] = relationship(back_populates="notas")
    sessao: Mapped[Sessao] = relationship()


class Anexo(Base):
    __tablename__ = "anexos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("itens.id", ondelete="CASCADE"), nullable=False
    )
    sessao_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessoes.id", ondelete="SET NULL"), nullable=True
    )
    nome_arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    caminho_arquivo: Mapped[str] = mapped_column(String(500), nullable=False)
    # Preenchido quando o usuário marca "Validado" nesse anexo: o conteúdo dele (HTML ou texto)
    # foi promovido a um Procedimento na biblioteca — ver app/pocs/router.py::validar_anexo.
    procedimento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("procedimentos.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    item: Mapped["Item"] = relationship(back_populates="anexos")
    sessao: Mapped[Sessao | None] = relationship()


class StatusHistorico(Base):
    __tablename__ = "status_historico"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("itens.id", ondelete="CASCADE"), nullable=False
    )
    sessao_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessoes.id", ondelete="SET NULL"), nullable=True
    )
    status_anterior: Mapped[StatusItem | None] = mapped_column(
        Enum(StatusItem, name="status_item"), nullable=True
    )
    status_novo: Mapped[StatusItem] = mapped_column(Enum(StatusItem, name="status_item"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    item: Mapped["Item"] = relationship(back_populates="status_historico")
    sessao: Mapped[Sessao | None] = relationship()


class ResultadoCatalogo(Base):
    """Histórico anônimo de resultados por teste do catálogo do planejador (ADR 1). Uma linha por (PoC, teste do
    catálogo) com resultado terminal. NÃO é apagada em cascata: `poc_id` vira nulo quando a PoC é excluída e o resultado
    continua valendo para a viabilidade por histórico. Por isso não guarda cliente, título, dono nem texto livre."""

    __tablename__ = "resultados_catalogo"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    catalogo_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    resultado: Mapped[ResultadoItem] = mapped_column(
        Enum(ResultadoItem, name="resultado_item", values_callable=_valores), nullable=False
    )
    aderencia: Mapped[AderenciaItem | None] = mapped_column(
        Enum(AderenciaItem, name="aderencia_item", values_callable=_valores), nullable=True
    )
    # "Executado sem problemas": resultado = pass e nenhuma transição do item para `bloqueado`.
    sucesso: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Primeiro dia do mês da execução: só o mês é guardado, pra dificultar ligar a linha anônima a uma PoC (ADR 1).
    executado_em: Mapped[date] = mapped_column(Date, nullable=False)
    poc_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pocs.id", ondelete="SET NULL"), nullable=True
    )


class Exclusao(Base):
    """Registro de auditoria de uma exclusão permanente (ADR 4): tipo, quem, quando, o título e as contagens do que foi
    removido. Deliberadamente SEM nome de cliente e sem conteúdo."""

    __tablename__ = "exclusoes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)
    excluido_por_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    excluido_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    contagens: Mapped[dict] = mapped_column(JSONB, default=dict)
