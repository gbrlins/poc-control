import pathlib
import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.categorias import normalizar as normalizar_categoria
from app.classificacao.service import atualizar_embedding_historico, classificar_item, sugerir_procedimentos
from app.classificacao.tasks import classificar_pendentes
from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.gemini import extrair_resumo_sessao, gerar_resumo_email, gerar_resumo_executivo
from app.gemini_key import resolve_api_key, resolve_model
from app.models import (
    Anexo,
    Classificacao,
    Item,
    Nota,
    OrigemClassificacao,
    OrigemConhecimento,
    Poc,
    PocDocumento,
    Prerequisito,
    Sessao,
    StatusExtracao,
    StatusHistorico,
    StatusItem,
    StatusProcedimento,
    User,
)
from app.pocs.apresentacao import montar_apresentacao_html
from app.pocs.documentos import TEXTO_COLADO_NOME, ler_conteudo, remover_arquivo, salvar_documento
from app.pocs.export import montar_export_html
from app.pocs.planner_import import extrair_parametros_tecnicos
from app.pocs.resultados import sincronizar_resultado_catalogo
from app import exclusao as excl
from app.procedimentos.router import _criar_procedimento, _escapar_html
from app.procedimentos.schemas import ProcedimentoListItem as ProcedimentoListItemOut
from app.pocs.roteiro import montar_roteiro_html
from app.pocs.schemas import (
    ClassificacaoManualUpdate,
    FaseOut,
    ItemOut,
    ItemUpdate,
    NotaCreate,
    PocDetail,
    PocDocumentoOut,
    PocListItem,
    PrerequisitoOut,
    PrerequisitoUpdate,
    ResumoExecutivoUpdate,
    SessaoCreate,
    SessaoImportar,
    SessaoOut,
)
from app.pocs.tasks import iniciar_processamento, processar_poc

router = APIRouter(prefix="/api/pocs", tags=["pocs"], dependencies=[Depends(get_current_user)])


def _contar_itens(db: Session, poc_id: uuid.UUID) -> tuple[int, int]:
    total = db.query(func.count(Item.id)).filter(Item.poc_id == poc_id).scalar() or 0
    concluidos = (
        db.query(func.count(Item.id))
        .filter(Item.poc_id == poc_id, Item.status == StatusItem.concluido)
        .scalar()
        or 0
    )
    return total, concluidos


def _produtos_poc(db: Session, poc_id: uuid.UUID) -> list[str]:
    """Códigos de produto (taxonomia fixa) distintos entre os itens da PoC -- não existe campo de
    produto na Poc em si, só por item (categoria_codigo), então a lista exibida no "banco de dados
    de PoCs" (home) é derivada aqui, não armazenada."""
    linhas = (
        db.query(Item.categoria_codigo)
        .filter(Item.poc_id == poc_id, Item.categoria_codigo != "")
        .distinct()
        .all()
    )
    return [codigo for (codigo,) in linhas]


def _list_item(db: Session, poc: Poc) -> PocListItem:
    total, concluidos = _contar_itens(db, poc.id)
    return PocListItem(
        id=poc.id,
        titulo=poc.titulo,
        cliente=poc.cliente,
        status=poc.status,
        status_extracao=poc.status_extracao,
        created_at=poc.created_at,
        processamento_iniciado_em=poc.processamento_iniciado_em,
        progresso=poc.progresso,
        cancelamento_solicitado=poc.cancelamento_solicitado,
        total_itens=total,
        itens_concluidos=concluidos,
        responsavel_id=poc.responsavel_id,
        responsavel_email=poc.responsavel.email if poc.responsavel else None,
        criado_por_email=poc.criado_por.email if poc.criado_por else None,
        produtos=_produtos_poc(db, poc.id),
    )


def _get_poc_or_404(db: Session, poc_id: uuid.UUID) -> Poc:
    poc = db.get(Poc, poc_id)
    if poc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PoC não encontrada")
    return poc


def _get_item_or_404(db: Session, poc_id: uuid.UUID, item_id: uuid.UUID) -> Item:
    item = db.get(Item, item_id)
    if item is None or item.poc_id != poc_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item não encontrado")
    return item


def _exigir_ocioso(poc: Poc) -> None:
    if poc.status_extracao == StatusExtracao.extraindo:
        raise HTTPException(status.HTTP_409_CONFLICT, "A PoC ainda está sendo processada; aguarde terminar")


def _documento_out(db: Session, doc: PocDocumento) -> PocDocumentoOut:
    total = db.query(func.count(Item.id)).filter(Item.documento_id == doc.id).scalar() or 0
    return PocDocumentoOut(id=doc.id, nome_arquivo=doc.nome_arquivo, created_at=doc.created_at, total_itens=total)


def _ler_uploads(arquivos: list[UploadFile] | None, texto: str | None) -> list[tuple[str, bytes]]:
    """Valida cada arquivo (e o texto colado, que vira mais um documento) ANTES de gravar qualquer
    coisa, pra um arquivo ruim não deixar uma PoC pela metade. Mesmo desenho de
    app/rfi/router.py::_ler_uploads."""
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


def _parametros_tecnicos_do_lote(docs: list[tuple[str, bytes]]) -> dict | None:
    """Usa o primeiro documento do lote que for o JSON exportado pelo Planejar PoC (o único
    formato de onde dá pra extrair parâmetros técnicos sem IA -- ver extrair_parametros_tecnicos).
    PDFs e outros textos livres simplesmente não batem com o formato e são ignorados aqui."""
    for nome, conteudo in docs:
        try:
            _, texto = ler_conteudo(nome, conteudo)
        except ValueError:
            continue
        if texto:
            parametros = extrair_parametros_tecnicos(texto)
            if parametros is not None:
                return parametros
    return None


@router.get("", response_model=list[PocListItem])
def listar_pocs(db: Session = Depends(get_db)):
    pocs = db.query(Poc).order_by(Poc.created_at.desc()).all()
    return [_list_item(db, poc) for poc in pocs]


def _criar_poc_de_entrada(
    db: Session, *, titulo: str, cliente: str, escopo: str, arquivos: list[UploadFile] | None, texto: str | None, dono: User
) -> tuple[Poc, list[PocDocumento]]:
    """Resolve a entrada (PDF/XLSX/CSV/texto/JSON por documento — lido nativamente pelo Gemini no \
    caso do PDF; os demais formatos são convertidos a texto antes, incluindo planilhas via \
    app/pocs/planilha_import.py), cria a `Poc`, grava cada documento em disco e devolve os \
    `PocDocumento` criados para a fila de extração (app/pocs/tasks.py::processar_poc). \
    Compartilhado por `criar_poc` e `importar_planejador`, que só diferem em título/cliente \
    (já conhecidos vs. a extrair) e em qual extração o background task vai rodar."""
    docs = _ler_uploads(arquivos, texto)
    if not docs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Envie o PDF da POC, ou cole/envie o plano de testes em texto/JSON")

    poc = Poc(
        titulo=titulo,
        cliente=cliente,
        escopo=escopo or None,
        parametros_tecnicos=_parametros_tecnicos_do_lote(docs),
        criado_por_id=dono.id,
        responsavel_id=dono.id,
    )
    iniciar_processamento(poc)
    db.add(poc)
    db.flush()
    criados = [salvar_documento(db, poc, nome, conteudo) for nome, conteudo in docs]
    db.commit()
    db.refresh(poc)

    return poc, criados


@router.post("", response_model=PocListItem, status_code=status.HTTP_201_CREATED)
def criar_poc(
    background_tasks: BackgroundTasks,
    titulo: str = Form(...),
    cliente: str = Form(...),
    escopo: str = Form(""),
    arquivos: list[UploadFile] | None = File(None),
    texto: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Entrada aceita PDF(s) (upload original, lido nativamente pelo Gemini) e/ou texto/JSON/XLSX/CSV
    # — este último grupo cobre colar o plano de testes em texto, subir o JSON exportado pelo
    # "Planejar PoC" (botão "Exportar Projeto" na etapa Resumo), ou subir uma planilha de
    # caderno de testes. Cada documento é extraído em sequência, numa fila em segundo plano (ver
    # app/pocs/tasks.py::processar_poc) -- dá pra mandar vários de uma vez (ex.: o PDF do edital +
    # uma planilha complementar) e a falha de um não trava os demais. O Gemini sabe interpretar
    # todos esses formatos (ver prompt em app/gemini.py). Ver também importar_planejador, abaixo,
    # pra importação a partir do próprio planejador (sem título/cliente ainda definidos).
    poc, criados = _criar_poc_de_entrada(
        db, titulo=titulo, cliente=cliente, escopo=escopo, arquivos=arquivos, texto=texto, dono=current_user
    )

    background_tasks.add_task(
        processar_poc, poc.id, [d.id for d in criados], resolve_api_key(current_user), resolve_model(current_user)
    )

    return _list_item(db, poc)


@router.post("/importar-planejador", response_model=PocListItem, status_code=status.HTTP_201_CREATED)
def importar_planejador(
    background_tasks: BackgroundTasks,
    arquivo: UploadFile | None = File(None),
    texto: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Importação de documento a partir do assistente "Planejar PoC" (tela inicial do app, \
    botão "Importar documento do cliente", ou o botão "Habilitar execução desta PoC" no \
    Resumo, que manda o próprio JSON exportado do estado em andamento). Ao contrário de \
    `criar_poc`, título/cliente ainda não existem -- o Gemini sugere os dois (ver \
    hidratar_planejador em app/pocs/tasks.py), que também preenche \
    `parametros_tecnicos["hidratacao_planejador"]` pro front aplicar no estado do assistente.
    Sempre um documento só (o planejador nunca manda mais de um nesta chamada)."""
    poc, criados = _criar_poc_de_entrada(
        db, titulo="", cliente="", escopo="", arquivos=[arquivo] if arquivo else None, texto=texto, dono=current_user
    )

    background_tasks.add_task(
        processar_poc,
        poc.id,
        [d.id for d in criados],
        resolve_api_key(current_user),
        resolve_model(current_user),
        hidratar_planejador=True,
    )

    return _list_item(db, poc)


@router.post("/{poc_id}/documentos", response_model=PocListItem, status_code=status.HTTP_202_ACCEPTED)
def adicionar_documentos(
    poc_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    arquivos: list[UploadFile] | None = File(None),
    texto: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Anexa documentos a uma PoC existente: extrai só os itens NOVOS (os existentes não são
    tocados). Mesmo desenho de app/rfi/router.py::adicionar_documentos."""
    poc = _get_poc_or_404(db, poc_id)
    _exigir_ocioso(poc)
    docs = _ler_uploads(arquivos, texto)
    if not docs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Envie ao menos um documento, ou cole o texto")
    criados = [salvar_documento(db, poc, nome, conteudo) for nome, conteudo in docs]
    iniciar_processamento(poc)
    db.commit()
    background_tasks.add_task(
        processar_poc, poc.id, [d.id for d in criados], resolve_api_key(current_user), resolve_model(current_user)
    )
    return _list_item(db, poc)


@router.delete("/{poc_id}/documentos/{documento_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_documento(poc_id: uuid.UUID, documento_id: uuid.UUID, db: Session = Depends(get_db)):
    """Remove o documento, o arquivo e todos os itens extraídos dele. Mesmo desenho de
    app/rfi/router.py::remover_documento."""
    poc = _get_poc_or_404(db, poc_id)
    _exigir_ocioso(poc)
    doc = db.get(PocDocumento, documento_id)
    if doc is None or doc.poc_id != poc_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado")
    # Remove os itens explicitamente (não só pelo ON DELETE CASCADE do banco): o ORM não tem
    # relationship Documento->Itens, então só assim a sessão fica consistente.
    db.query(Item).filter(Item.documento_id == doc.id).delete(synchronize_session=False)
    remover_arquivo(doc)
    db.delete(doc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{poc_id}/cancelar", response_model=PocListItem, status_code=status.HTTP_202_ACCEPTED)
def cancelar_processamento(poc_id: uuid.UUID, db: Session = Depends(get_db)):
    """Pede a interrupção do processamento em andamento. A tarefa em background confere o pedido
    entre um documento e outro e para; uma chamada já em curso ao Gemini termina antes. Mesmo
    desenho de app/rfi/router.py::cancelar_processamento."""
    poc = _get_poc_or_404(db, poc_id)
    if poc.status_extracao != StatusExtracao.extraindo:
        raise HTTPException(status.HTTP_409_CONFLICT, "Não há processamento em andamento nesta PoC")
    poc.cancelamento_solicitado = True
    db.commit()
    return _list_item(db, poc)


@router.get("/{poc_id}", response_model=PocDetail)
def obter_poc(poc_id: uuid.UUID, db: Session = Depends(get_db)):
    poc = _get_poc_or_404(db, poc_id)
    return PocDetail(
        # Reaproveita _list_item (em vez de repetir campo a campo) -- é exatamente esse tipo de
        # duplicação que já deixou responsavel_id de fora daqui uma vez (ver test_exclusao_db.py
        # ::test_detalhe_mostra_o_mesmo_dono_que_a_listagem).
        **_list_item(db, poc).model_dump(),
        escopo=poc.escopo,
        erro_extracao=poc.erro_extracao,
        modelo_extracao=poc.modelo_extracao,
        resumo_executivo=poc.resumo_executivo,
        parametros_tecnicos=poc.parametros_tecnicos,
        fases=[FaseOut(**f) for f in (poc.fases or [])],
        itens=[ItemOut.model_validate(i) for i in poc.itens],
        prerequisitos=[PrerequisitoOut.model_validate(p) for p in poc.prerequisitos],
        sessoes=[SessaoOut.model_validate(s) for s in poc.sessoes],
        documentos=[_documento_out(db, d) for d in poc.documentos],
    )


class ResponsavelIn(BaseModel):
    responsavel_id: uuid.UUID


class ExclusaoIn(BaseModel):
    confirmar: str


@router.put("/{poc_id}/responsavel")
def definir_responsavel(
    poc_id: uuid.UUID,
    payload: ResponsavelIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transfere o dono (só o dono atual), assume uma PoC sem dono (qualquer engenheiro, só para si) ou reatribui (administrador).
    Regras da ADR 4; ver app/exclusao.py."""
    poc = _get_poc_or_404(db, poc_id)
    novo = db.get(User, payload.responsavel_id)
    if novo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado")
    if not excl.pode_atribuir(current_user, poc, novo.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Só o dono (ou um administrador) altera o responsável; uma PoC sem dono pode ser assumida.")
    poc.responsavel_id = novo.id
    db.commit()
    return {"id": poc.id, "responsavel_id": poc.responsavel_id}


@router.get("/{poc_id}/exclusao")
def previa_exclusao(poc_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """O que uma exclusão removeria e o que ficaria (para a tela de confirmação). Não altera nada."""
    return excl.previa(db, current_user, "poc", _get_poc_or_404(db, poc_id))


@router.delete("/{poc_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_poc(
    poc_id: uuid.UUID,
    payload: ExclusaoIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exclusão PERMANENTE (ADR 4): só o dono, com o título digitado em `confirmar`."""
    poc = _get_poc_or_404(db, poc_id)
    try:
        excl.excluir(db, current_user, "poc", poc, payload.confirmar)
    except excl.ExclusaoErro as e:
        raise HTTPException(e.status, e.mensagem)


@router.post("/{poc_id}/reextrair", status_code=status.HTTP_202_ACCEPTED)
def reextrair_poc(
    poc_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tenta de novo a extração de itens de uma PoC cujo status_extracao ficou 'erro' (ex.: o
    Gemini respondeu 503 por sobrecarga) -- sem precisar recriar a PoC do zero. Só chega a `erro`
    quando TODOS os documentos falharam (ver app/pocs/tasks.py::processar_poc), então reprocessa
    a fila inteira; cada documento relê o próprio arquivo do disco."""
    poc = _get_poc_or_404(db, poc_id)
    if poc.status_extracao != StatusExtracao.erro:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Só é possível reprocessar uma PoC cuja extração falhou"
        )
    if not poc.documentos:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta PoC não tem documento original para reprocessar")

    iniciar_processamento(poc)
    db.commit()

    background_tasks.add_task(
        processar_poc,
        poc.id,
        [d.id for d in poc.documentos],
        resolve_api_key(current_user),
        resolve_model(current_user),
        # Só importar_planejador cria a Poc com título vazio -- se a primeira extração falhou
        # antes de sugerir um, título continua vazio e o reprocessamento precisa hidratar de
        # novo (senão o título/produtos/rede do assistente nunca chegam a ser preenchidos).
        hidratar_planejador=not poc.titulo,
    )
    return {"status": "extraindo"}


@router.get("/{poc_id}/export", response_class=HTMLResponse)
def exportar_poc(poc_id: uuid.UUID, db: Session = Depends(get_db)):
    poc = _get_poc_or_404(db, poc_id)
    return HTMLResponse(montar_export_html(poc))


def _contexto_apresentacao(poc: Poc) -> str:
    total = len(poc.itens)
    concluidos = sum(1 for i in poc.itens if i.status == StatusItem.concluido)
    pct = round(concluidos / total * 100) if total else 0

    linhas = [
        f"PoC: {poc.titulo} — Cliente: {poc.cliente}",
        f"Progresso: {concluidos}/{total} itens concluídos ({pct}%)",
    ]

    fase_titulo = {f["numero"]: f["titulo"] for f in (poc.fases or [])}
    por_fase: dict[int, list] = {}
    for item in poc.itens:
        por_fase.setdefault(item.fase, []).append(item)
    for numero in sorted(por_fase):
        titulo_fase = fase_titulo.get(numero, f"Fase {numero}")
        resumo_itens = ", ".join(
            f"{i.codigo} {i.titulo} ({i.status.value}"
            + (f", {i.classificacao.flag.value}" if i.classificacao else "")
            + ")"
            for i in por_fase[numero]
        )
        linhas.append(f"Fase \"{titulo_fase}\": {resumo_itens}")

    atendidos = [p.titulo for p in poc.prerequisitos if p.atendido]
    pendentes_prereq = [p.titulo for p in poc.prerequisitos if not p.atendido]
    if atendidos:
        linhas.append("Pré-requisitos atendidos: " + "; ".join(atendidos))
    if pendentes_prereq:
        linhas.append("Pré-requisitos pendentes: " + "; ".join(pendentes_prereq))

    for s in sorted(poc.sessoes, key=lambda s: s.data):
        linhas.append(f"Sessão de {s.data.isoformat()}:")
        if s.pontos_resolvidos:
            linhas.append("  Resolvido: " + "; ".join(s.pontos_resolvidos))
        if s.pontos_falha:
            linhas.append("  Pendência/falha: " + "; ".join(s.pontos_falha))
        if s.proximos_passos:
            linhas.append("  Próximos passos: " + "; ".join(s.proximos_passos))

    return "\n".join(linhas)


@router.post("/{poc_id}/apresentacao/resumo")
def gerar_resumo_executivo_poc(
    poc_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    poc = _get_poc_or_404(db, poc_id)
    texto = gerar_resumo_executivo(
        _contexto_apresentacao(poc), api_key=resolve_api_key(current_user), model=resolve_model(current_user)
    )
    poc.resumo_executivo = texto
    db.commit()
    return {"texto": texto}


@router.patch("/{poc_id}/apresentacao/resumo")
def salvar_resumo_executivo_poc(poc_id: uuid.UUID, payload: ResumoExecutivoUpdate, db: Session = Depends(get_db)):
    poc = _get_poc_or_404(db, poc_id)
    poc.resumo_executivo = payload.resumo_executivo
    db.commit()
    return {"texto": poc.resumo_executivo}


@router.get("/{poc_id}/apresentacao", response_class=HTMLResponse)
def exportar_apresentacao(poc_id: uuid.UUID, db: Session = Depends(get_db)):
    poc = _get_poc_or_404(db, poc_id)
    return HTMLResponse(montar_apresentacao_html(poc))


@router.get("/{poc_id}/roteiro", response_class=HTMLResponse)
def gerar_roteiro(poc_id: uuid.UUID, item_ids: list[uuid.UUID] = Query(...), db: Session = Depends(get_db)):
    """Roteiro do dia: para os itens marcados (checklist na aba "Andamento"), monta uma página
    imprimível com os procedimentos vinculados já na ordem de execução (fase, depois ordem),
    precedida pelos parâmetros técnicos desta PoC (rede/infra) quando vieram do Planejar PoC.
    GET (em vez de POST) de propósito: assim o front abre o resultado direto num link/nova aba,
    igual aos outros exports (ver urlExportarPoc/urlApresentacaoPoc em web/src/api.ts)."""
    poc = _get_poc_or_404(db, poc_id)
    ids_selecionados = set(item_ids)
    itens_selecionados = [i for i in poc.itens if i.id in ids_selecionados]
    if not itens_selecionados:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selecione ao menos um item")
    return HTMLResponse(montar_roteiro_html(poc, itens_selecionados))


@router.patch("/{poc_id}/itens/{item_id}", response_model=ItemOut)
def atualizar_item(
    poc_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = _get_item_or_404(db, poc_id, item_id)
    dados = payload.model_dump(exclude_unset=True)
    sessao_id = dados.pop("sessao_id", None)

    if "categoria_codigo" in dados:
        dados["categoria_codigo"] = normalizar_categoria(dados["categoria_codigo"])

    status_anterior = item.status
    resultado_anterior = item.resultado
    for campo, valor in dados.items():
        setattr(item, campo, valor)

    if "status" in dados and dados["status"] != status_anterior:
        db.add(
            StatusHistorico(
                item_id=item.id,
                sessao_id=sessao_id,
                status_anterior=status_anterior,
                status_novo=item.status,
            )
        )

    # Histórico anônimo por teste do catálogo (ADR 1): reavalia quando o resultado, a aderência ou o status mudam (um
    # bloqueio depois de um `pass` tira o "sem problemas"). O flush antes garante que a transição acima já vale na consulta.
    if {"resultado", "aderencia", "status"} & dados.keys():
        db.flush()
        sincronizar_resultado_catalogo(db, item, resultado_mudou=item.resultado != resultado_anterior)
        atualizar_embedding_historico(db, item, resolve_api_key(current_user))

    db.commit()
    db.refresh(item)
    return item


@router.delete("/{poc_id}/itens/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_item(poc_id: uuid.UUID, item_id: uuid.UUID, db: Session = Depends(get_db)):
    item = _get_item_or_404(db, poc_id, item_id)
    db.delete(item)
    db.commit()


@router.post("/{poc_id}/itens/{item_id}/classificar", response_model=ItemOut)
def classificar_item_individual(
    poc_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = _get_item_or_404(db, poc_id, item_id)
    classificar_item(db, item, api_key=resolve_api_key(current_user), model=resolve_model(current_user))
    db.refresh(item)
    return item


@router.get("/{poc_id}/itens/{item_id}/sugestoes-procedimento", response_model=list[ProcedimentoListItemOut])
def sugerir_procedimento_para_item(
    poc_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = _get_item_or_404(db, poc_id, item_id)
    sugestoes = sugerir_procedimentos(db, item, api_key=resolve_api_key(current_user))
    return [ProcedimentoListItemOut.model_validate(p) for p in sugestoes]


@router.patch("/{poc_id}/itens/{item_id}/classificacao", response_model=ItemOut)
def sobrescrever_classificacao(
    poc_id: uuid.UUID, item_id: uuid.UUID, payload: ClassificacaoManualUpdate, db: Session = Depends(get_db)
):
    item = _get_item_or_404(db, poc_id, item_id)

    classificacao = item.classificacao
    if classificacao is None:
        classificacao = Classificacao(item_id=item.id)
        db.add(classificacao)

    classificacao.flag = payload.flag
    classificacao.origem = OrigemClassificacao.manual
    classificacao.justificativa = payload.justificativa
    classificacao.procedimento_id = payload.procedimento_id
    classificacao.confirmado_por_historico = False
    classificacao.modelo = None
    if classificacao.fontes is None:
        classificacao.fontes = []

    db.commit()
    db.refresh(item)
    return item


@router.post("/{poc_id}/classificar-pendentes", status_code=status.HTTP_202_ACCEPTED)
def classificar_pendentes_da_poc(
    poc_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_poc_or_404(db, poc_id)
    background_tasks.add_task(
        classificar_pendentes, poc_id, resolve_api_key(current_user), resolve_model(current_user)
    )
    return {"status": "classificando"}


@router.patch("/{poc_id}/prerequisitos/{prereq_id}", response_model=PrerequisitoOut)
def atualizar_prerequisito(
    poc_id: uuid.UUID, prereq_id: uuid.UUID, payload: PrerequisitoUpdate, db: Session = Depends(get_db)
):
    prereq = db.get(Prerequisito, prereq_id)
    if prereq is None or prereq.poc_id != poc_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pré-requisito não encontrado")
    prereq.atendido = payload.atendido
    db.commit()
    db.refresh(prereq)
    return prereq


@router.post("/{poc_id}/sessoes", response_model=SessaoOut, status_code=status.HTTP_201_CREATED)
def criar_sessao(poc_id: uuid.UUID, payload: SessaoCreate, db: Session = Depends(get_db)):
    _get_poc_or_404(db, poc_id)
    sessao = Sessao(poc_id=poc_id, data=payload.data, participantes=payload.participantes, agenda=payload.agenda)
    db.add(sessao)
    db.commit()
    db.refresh(sessao)
    return sessao


@router.post("/{poc_id}/sessoes/importar", response_model=SessaoOut, status_code=status.HTTP_201_CREATED)
def importar_sessao(
    poc_id: uuid.UUID,
    payload: SessaoImportar,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_poc_or_404(db, poc_id)
    extraido = extrair_resumo_sessao(
        payload.texto, api_key=resolve_api_key(current_user), model=resolve_model(current_user)
    )

    try:
        data_sessao = date.fromisoformat(extraido.data) if extraido.data else date.today()
    except ValueError:
        data_sessao = date.today()

    sessao = Sessao(
        poc_id=poc_id,
        data=data_sessao,
        participantes=extraido.participantes,
        resumo_bruto=payload.texto,
        pontos_resolvidos=extraido.pontos_resolvidos,
        pontos_falha=extraido.pontos_falha,
        proximos_passos=extraido.proximos_passos,
    )
    db.add(sessao)
    db.commit()
    db.refresh(sessao)
    return sessao


def _get_sessao_or_404(db: Session, poc_id: uuid.UUID, sessao_id: uuid.UUID) -> Sessao:
    sessao = db.get(Sessao, sessao_id)
    if sessao is None or sessao.poc_id != poc_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessão não encontrada")
    return sessao


def _contexto_sessao(poc: Poc, sessao: Sessao) -> str:
    linhas = [f"PoC: {poc.titulo} — Cliente: {poc.cliente}", f"Data da sessão: {sessao.data.isoformat()}"]
    if sessao.participantes:
        linhas.append(f"Participantes: {', '.join(sessao.participantes)}")
    if sessao.agenda:
        linhas.append(f"Agenda: {sessao.agenda}")
    if sessao.pontos_resolvidos:
        linhas.append("Pontos resolvidos (resumo importado): " + "; ".join(sessao.pontos_resolvidos))
    if sessao.pontos_falha:
        linhas.append("Pontos com falha/pendência (resumo importado): " + "; ".join(sessao.pontos_falha))
    if sessao.proximos_passos:
        linhas.append("Próximos passos combinados (resumo importado): " + "; ".join(sessao.proximos_passos))

    mudancas = []
    notas = []
    for item in poc.itens:
        for h in item.status_historico:
            if h.sessao_id == sessao.id:
                anterior = h.status_anterior.value if h.status_anterior else "novo"
                mudancas.append(f"{item.codigo} {item.titulo}: {anterior} -> {h.status_novo.value}")
        for n in item.notas:
            if n.sessao_id == sessao.id:
                notas.append(f"{item.codigo} {item.titulo}: {n.texto}")

    if mudancas:
        linhas.append("Mudanças de status nesta sessão:\n" + "\n".join(mudancas))
    if notas:
        linhas.append("Notas registradas nesta sessão:\n" + "\n".join(notas))

    return "\n\n".join(linhas)


@router.post("/{poc_id}/sessoes/{sessao_id}/resumo")
def obter_resumo_sessao(
    poc_id: uuid.UUID,
    sessao_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    poc = _get_poc_or_404(db, poc_id)
    sessao = _get_sessao_or_404(db, poc_id, sessao_id)
    texto = gerar_resumo_email(
        _contexto_sessao(poc, sessao), api_key=resolve_api_key(current_user), model=resolve_model(current_user)
    )
    return {"texto": texto}


@router.post("/{poc_id}/itens/{item_id}/notas", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def criar_nota(poc_id: uuid.UUID, item_id: uuid.UUID, payload: NotaCreate, db: Session = Depends(get_db)):
    item = _get_item_or_404(db, poc_id, item_id)
    if payload.sessao_id is not None:
        _get_sessao_or_404(db, poc_id, payload.sessao_id)
    db.add(Nota(item_id=item.id, sessao_id=payload.sessao_id, texto=payload.texto))
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{poc_id}/itens/{item_id}/notas/{nota_id}", response_model=ItemOut)
def remover_nota(poc_id: uuid.UUID, item_id: uuid.UUID, nota_id: uuid.UUID, db: Session = Depends(get_db)):
    item = _get_item_or_404(db, poc_id, item_id)
    nota = db.get(Nota, nota_id)
    if nota is None or nota.item_id != item.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nota não encontrada")
    db.delete(nota)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{poc_id}/itens/{item_id}/anexos", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def criar_anexo(
    poc_id: uuid.UUID,
    item_id: uuid.UUID,
    sessao_id: uuid.UUID | None = Form(None),
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    item = _get_item_or_404(db, poc_id, item_id)
    if sessao_id is not None:
        _get_sessao_or_404(db, poc_id, sessao_id)

    conteudo = arquivo.file.read()
    if not conteudo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Arquivo vazio")

    anexo_dir = pathlib.Path(settings.uploads_dir) / "pocs" / str(poc_id) / "anexos" / str(item_id)
    anexo_dir.mkdir(parents=True, exist_ok=True)
    nome_arquivo = arquivo.filename or "anexo"
    caminho = anexo_dir / f"{uuid.uuid4()}_{nome_arquivo}"
    caminho.write_bytes(conteudo)

    db.add(
        Anexo(
            item_id=item.id,
            sessao_id=sessao_id,
            nome_arquivo=nome_arquivo,
            caminho_arquivo=str(caminho),
        )
    )
    db.commit()
    db.refresh(item)
    return item


@router.get("/{poc_id}/itens/{item_id}/anexos/{anexo_id}")
def baixar_anexo(poc_id: uuid.UUID, item_id: uuid.UUID, anexo_id: uuid.UUID, db: Session = Depends(get_db)):
    item = _get_item_or_404(db, poc_id, item_id)
    anexo = db.get(Anexo, anexo_id)
    if anexo is None or anexo.item_id != item.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anexo não encontrado")
    return FileResponse(anexo.caminho_arquivo, filename=anexo.nome_arquivo)


@router.delete("/{poc_id}/itens/{item_id}/anexos/{anexo_id}", response_model=ItemOut)
def remover_anexo(poc_id: uuid.UUID, item_id: uuid.UUID, anexo_id: uuid.UUID, db: Session = Depends(get_db)):
    item = _get_item_or_404(db, poc_id, item_id)
    anexo = db.get(Anexo, anexo_id)
    if anexo is None or anexo.item_id != item.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anexo não encontrado")
    pathlib.Path(anexo.caminho_arquivo).unlink(missing_ok=True)
    db.delete(anexo)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{poc_id}/itens/{item_id}/anexos/{anexo_id}/validar", response_model=ItemOut)
def validar_anexo(
    poc_id: uuid.UUID,
    item_id: uuid.UUID,
    anexo_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marca a caixinha "Validado" ao lado de um anexo: pega o conteúdo do arquivo (HTML direto,
    ou texto simples envolvido num HTML mínimo) e promove a um procedimento validado na
    biblioteca, com o título do próprio item -- substitui o formulário separado que existia
    antes pra escrever um procedimento do zero."""
    item = _get_item_or_404(db, poc_id, item_id)
    anexo = db.get(Anexo, anexo_id)
    if anexo is None or anexo.item_id != item.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anexo não encontrado")
    if anexo.procedimento_id is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este anexo já foi validado como procedimento")

    caminho = pathlib.Path(anexo.caminho_arquivo)
    if not caminho.exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "O arquivo do anexo não foi encontrado em disco")
    try:
        conteudo = caminho.read_text(encoding="utf-8")
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Só é possível validar anexos de texto ou HTML")

    if pathlib.Path(anexo.nome_arquivo).suffix.lower() in (".html", ".htm"):
        html = conteudo
    else:
        paragrafos = "\n".join(
            f"<p>{_escapar_html(p).replace(chr(10), '<br/>')}</p>" for p in conteudo.split("\n\n") if p.strip()
        )
        html = f"<h2>{_escapar_html(item.titulo)}</h2>\n{paragrafos}"

    procedimento = _criar_procedimento(
        db,
        titulo=item.titulo,
        tags=[item.categoria] if item.categoria else [],
        categorias=[item.categoria_codigo] if item.categoria_codigo else [],
        cliente_origem=item.poc.cliente,
        data_origem=None,
        status_valor=StatusProcedimento.validado,
        versao=1,
        html=html,
        api_key=resolve_api_key(current_user),
        dono_id=current_user.id,
        origem=OrigemConhecimento.poc,
    )
    anexo.procedimento_id = procedimento.id
    db.commit()
    db.refresh(item)
    return item
