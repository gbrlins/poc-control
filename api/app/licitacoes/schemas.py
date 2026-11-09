import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class LicitacaoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero_controle_pncp: str
    orgao_nome: str
    orgao_cnpj: str
    unidade_nome: str | None
    uf: str | None
    municipio: str | None
    objeto: str
    modalidade_codigo: int
    modalidade_nome: str | None
    valor_estimado: float | None
    data_publicacao: date
    data_abertura_proposta: datetime | None
    data_encerramento_proposta: datetime | None
    termos_encontrados: list[str]
    link_pncp: str
    created_at: datetime


class TermoBuscaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    termo: str
    categoria_codigo: str | None
    ativo: bool
    created_at: datetime


class TermoBuscaIn(BaseModel):
    termo: str
    categoria_codigo: str | None = None


class AtualizarLicitacoesOut(BaseModel):
    novas: int
