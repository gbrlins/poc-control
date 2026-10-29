import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status as http_status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.gemini import embed_document
from app.gemini_key import resolve_api_key
from app.models import Procedimento, ProcedimentoChunk, StatusProcedimento, User
from app.procedimentos.html_processing import extrair_secoes
from app.procedimentos.schemas import ProcedimentoDetail, ProcedimentoListItem, SecaoOut

router = APIRouter(
    prefix="/api/procedimentos", tags=["procedimentos"], dependencies=[Depends(get_current_user)]
)


def _criar_procedimento(
    db: Session,
    *,
    titulo: str,
    tags: list[str],
    cliente_origem: str | None,
    data_origem: date | None,
    status_valor: StatusProcedimento,
    versao: int,
    html: str,
    api_key: str | None = None,
    dono_id: uuid.UUID | None = None,
) -> Procedimento:
    secoes = extrair_secoes(html)
    if not secoes:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Nenhuma seção encontrada no HTML")

    procedimento = Procedimento(
        titulo=titulo,
        tags=tags,
        cliente_origem=cliente_origem,
        data_origem=data_origem,
        status=status_valor,
        versao=versao,
        html_original=html,
        criado_por_id=dono_id,
        responsavel_id=dono_id,
    )
    db.add(procedimento)

    for secao in secoes:
        embedding = embed_document(secao.content_text, api_key=api_key)
        db.add(
            ProcedimentoChunk(
                procedimento=procedimento,
                heading_level=secao.heading_level,
                heading_title=secao.heading_title,
                parent_heading_title=secao.parent_heading_title,
                order_index=secao.order_index,
                content_text=secao.content_text,
                embedding=embedding,
            )
        )

    db.commit()
    return procedimento


def _parse_tags(tags: str) -> list[str]:
    return [t.strip() for t in tags.split(",") if t.strip()]


@router.post("", response_model=ProcedimentoListItem, status_code=http_status.HTTP_201_CREATED)
def criar_procedimento(
    titulo: str = Form(...),
    tags: str = Form(""),
    cliente_origem: str | None = Form(None),
    data_origem: date | None = Form(None),
    status: str = Form("rascunho"),
    versao: int = Form(1),
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        status_valor = StatusProcedimento(status)
    except ValueError:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "status inválido")

    html = (arquivo.file.read()).decode("utf-8")

    procedimento = _criar_procedimento(
        db,
        titulo=titulo,
        tags=_parse_tags(tags),
        cliente_origem=cliente_origem,
        data_origem=data_origem,
        status_valor=status_valor,
        versao=versao,
        html=html,
        api_key=resolve_api_key(current_user),
        dono_id=current_user.id,
    )
    return procedimento


@router.get("", response_model=list[ProcedimentoListItem])
def listar_procedimentos(db: Session = Depends(get_db)):
    return db.query(Procedimento).order_by(Procedimento.created_at.desc()).all()


@router.get("/{procedimento_id}", response_model=ProcedimentoDetail)
def obter_procedimento(procedimento_id: uuid.UUID, db: Session = Depends(get_db)):
    procedimento = db.get(Procedimento, procedimento_id)
    if procedimento is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Procedimento não encontrado")

    return ProcedimentoDetail(
        id=procedimento.id,
        titulo=procedimento.titulo,
        tags=procedimento.tags,
        cliente_origem=procedimento.cliente_origem,
        status=procedimento.status,
        versao=procedimento.versao,
        data_origem=procedimento.data_origem,
        created_at=procedimento.created_at,
        html_original=procedimento.html_original,
        secoes=[
            SecaoOut(
                heading_level=c.heading_level,
                heading_title=c.heading_title,
                parent_heading_title=c.parent_heading_title,
                order_index=c.order_index,
            )
            for c in procedimento.chunks
        ],
    )
