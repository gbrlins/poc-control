import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import OrigemClassificacao, StatusExtracao, VeredictoRfi
from app.pocs.schemas import FonteOut


class RfiItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    categoria: str | None
    descricao: str
    ordem: int
    veredito: VeredictoRfi | None
    justificativa: str | None
    fontes: list[FonteOut]
    origem: OrigemClassificacao | None
    modelo: str | None
    created_at: datetime


class RfiItemManualUpdate(BaseModel):
    veredito: VeredictoRfi
    justificativa: str | None = None


class RfiListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titulo: str
    orgao: str
    numero_processo: str | None
    status_extracao: StatusExtracao
    criado_por_email: str
    created_at: datetime
    total_itens: int
    itens_avaliados: int
    responsavel_id: uuid.UUID | None = None


class RfiDetail(RfiListItem):
    erro_extracao: str | None
    modelo_extracao: str | None
    nome_arquivo: str
    itens: list[RfiItemOut]
