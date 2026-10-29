import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models import (
    AderenciaItem,
    AderenciaOrigem,
    CondicaoItem,
    FlagClassificacao,
    OrigemClassificacao,
    PrioridadeItem,
    ResultadoItem,
    StatusExtracao,
    StatusItem,
    StatusPoc,
)


class FaseOut(BaseModel):
    numero: int
    titulo: str
    descricao: str


class PrerequisitoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titulo: str
    descricao: str | None
    atendido: bool
    ordem: int


class PrerequisitoUpdate(BaseModel):
    atendido: bool


class FonteOut(BaseModel):
    titulo: str
    url: str


class ClassificacaoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    flag: FlagClassificacao
    origem: OrigemClassificacao
    justificativa: str | None
    fontes: list[FonteOut]
    procedimento_id: uuid.UUID | None
    modelo: str | None
    created_at: datetime


class ClassificacaoManualUpdate(BaseModel):
    flag: FlagClassificacao
    procedimento_id: uuid.UUID | None = None
    justificativa: str | None = None


class SessaoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    data: date
    participantes: list[str]
    agenda: str | None
    resumo_bruto: str | None
    pontos_resolvidos: list[str]
    pontos_falha: list[str]
    proximos_passos: list[str]
    created_at: datetime


class SessaoCreate(BaseModel):
    data: date
    participantes: list[str] = []
    agenda: str | None = None


class SessaoImportar(BaseModel):
    texto: str


class NotaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sessao_id: uuid.UUID | None
    texto: str
    created_at: datetime


class NotaCreate(BaseModel):
    sessao_id: uuid.UUID | None = None
    texto: str


class AnexoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sessao_id: uuid.UUID | None
    nome_arquivo: str
    procedimento_id: uuid.UUID | None
    created_at: datetime


class StatusHistoricoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sessao_id: uuid.UUID | None
    status_anterior: StatusItem | None
    status_novo: StatusItem
    created_at: datetime


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    titulo: str
    descricao: str | None
    criterio_aceite: str | None
    categoria: str | None
    categoria_codigo: str | None = None
    fase: int
    ref: str | None
    conducao: CondicaoItem | None
    status: StatusItem
    ordem: int
    catalogo_id: str | None = None
    planner_id: str | None = None
    resultado: ResultadoItem | None = None
    prioridade: PrioridadeItem | None = None
    aderencia: AderenciaItem | None = None
    aderencia_origem: AderenciaOrigem | None = None
    responsavel: str | None = None
    classificacao: ClassificacaoOut | None
    notas: list[NotaOut]
    anexos: list[AnexoOut]
    status_historico: list[StatusHistoricoOut]


class ItemUpdate(BaseModel):
    titulo: str | None = None
    descricao: str | None = None
    criterio_aceite: str | None = None
    categoria: str | None = None
    categoria_codigo: str | None = None
    fase: int | None = None
    ref: str | None = None
    conducao: CondicaoItem | None = None
    status: StatusItem | None = None
    resultado: ResultadoItem | None = None
    prioridade: PrioridadeItem | None = None
    aderencia: AderenciaItem | None = None
    aderencia_origem: AderenciaOrigem | None = None
    responsavel: str | None = None
    sessao_id: uuid.UUID | None = None


class PocListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titulo: str
    cliente: str
    status: StatusPoc
    status_extracao: StatusExtracao
    created_at: datetime
    total_itens: int
    itens_concluidos: int
    responsavel_id: uuid.UUID | None = None
    responsavel_email: str | None = None


class PocDetail(PocListItem):
    escopo: str | None
    erro_extracao: str | None
    modelo_extracao: str | None
    resumo_executivo: str | None
    parametros_tecnicos: dict | None
    fases: list[FaseOut]
    itens: list[ItemOut]
    prerequisitos: list[PrerequisitoOut]
    sessoes: list[SessaoOut]


class ResumoExecutivoUpdate(BaseModel):
    resumo_executivo: str
