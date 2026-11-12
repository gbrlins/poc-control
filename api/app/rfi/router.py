import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import exclusao as excl
from app.classificacao.service import atualizar_embedding_historico_rfi
from app.db import get_db
from app.deps import get_current_user
from app.gemini import interpretar_erro_gemini
from app.gemini_key import resolve_api_key, resolve_model
from app.models import OrigemClassificacao, Rfi, RfiDocumento, RfiItem, StatusExtracao, User
from app.rfi.documentos import TEXTO_COLADO_NOME, ler_conteudo, remover_arquivo, salvar_documento
from app.rfi.export import montar_rfi_export_html, montar_rfi_export_xlsx
from app.rfi.schemas import ContagemVeredito, RfiDetail, RfiDocumentoOut, RfiItemManualUpdate, RfiItemOut, RfiListItem
from app.rfi.service import avaliar_item_rfi
from app.rfi.tasks import iniciar_processamento, processar_rfi, reavaliar_rfi

router = APIRouter(prefix="/api/rfis", tags=["rfis"], dependencies=[Depends(get_current_user)])


def _contar_itens(db: Session, rfi_id: uuid.UUID) -> tuple[int, int, float | None, ContagemVeredito]:
    total = db.query(func.count(RfiItem.id)).filter(RfiItem.rfi_id == rfi_id).scalar() or 0
    avaliados = (
        db.query(func.count(RfiItem.id))
        .filter(RfiItem.rfi_id == rfi_id, RfiItem.veredito.is_not(None))
        .scalar()
        or 0
    )
    linhas = (
        db.query(RfiItem.veredito, func.count(RfiItem.id))
        .filter(RfiItem.rfi_id == rfi_id, RfiItem.veredito.is_not(None))
        .group_by(RfiItem.veredito)
        .all()
    )
    contagem = ContagemVeredito()
    for veredito, n in linhas:
        setattr(contagem, veredito.value, n)
    score = round(100 * contagem.atende / total, 1) if total > 0 else None
    return total, avaliados, score, contagem


def _list_item(db: Session, rfi: Rfi) -> RfiListItem:
    total, avaliados, score, contagem = _contar_itens(db, rfi.id)
    return RfiListItem(
        id=rfi.id,
        titulo=rfi.titulo,
        orgao=rfi.orgao,
        numero_processo=rfi.numero_processo,
        status_extracao=rfi.status_extracao,
        criado_por_email=rfi.criado_por.email,
        created_at=rfi.created_at,
        processamento_iniciado_em=rfi.processamento_iniciado_em,
        progresso=rfi.progresso,
        cancelamento_solicitado=rfi.cancelamento_solicitado,
        total_itens=total,
        itens_avaliados=avaliados,
        score=score,
        contagem_veredito=contagem,
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


def _ler_uploads(arquivos: list[UploadFile] | None, texto: str | None) -> list[tuple[str, bytes]]:
    """Valida cada arquivo (e o texto colado, que vira mais um documento) ANTES de gravar qualquer
    coisa, pra um arquivo ruim não deixar um RFI pela metade."""
    docs: list[tuple[str, bytes]] = []
    for arq in arquivos or []:
        if not arq.filename:
            continue
        conteudo = arq.file.read()
        try:
            ler_conteudo(arq.filename, conteudo)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        docs.append((arq.filename, conteudo))
    if (texto or "").strip():
        docs.append((TEXTO_COLADO_NOME, texto.strip().encode("utf-8")))
    return docs


def _exigir_ocioso(rfi: Rfi) -> None:
    if rfi.status_extracao == StatusExtracao.extraindo:
        raise HTTPException(status.HTTP_409_CONFLICT, "O RFI ainda está sendo processado; aguarde terminar")


def _documento_out(db: Session, doc: RfiDocumento) -> RfiDocumentoOut:
    total = db.query(func.count(RfiItem.id)).filter(RfiItem.documento_id == doc.id).scalar() or 0
    manuais = (
        db.query(func.count(RfiItem.id))
        .filter(RfiItem.documento_id == doc.id, RfiItem.origem == OrigemClassificacao.manual)
        .scalar()
        or 0
    )
    return RfiDocumentoOut(
        id=doc.id, nome_arquivo=doc.nome_arquivo, created_at=doc.created_at, total_itens=total, itens_manuais=manuais
    )


@router.post("", response_model=RfiListItem, status_code=status.HTTP_201_CREATED)
def criar_rfi(
    background_tasks: BackgroundTasks,
    titulo: str = Form(""),
    orgao: str = Form(""),
    arquivos: list[UploadFile] | None = File(None),
    texto: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Título/órgão são opcionais aqui (diferente de criar_poc): a extração já tenta sugeri-los
    # a partir do próprio documento (ver app/rfi/tasks.py::processar_rfi).
    docs = _ler_uploads(arquivos, texto)
    if not docs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Envie o(s) documento(s) do edital/TR, ou cole o texto")

    rfi = Rfi(
        titulo=titulo,
        orgao=orgao,
        criado_por_id=current_user.id,
        responsavel_id=current_user.id,
        nome_arquivo="",
        caminho_arquivo="",
    )
    iniciar_processamento(rfi)
    db.add(rfi)
    db.flush()
    criados = [salvar_documento(db, rfi, nome, conteudo) for nome, conteudo in docs]
    db.commit()
    db.refresh(rfi)

    background_tasks.add_task(
        processar_rfi, rfi.id, [d.id for d in criados], resolve_api_key(current_user), resolve_model(current_user)
    )
    return _list_item(db, rfi)


@router.get("/{rfi_id}", response_model=RfiDetail)
def obter_rfi(rfi_id: uuid.UUID, db: Session = Depends(get_db)):
    rfi = _get_rfi_or_404(db, rfi_id)
    return RfiDetail(
        **_list_item(db, rfi).model_dump(),
        erro_extracao=rfi.erro_extracao,
        modelo_extracao=rfi.modelo_extracao,
        documentos=[_documento_out(db, d) for d in rfi.documentos],
        itens=[RfiItemOut.model_validate(i) for i in rfi.itens],
    )


@router.post("/{rfi_id}/documentos", response_model=RfiListItem, status_code=status.HTTP_202_ACCEPTED)
def adicionar_documentos(
    rfi_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    arquivos: list[UploadFile] | None = File(None),
    texto: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Anexa documentos a um RFI existente: extrai e avalia só os itens NOVOS (os existentes, e
    qualquer veredito manual, ficam como estão)."""
    rfi = _get_rfi_or_404(db, rfi_id)
    _exigir_ocioso(rfi)
    docs = _ler_uploads(arquivos, texto)
    if not docs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Envie ao menos um documento, ou cole o texto")
    criados = [salvar_documento(db, rfi, nome, conteudo) for nome, conteudo in docs]
    iniciar_processamento(rfi)
    db.commit()
    background_tasks.add_task(
        processar_rfi, rfi.id, [d.id for d in criados], resolve_api_key(current_user), resolve_model(current_user)
    )
    return _list_item(db, rfi)


@router.post("/{rfi_id}/reextrair", status_code=status.HTTP_202_ACCEPTED)
def reextrair_rfi(
    rfi_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tenta de novo a extração de um RFI cujo status_extracao ficou 'erro' (ex.: todos os
    documentos falharam no Gemini, ou a recuperação de reinício marcou como erro -- ADR 7,
    app/recuperacao.py) -- mesmo espírito do reextrair_poc de app/pocs/router.py, mas só reprocessa
    documentos que ainda não geraram nenhum item: uma recuperação de reinício pode ter marcado
    `erro` com o 1º documento já bem-sucedido e o 2º interrompido no meio -- refazer o 1º
    duplicaria os itens dele."""
    rfi = _get_rfi_or_404(db, rfi_id)
    if rfi.status_extracao != StatusExtracao.erro:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Só é possível reprocessar um RFI cuja extração falhou")
    if not rfi.documentos:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este RFI não tem documento original para reprocessar")

    pendentes = [d for d in rfi.documentos if not any(i.documento_id == d.id for i in rfi.itens)]
    if not pendentes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            'Todos os documentos deste RFI já têm itens extraídos -- use "Reavaliar" nos itens pendentes',
        )

    iniciar_processamento(rfi)
    db.commit()
    background_tasks.add_task(
        processar_rfi, rfi.id, [d.id for d in pendentes], resolve_api_key(current_user), resolve_model(current_user)
    )
    return _list_item(db, rfi)


@router.delete("/{rfi_id}/documentos/{documento_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_documento(rfi_id: uuid.UUID, documento_id: uuid.UUID, db: Session = Depends(get_db)):
    """Remove o documento, o arquivo e TODOS os itens extraídos dele (inclusive os com veredito
    manual -- o front avisa antes, ver RfiDocumentoOut.itens_manuais)."""
    rfi = _get_rfi_or_404(db, rfi_id)
    _exigir_ocioso(rfi)
    doc = db.get(RfiDocumento, documento_id)
    if doc is None or doc.rfi_id != rfi_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado")
    # Remove os itens explicitamente (não só pelo ON DELETE CASCADE do banco): o ORM não tem
    # relationship Documento->Itens, então só assim a sessão fica consistente.
    db.query(RfiItem).filter(RfiItem.documento_id == doc.id).delete(synchronize_session=False)
    remover_arquivo(doc)
    db.delete(doc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{rfi_id}/cancelar", response_model=RfiListItem, status_code=status.HTTP_202_ACCEPTED)
def cancelar_processamento(rfi_id: uuid.UUID, db: Session = Depends(get_db)):
    """Pede a interrupção do processamento em andamento. A tarefa em background confere o pedido
    entre um passo e outro (documento, item) e para; uma chamada já em curso ao Gemini termina antes."""
    rfi = _get_rfi_or_404(db, rfi_id)
    if rfi.status_extracao != StatusExtracao.extraindo:
        raise HTTPException(status.HTTP_409_CONFLICT, "Não há processamento em andamento neste RFI")
    rfi.cancelamento_solicitado = True
    db.commit()
    return _list_item(db, rfi)


@router.post("/{rfi_id}/reavaliar", response_model=RfiListItem, status_code=status.HTTP_202_ACCEPTED)
def reavaliar_todos(
    rfi_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    incluir_manuais: bool = False,
    somente_pendentes: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reavalia todos os itens em background; por padrão preserva os vereditos sobrescritos à mão."""
    rfi = _get_rfi_or_404(db, rfi_id)
    _exigir_ocioso(rfi)
    iniciar_processamento(rfi)
    db.commit()
    background_tasks.add_task(
        reavaliar_rfi,
        rfi.id,
        incluir_manuais,
        resolve_api_key(current_user),
        resolve_model(current_user),
        somente_pendentes,
    )
    return _list_item(db, rfi)


@router.patch("/{rfi_id}/itens/{item_id}", response_model=RfiItemOut)
def sobrescrever_veredito(
    rfi_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: RfiItemManualUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = _get_item_or_404(db, rfi_id, item_id)
    item.veredito = payload.veredito
    item.justificativa = payload.justificativa
    item.origem = OrigemClassificacao.manual
    item.confirmado_por_historico = False
    item.modelo = None
    # Um "atende" marcado à mão vale tanto quanto um confirmado pelo Gemini pra alimentar a base
    # de histórico compartilhada (ver atualizar_embedding_historico_rfi, app/classificacao/
    # service.py) -- sem isto, só itens que passaram pela avaliação automática viravam evidência
    # buscável, e o conhecimento que o próprio usuário valida à mão (ex.: "isto aqui atende, eu
    # sei por experiência") nunca entrava pro ciclo de confirmar RFIs/PoCs futuros equivalentes.
    atualizar_embedding_historico_rfi(db, item, resolve_api_key(current_user))
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
    tinha_veredito = item.veredito is not None
    try:
        avaliar_item_rfi(db, item, api_key=resolve_api_key(current_user), model=resolve_model(current_user))
    except Exception as exc:
        if tinha_veredito:
            # avaliar_item_rfi preserva o veredito que já existia (uma falha do Gemini não pode
            # apagar uma resposta já confirmada) -- aqui devolve o erro de verdade pro usuário,
            # já que silenciosamente não fazer nada deixaria o botão "Reavaliar" sem feedback.
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, interpretar_erro_gemini(exc))
        # Item que nunca tinha sido avaliado: avaliar_item_rfi já persistiu um veredito "sem
        # evidência" com o erro na justificativa -- devolve normalmente pra UI mostrar.
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
