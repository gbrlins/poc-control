import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models import OrigemConhecimento, StatusProcedimento


class SecaoOut(BaseModel):
    heading_level: int
    heading_title: str
    parent_heading_title: str | None
    order_index: int


class ProcedimentoListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titulo: str
    tags: list[str]
    categorias: list[str]
    cliente_origem: str | None
    status: StatusProcedimento
    origem_conhecimento: OrigemConhecimento = OrigemConhecimento.manual
    gerado_por_ia: bool = False
    versao: int
    data_origem: date | None
    created_at: datetime
    responsavel_id: uuid.UUID | None = None
    responsavel_email: str | None = None
    criado_por_email: str | None = None


class ProcedimentoDetail(ProcedimentoListItem):
    html_original: str
    idioma_original: str | None = None
    # Idioma real do campo `html` abaixo: igual ao idioma pedido (?lang=) quando a tradução deu
    # certo (ou já era o idioma original); cai pro idioma_original se a tradução sob demanda
    # falhar, pra UI avisar que está mostrando outro idioma em vez de quebrar a página.
    idioma_conteudo: str | None = None
    html: str
    secoes: list[SecaoOut]
