import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_admin_user, get_current_user
from app.licitacoes.schemas import AtualizarLicitacoesOut, LicitacaoOut, TermoBuscaIn, TermoBuscaOut
from app.licitacoes.service import verificar_licitacoes
from app.models import Licitacao, TermoBuscaLicitacao

router = APIRouter(prefix="/api/licitacoes", tags=["licitacoes"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[LicitacaoOut])
def listar_licitacoes(db: Session = Depends(get_db)):
    # Sem filtro no backend -- lista ainda pequena (beta recém-ligado), o front filtra em memória
    # na tela cheia, mesmo padrão de listar_rfis (app/rfi/router.py).
    licitacoes = db.query(Licitacao).order_by(Licitacao.data_publicacao.desc()).all()
    return licitacoes


@router.post("/atualizar", response_model=AtualizarLicitacoesOut)
def atualizar_licitacoes(db: Session = Depends(get_db)):
    """Dispara a verificação na hora (síncrono -- aceitável pra uma ação sob demanda; o front
    mostra "Atualizando..." no botão enquanto espera). Mesma função usada pelo laço periódico em
    app/main.py."""
    novas = verificar_licitacoes(db)
    return AtualizarLicitacoesOut(novas=novas)


@router.get("/termos", response_model=list[TermoBuscaOut], dependencies=[Depends(get_current_admin_user)])
def listar_termos(db: Session = Depends(get_db)):
    return db.query(TermoBuscaLicitacao).order_by(TermoBuscaLicitacao.termo).all()


@router.post(
    "/termos",
    response_model=TermoBuscaOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_admin_user)],
)
def criar_termo(payload: TermoBuscaIn, db: Session = Depends(get_db)):
    termo = payload.termo.strip()
    if not termo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Termo não pode ser vazio")
    existente = db.query(TermoBuscaLicitacao).filter(TermoBuscaLicitacao.termo == termo).one_or_none()
    if existente is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um termo de busca igual a esse")

    novo = TermoBuscaLicitacao(termo=termo, categoria_codigo=payload.categoria_codigo)
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@router.patch("/termos/{termo_id}", response_model=TermoBuscaOut, dependencies=[Depends(get_current_admin_user)])
def alternar_termo(termo_id: uuid.UUID, db: Session = Depends(get_db)):
    """Liga/desliga um termo sem apagar -- dá pra reativar depois sem perder o histórico de quando
    foi criado."""
    termo = db.get(TermoBuscaLicitacao, termo_id)
    if termo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Termo não encontrado")
    termo.ativo = not termo.ativo
    db.commit()
    db.refresh(termo)
    return termo


@router.delete("/termos/{termo_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(get_current_admin_user)])
def remover_termo(termo_id: uuid.UUID, db: Session = Depends(get_db)):
    termo = db.get(TermoBuscaLicitacao, termo_id)
    if termo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Termo não encontrado")
    db.delete(termo)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
