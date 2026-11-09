import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import OrigemClassificacao, StatusExtracao, VeredictoRfi
from app.pocs.schemas import FonteOut


class RfiDocumentoOut(BaseModel):
    id: uuid.UUID
    nome_arquivo: str
    created_at: datetime
    total_itens: int
    itens_manuais: int  # itens com veredito sobrescrito à mão -- somem junto se o documento for removido


class RfiItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    documento_id: uuid.UUID | None = None
    codigo: str
    categoria: str | None
    categoria_codigo: str | None = None
    descricao: str
    ordem: int
    veredito: VeredictoRfi | None
    justificativa: str | None
    fontes: list[FonteOut]
    origem: OrigemClassificacao | None
    procedimento_id: uuid.UUID | None = None
    confirmado_por_historico: bool = False
    etapa: str | None = None
    modelo: str | None
    created_at: datetime


class RfiItemManualUpdate(BaseModel):
    veredito: VeredictoRfi
    justificativa: str | None = None


class ContagemVeredito(BaseModel):
    atende: int = 0
    atende_parcial: int = 0
    nao_atende: int = 0
    sem_evidencia: int = 0


class RfiListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titulo: str
    orgao: str
    numero_processo: str | None
    status_extracao: StatusExtracao
    criado_por_email: str
    created_at: datetime
    processamento_iniciado_em: datetime | None = None
    progresso: dict | None = None
    cancelamento_solicitado: bool = False
    total_itens: int
    itens_avaliados: int
    # % de itens com veredito "atende" sobre o total (não só os avaliados -- fórmula escolhida
    # pelo usuário); None quando o RFI ainda não tem nenhum item. Atualiza ao vivo durante a
    # avaliação, já que o denominador é o total e não só os itens já avaliados.
    score: float | None = None
    contagem_veredito: ContagemVeredito | None = None
    responsavel_id: uuid.UUID | None = None
    responsavel_email: str | None = None


class RfiDetail(RfiListItem):
    erro_extracao: str | None
    modelo_extracao: str | None
    documentos: list[RfiDocumentoOut]
    itens: list[RfiItemOut]
