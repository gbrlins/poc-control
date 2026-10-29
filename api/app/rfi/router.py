import pathlib
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import exclusao as excl
from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.gemini_key import resolve_api_key, resolve_model
from app.models import OrigemClassificacao, Rfi, RfiItem, StatusExtracao, User
from app.pocs.planilha_import import texto_de_planilha
from app.rfi.documento_import import texto_de_docx
from app.rfi.export import montar_rfi_export_html, montar_rfi_export_xlsx
from app.rfi.schemas import RfiDetail, RfiItemManualUpdate, RfiItemOut, RfiListItem
from app.rfi.service import avaliar_item_rfi
from app.rfi.tasks import processar_rfi

router = APIRouter(prefix="/api/rfis", tags=["rfis"], dependencies=[Depends(get_current_user)])


def _contar_itens(db: Session, rfi_id: uuid.UUID) -> tuple[int, int]:
    total = db.query(func.count(RfiItem.id)).filter(RfiItem.rfi_id == rfi_id).scalar() or 0
    avaliados = (
        db.query(func.count(RfiItem.id))
        .filter(RfiItem.rfi_id == rfi_id, RfiItem.veredito.is_not(None))
        .scalar()
        or 0
    )
    return total, avaliados


def _list_item(db: Session, rfi: Rfi) -> RfiListItem:
    total, avaliados = _contar_itens(db, rfi.id)
    return RfiListItem(
        id=rfi.id,
        titulo=rfi.titulo,
        orgao=rfi.orgao,
        numero_processo=rfi.numero_processo,
        status_extracao=rfi.status_extracao,
        criado_por_email=rfi.criado_por.email,
        created_at=rfi.created_at,
        total_itens=total,
        itens_avaliados=avaliados,
        responsavel_id=rfi.responsavel_id,
        responsavel_email=rfi.responsavel.email if rfi.responsavel else None,
    )


def _get_rfi_or_404(db: Session, rfi_id: uuid.UUID) -> Rfi:
    rfi = db.get(Rfi, rfi_id)
    if rfi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "RFI não encontrado")
    return rfi


def _get_item_or_404(db: Session, rfi_id: uuid.UUID, item_id: uuid.UUID) -> RfiItem:
    item = db.get(RfiItem, item_id)
    if item is None or item.rfi_id != rfi_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item não encontrado")
    return item


@router.get("", response_model=list[RfiListItem])
def listar_rfis(db: Session = Depends(get_db)):
    # Sem filtro de usuário/data no backend -- a lista inteira é pequena (triagem de editais,
    # não um fluxo de alto volume) e o front filtra em memória (ver web/src/features/rfi).
    rfis = db.query(Rfi).order_by(Rfi.created_at.desc()).all()
    return [_list_item(db, rfi) for rfi in rfis]


@router.post("", response_model=RfiListItem, status_code=status.HTTP_201_CREATED)
def criar_rfi(
    background_tasks: BackgroundTasks,
    titulo: str = Form(""),
    orgao: str = Form(""),
    arquivo: UploadFile | None = File(None),
    texto: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Título/órgão são opcionais aqui (diferente de criar_poc): a extração já tenta sugeri-los
    # a partir do próprio documento (ver app/rfi/tasks.py::processar_rfi).
    pdf_bytes: bytes | None = None
    planilha_bytes: bytes | None = None
    nome_arquivo: str | None = None
    texto_arquivo: str | None = None

    if arquivo is not None and arquivo.filename:
        conteudo = arquivo.file.read()
        if not conteudo:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Arquivo vazio")
        nome_arquivo = arquivo.filename
        extensao = pathlib.Path(nome_arquivo).suffix.lower()
        if extensao == ".pdf":
            pdf_bytes = conteudo
        elif extensao in (".xlsx", ".csv"):
            try:
                texto_arquivo = texto_de_planilha(conteudo, extensao)
            except ValueError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
            planilha_bytes = conteudo
        elif extensao == ".docx":
            try:
                texto_arquivo = texto_de_docx(conteudo)
            except ValueError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
            planilha_bytes = conteudo
        else:
            try:
                texto_arquivo = conteudo.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Não foi possível ler o arquivo como texto; envie um PDF, um Word (.docx), uma "
                    "planilha XLSX/CSV, ou um arquivo de texto em UTF-8",
                )

    texto_final = (texto or "").strip() or texto_arquivo
    if not pdf_bytes and not texto_final:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Envie o documento do edital/TR, ou cole o texto")

    rfi = Rfi(
        titulo=titulo,
        orgao=orgao,
        status_extracao=StatusExtracao.extraindo,
        criado_por_id=current_user.id,
        responsavel_id=current_user.id,
        nome_arquivo="",
        caminho_arquivo="",
    )
    db.add(rfi)
    db.commit()
    db.refresh(rfi)

    rfi_dir = pathlib.Path(settings.uploads_dir) / "rfis" / str(rfi.id)
    rfi_dir.mkdir(parents=True, exist_ok=True)
    if pdf_bytes:
        nome = nome_arquivo or "rfi.pdf"
        caminho = rfi_dir / nome
        caminho.write_bytes(pdf_bytes)
    elif planilha_bytes:
        nome = nome_arquivo or "rfi-importado"
        caminho = rfi_dir / nome
        caminho.write_bytes(planilha_bytes)
    else:
        nome = nome_arquivo or "rfi-importado.txt"
        caminho = rfi_dir / nome
        caminho.write_text(texto_final, encoding="utf-8")

    rfi.nome_arquivo = nome
    rfi.caminho_arquivo = str(caminho)
    db.commit()

    background_tasks.add_task(
        processar_rfi, rfi.id, pdf_bytes, texto_final, resolve_api_key(current_user), resolve_model(current_user)
    )
    return _list_item(db, rfi)


@router.get("/{rfi_id}", response_model=RfiDetail)
def obter_rfi(rfi_id: uuid.UUID, db: Session = Depends(get_db)):
    rfi = _get_rfi_or_404(db, rfi_id)
    return RfiDetail(
        **_list_item(db, rfi).model_dump(),
        erro_extracao=rfi.erro_extracao,
        modelo_extracao=rfi.modelo_extracao,
        nome_arquivo=rfi.nome_arquivo,
        itens=[RfiItemOut.model_validate(i) for i in rfi.itens],
    )


@router.patch("/{rfi_id}/itens/{item_id}", response_model=RfiItemOut)
def sobrescrever_veredito(
    rfi_id: uuid.UUID, item_id: uuid.UUID, payload: RfiItemManualUpdate, db: Session = Depends(get_db)
):
    item = _get_item_or_404(db, rfi_id, item_id)
    item.veredito = payload.veredito
    item.justificativa = payload.justificativa
    item.origem = OrigemClassificacao.manual
    item.modelo = None
    db.commit()
    db.refresh(item)
    return item


@router.post("/{rfi_id}/itens/{item_id}/reavaliar", response_model=RfiItemOut)
def reavaliar_item(
    rfi_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = _get_item_or_404(db, rfi_id, item_id)
    avaliar_item_rfi(db, item, api_key=resolve_api_key(current_user), model=resolve_model(current_user))
    db.refresh(item)
    return item


@router.get("/{rfi_id}/export", response_class=HTMLResponse)
def exportar_rfi(rfi_id: uuid.UUID, db: Session = Depends(get_db)):
    rfi = _get_rfi_or_404(db, rfi_id)
    return HTMLResponse(montar_rfi_export_html(rfi))


@router.get("/{rfi_id}/export.xlsx")
def exportar_rfi_xlsx(rfi_id: uuid.UUID, db: Session = Depends(get_db)):
    rfi = _get_rfi_or_404(db, rfi_id)
    conteudo = montar_rfi_export_xlsx(rfi)
    nome = f"rfi-{rfi.titulo or rfi.id}.xlsx".replace("/", "-")
    return Response(
        content=conteudo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


class ResponsavelIn(BaseModel):
    responsavel_id: uuid.UUID


class ExclusaoIn(BaseModel):
    confirmar: str


@router.put("/{rfi_id}/responsavel")
def definir_responsavel(
    rfi_id: uuid.UUID,
    payload: ResponsavelIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mesmas regras da PoC (ADR 4): o dono transfere, uma RFI sem dono pode ser assumida, o administrador reatribui."""
    rfi = _get_rfi_or_404(db, rfi_id)
    novo = db.get(User, payload.responsavel_id)
    if novo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado")
    if not excl.pode_atribuir(current_user, rfi, novo.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Só o dono (ou um administrador) altera o responsável; uma RFI sem dono pode ser assumida.")
    rfi.responsavel_id = novo.id
    db.commit()
    return {"id": rfi.id, "responsavel_id": rfi.responsavel_id}


@router.get("/{rfi_id}/exclusao")
def previa_exclusao(rfi_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return excl.previa(db, current_user, "rfi", _get_rfi_or_404(db, rfi_id))


@router.delete("/{rfi_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_rfi(
    rfi_id: uuid.UUID,
    payload: ExclusaoIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exclusão PERMANENTE (ADR 4): só o dono, com o título digitado em `confirmar`."""
    rfi = _get_rfi_or_404(db, rfi_id)
    try:
        excl.excluir(db, current_user, "rfi", rfi, payload.confirmar)
    except excl.ExclusaoErro as e:
        raise HTTPException(e.status, e.mensagem)
