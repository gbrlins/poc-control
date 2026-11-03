import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import exclusao as excl
from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.gemini_key import resolve_api_key
from app.models import Procedimento, StatusProcedimento, User
from app.procedimentos.router import _criar_procedimento
from app.procedimentos.schemas import ProcedimentoListItem
from app.sync.client import RemotoErro, cliente_remoto, criar_remoto, listar_remotos, obter_remoto

router = APIRouter(prefix="/api/sync", tags=["sync"], dependencies=[Depends(get_current_user)])


class SincronizarIdsIn(BaseModel):
    ids: list[uuid.UUID]


class ResultadoSincronizacao(BaseModel):
    id: uuid.UUID | str
    titulo: str
    status: str  # "baixado" | "enviado" | "erro"
    erro: str | None = None


@router.get("/config")
def obter_config():
    """Pro front saber se mostra o botão de sincronizar -- não expõe URL nem credenciais."""
    return {"configurado": settings.sync_configurado}


@router.get("/remoto/procedimentos", response_model=list[ProcedimentoListItem])
def listar_procedimentos_remotos():
    try:
        cliente = cliente_remoto()
    except RemotoErro as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    try:
        return listar_remotos(cliente)
    except RemotoErro as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    finally:
        cliente.close()


@router.post("/remoto/baixar", response_model=list[ResultadoSincronizacao])
def baixar_do_servidor(
    payload: SincronizarIdsIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Baixa cada procedimento remoto selecionado e cria uma cópia local (origem=manual). Erro num
    item não trava os demais -- mesmo espírito das filas de documento de PoC/RFI."""
    try:
        cliente = cliente_remoto()
    except RemotoErro as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    resultados: list[ResultadoSincronizacao] = []
    try:
        for procedimento_id in payload.ids:
            try:
                detalhe = obter_remoto(cliente, str(procedimento_id))
                _criar_procedimento(
                    db,
                    titulo=detalhe["titulo"],
                    tags=detalhe["tags"],
                    categorias=detalhe["categorias"],
                    cliente_origem=detalhe.get("cliente_origem"),
                    data_origem=date.fromisoformat(detalhe["data_origem"]) if detalhe.get("data_origem") else None,
                    status_valor=StatusProcedimento(detalhe["status"]),
                    versao=detalhe["versao"],
                    html=detalhe["html_original"],
                    api_key=resolve_api_key(current_user),
                    dono_id=current_user.id,
                )
                resultados.append(
                    ResultadoSincronizacao(id=procedimento_id, titulo=detalhe["titulo"], status="baixado")
                )
            except Exception as exc:  # noqa: BLE001 - não pode travar o lote por um item com erro
                db.rollback()
                resultados.append(
                    ResultadoSincronizacao(id=procedimento_id, titulo=str(procedimento_id), status="erro", erro=str(exc))
                )
    finally:
        cliente.close()
    return resultados


@router.post("/local/enviar", response_model=list[ResultadoSincronizacao])
def enviar_para_servidor(
    payload: SincronizarIdsIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Sobe cada procedimento local selecionado pro servidor remoto; só apaga daqui se o servidor
    confirmar que salvou (HTTP 201). Se der certo lá mas não conseguir apagar aqui (ex.: você não é
    o dono local), o item fica como erro -- melhor duplicado e visível do que silenciosamente
    sumido sem confirmação."""
    try:
        cliente = cliente_remoto()
    except RemotoErro as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    resultados: list[ResultadoSincronizacao] = []
    try:
        for procedimento_id in payload.ids:
            procedimento = db.get(Procedimento, procedimento_id)
            if procedimento is None:
                resultados.append(
                    ResultadoSincronizacao(id=procedimento_id, titulo=str(procedimento_id), status="erro", erro="Procedimento não encontrado")
                )
                continue
            titulo = procedimento.titulo
            try:
                criar_remoto(cliente, procedimento)
            except RemotoErro as exc:
                resultados.append(ResultadoSincronizacao(id=procedimento_id, titulo=titulo, status="erro", erro=str(exc)))
                continue
            try:
                confirmar = (procedimento.titulo or "").strip() or str(procedimento.id)
                excl.excluir(db, current_user, "procedimento", procedimento, confirmar)
            except excl.ExclusaoErro as exc:
                resultados.append(
                    ResultadoSincronizacao(
                        id=procedimento_id,
                        titulo=titulo,
                        status="erro",
                        erro=f"Enviado ao servidor, mas não foi possível apagar localmente: {exc.mensagem}",
                    )
                )
                continue
            resultados.append(ResultadoSincronizacao(id=procedimento_id, titulo=titulo, status="enviado"))
    finally:
        cliente.close()
    return resultados
