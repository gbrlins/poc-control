import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status as http_status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import exclusao as excl
from app.categorias import normalizar
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
    categorias: list[str] | None = None,
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
        categorias=sorted({c for c in (normalizar(c) for c in (categorias or [])) if c}),
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
    categorias: str = Form(""),
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
        categorias=_parse_tags(categorias),
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


def _get_procedimento_or_404(db: Session, procedimento_id: uuid.UUID) -> Procedimento:
    procedimento = db.get(Procedimento, procedimento_id)
    if procedimento is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Procedimento não encontrado")
    return procedimento


@router.get("/{procedimento_id}", response_model=ProcedimentoDetail)
def obter_procedimento(procedimento_id: uuid.UUID, db: Session = Depends(get_db)):
    procedimento = _get_procedimento_or_404(db, procedimento_id)

    return ProcedimentoDetail(
        **ProcedimentoListItem.model_validate(procedimento).model_dump(),
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


class ResponsavelIn(BaseModel):
    responsavel_id: uuid.UUID


class ExclusaoIn(BaseModel):
    confirmar: str


@router.put("/{procedimento_id}/responsavel")
def definir_responsavel(
    procedimento_id: uuid.UUID,
    payload: ResponsavelIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mesmas regras da PoC/RFI (ADR 4): o dono transfere, um procedimento sem dono pode ser assumido, o administrador reatribui."""
    procedimento = _get_procedimento_or_404(db, procedimento_id)
    novo = db.get(User, payload.responsavel_id)
    if novo is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Usuário não encontrado")
    if not excl.pode_atribuir(current_user, procedimento, novo.id):
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            "Só o dono (ou um administrador) altera o responsável; um procedimento sem dono pode ser assumido.",
        )
    procedimento.responsavel_id = novo.id
    db.commit()
    return {"id": procedimento.id, "responsavel_id": procedimento.responsavel_id}


@router.get("/{procedimento_id}/exclusao")
def previa_exclusao(
    procedimento_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """O que uma exclusão removeria e o que ficaria (para a tela de confirmação). Não altera nada."""
    return excl.previa(db, current_user, "procedimento", _get_procedimento_or_404(db, procedimento_id))


@router.delete("/{procedimento_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def excluir_procedimento(
    procedimento_id: uuid.UUID,
    payload: ExclusaoIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exclusão PERMANENTE (ADR 4): só o dono, com o título digitado em `confirmar`. Classificações,
    anexos validados e vereditos de RFI que citavam este procedimento só perdem o vínculo (SET NULL)."""
    procedimento = _get_procedimento_or_404(db, procedimento_id)
    try:
        excl.excluir(db, current_user, "procedimento", procedimento, payload.confirmar)
    except excl.ExclusaoErro as e:
        raise HTTPException(e.status, e.mensagem)
