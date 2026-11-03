import logging
import uuid
from datetime import date
from html import escape as _escapar_html

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status as http_status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import exclusao as excl
from app.categorias import normalizar
from app.db import get_db
from app.deps import get_current_user
from app.gemini import embed_document, traduzir_procedimento_html
from app.gemini_key import resolve_api_key
from app.models import OrigemConhecimento, Procedimento, ProcedimentoChunk, StatusProcedimento, User
from app.procedimentos.html_processing import extrair_secoes
from app.procedimentos.schemas import ProcedimentoDetail, ProcedimentoListItem, SecaoOut

logger = logging.getLogger(__name__)

_IDIOMAS_SITE = ("pt", "en", "es")

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
    origem: OrigemConhecimento = OrigemConhecimento.manual,
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
        origem_conhecimento=origem,
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

    # Tradução ansiosa só pro inglês (as outras duas ficam preguiçosas, sob demanda -- ver
    # _html_no_idioma): cobre o pedido mais provável de quem não leu o original em português, sem
    # gastar Gemini com um idioma que ninguém chegue a abrir. Nunca derruba o upload: se falhar
    # (rede, quota), fica pra tentar de novo na primeira visualização.
    try:
        traducao = traduzir_procedimento_html(html, "en", api_key=api_key)
        if traducao.idioma_detectado in _IDIOMAS_SITE:
            procedimento.idioma_original = traducao.idioma_detectado
        if procedimento.idioma_original != "en":
            procedimento.traducoes = {"en": traducao.html_traduzido}
    except Exception:
        logger.warning("Falha ao traduzir procedimento %r para inglês no upload", titulo, exc_info=True)

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


def _html_no_idioma(
    db: Session, procedimento: Procedimento, lang: str, *, api_key: str | None
) -> tuple[str, str | None]:
    """Resolve o HTML a exibir no idioma pedido: html_original se já é esse idioma, uma tradução
    já em cache (Procedimento.traducoes), ou traduz agora e guarda pra próxima vez. Nunca falha a
    página por causa de tradução: se o Gemini falhar, devolve html_original e o idioma real que
    está sendo mostrado, pra UI avisar em vez de quebrar."""
    if procedimento.idioma_original == lang:
        return procedimento.html_original, lang

    cacheado = (procedimento.traducoes or {}).get(lang)
    if cacheado:
        return cacheado, lang

    try:
        traducao = traduzir_procedimento_html(procedimento.html_original, lang, api_key=api_key)
    except Exception:
        logger.warning("Falha ao traduzir procedimento %s para %s", procedimento.id, lang, exc_info=True)
        return procedimento.html_original, procedimento.idioma_original

    if traducao.idioma_detectado in _IDIOMAS_SITE:
        procedimento.idioma_original = traducao.idioma_detectado
    if procedimento.idioma_original == lang:
        db.commit()
        return procedimento.html_original, lang

    traducoes = dict(procedimento.traducoes or {})
    traducoes[lang] = traducao.html_traduzido
    procedimento.traducoes = traducoes
    db.commit()
    return traducao.html_traduzido, lang


@router.get("/{procedimento_id}", response_model=ProcedimentoDetail)
def obter_procedimento(
    procedimento_id: uuid.UUID,
    lang: str = "pt",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    procedimento = _get_procedimento_or_404(db, procedimento_id)
    if lang not in _IDIOMAS_SITE:
        lang = "pt"
    html, idioma_conteudo = _html_no_idioma(db, procedimento, lang, api_key=resolve_api_key(current_user))

    return ProcedimentoDetail(
        **ProcedimentoListItem.model_validate(procedimento).model_dump(),
        html_original=procedimento.html_original,
        idioma_original=procedimento.idioma_original,
        idioma_conteudo=idioma_conteudo,
        html=html,
        secoes=[
            SecaoOut(
                heading_level=s.heading_level,
                heading_title=s.heading_title,
                parent_heading_title=s.parent_heading_title,
                order_index=s.order_index,
            )
            for s in extrair_secoes(html)
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
