import pathlib
import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.classificacao.service import classificar_item, sugerir_procedimentos
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
from app.pocs.export import montar_export_html
from app.pocs.planilha_import import texto_de_planilha
from app.pocs.planner_import import extrair_parametros_tecnicos
from app.pocs.resultados import sincronizar_resultado_catalogo
from app import exclusao as excl
from app.procedimentos.router import _criar_procedimento
from app.procedimentos.schemas import ProcedimentoListItem as ProcedimentoListItemOut
from app.pocs.roteiro import montar_roteiro_html
from app.pocs.schemas import (
    ClassificacaoManualUpdate,
    FaseOut,
    ItemOut,
    ItemUpdate,
    NotaCreate,
    PocDetail,
    PocListItem,
    PrerequisitoOut,
    PrerequisitoUpdate,
    ResumoExecutivoUpdate,
    SessaoCreate,
    SessaoImportar,
    SessaoOut,
)
from app.pocs.tasks import processar_extracao

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


def _list_item(db: Session, poc: Poc) -> PocListItem:
    total, concluidos = _contar_itens(db, poc.id)
    return PocListItem(
        id=poc.id,
        titulo=poc.titulo,
        cliente=poc.cliente,
        status=poc.status,
        status_extracao=poc.status_extracao,
        created_at=poc.created_at,
        total_itens=total,
        itens_concluidos=concluidos,
        responsavel_id=poc.responsavel_id,
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


@router.get("", response_model=list[PocListItem])
def listar_pocs(db: Session = Depends(get_db)):
    pocs = db.query(Poc).order_by(Poc.created_at.desc()).all()
    return [_list_item(db, poc) for poc in pocs]


def _criar_poc_de_entrada(
    db: Session, *, titulo: str, cliente: str, escopo: str, arquivo: UploadFile | None, texto: str | None, dono: User
) -> tuple[Poc, bytes | None, str | None]:
    """Resolve a entrada (PDF/XLSX/CSV/texto/JSON — lida nativamente pelo Gemini no caso do \
    PDF; os demais formatos são convertidos a texto antes, incluindo planilhas via \
    app/pocs/planilha_import.py), cria a `Poc` e grava o documento original em disco. \
    Compartilhado por `criar_poc` e `importar_planejador`, que só diferem em título/cliente \
    (já conhecidos vs. a extrair) e em qual extração o background task vai rodar."""
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
            # Guarda os bytes originais da planilha (não o texto convertido) pra salvar em
            # disco com a extensão real — ver bloco de persistência abaixo.
            planilha_bytes = conteudo
        else:
            try:
                texto_arquivo = conteudo.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Não foi possível ler o arquivo como texto; envie um PDF, uma planilha XLSX/CSV, "
                    "ou um arquivo de texto/JSON em UTF-8",
                )

    texto_final = (texto or "").strip() or texto_arquivo
    if not pdf_bytes and not texto_final:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Envie o PDF da POC, ou cole/envie o plano de testes em texto/JSON")

    parametros_tecnicos = extrair_parametros_tecnicos(texto_final) if texto_final else None

    poc = Poc(
        titulo=titulo,
        cliente=cliente,
        escopo=escopo or None,
        status_extracao=StatusExtracao.extraindo,
        parametros_tecnicos=parametros_tecnicos,
        criado_por_id=dono.id,
        responsavel_id=dono.id,
    )
    db.add(poc)
    db.commit()
    db.refresh(poc)

    poc_dir = pathlib.Path(settings.uploads_dir) / "pocs" / str(poc.id)
    poc_dir.mkdir(parents=True, exist_ok=True)
    if pdf_bytes:
        nome = nome_arquivo or "poc.pdf"
        caminho = poc_dir / nome
        caminho.write_bytes(pdf_bytes)
    elif planilha_bytes:
        nome = nome_arquivo or "plano-importado.xlsx"
        caminho = poc_dir / nome
        caminho.write_bytes(planilha_bytes)
    else:
        nome = nome_arquivo or "plano-importado.txt"
        caminho = poc_dir / nome
        caminho.write_text(texto_final, encoding="utf-8")

    db.add(PocDocumento(poc_id=poc.id, nome_arquivo=nome, caminho_arquivo=str(caminho)))
    db.commit()

    return poc, pdf_bytes, texto_final


@router.post("", response_model=PocListItem, status_code=status.HTTP_201_CREATED)
def criar_poc(
    background_tasks: BackgroundTasks,
    titulo: str = Form(...),
    cliente: str = Form(...),
    escopo: str = Form(""),
    arquivo: UploadFile | None = File(None),
    texto: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Entrada aceita PDF (upload original, lido nativamente pelo Gemini) OU texto/JSON/XLSX/CSV
    # — este último grupo cobre colar o plano de testes em texto, subir o JSON exportado pelo
    # "Planejar PoC" (botão "Exportar Projeto" na etapa Resumo), ou subir uma planilha de
    # caderno de testes. O Gemini sabe interpretar todos esses formatos (ver prompt em
    # app/gemini.py). Ver também importar_planejador, abaixo, pra importação a partir do
    # próprio planejador (sem título/cliente ainda definidos).
    poc, pdf_bytes, texto_final = _criar_poc_de_entrada(
        db, titulo=titulo, cliente=cliente, escopo=escopo, arquivo=arquivo, texto=texto, dono=current_user
    )

    background_tasks.add_task(
        processar_extracao, poc.id, pdf_bytes, texto_final, resolve_api_key(current_user), resolve_model(current_user)
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
    `parametros_tecnicos["hidratacao_planejador"]` pro front aplicar no estado do assistente."""
    poc, pdf_bytes, texto_final = _criar_poc_de_entrada(
        db, titulo="", cliente="", escopo="", arquivo=arquivo, texto=texto, dono=current_user
    )

    background_tasks.add_task(
        processar_extracao,
        poc.id,
        pdf_bytes,
        texto_final,
        resolve_api_key(current_user),
        resolve_model(current_user),
        hidratar_planejador=True,
    )

    return _list_item(db, poc)


@router.get("/{poc_id}", response_model=PocDetail)
def obter_poc(poc_id: uuid.UUID, db: Session = Depends(get_db)):
    poc = _get_poc_or_404(db, poc_id)
    total, concluidos = _contar_itens(db, poc.id)
    return PocDetail(
        id=poc.id,
        titulo=poc.titulo,
        cliente=poc.cliente,
        status=poc.status,
        status_extracao=poc.status_extracao,
        created_at=poc.created_at,
        total_itens=total,
        itens_concluidos=concluidos,
        escopo=poc.escopo,
        erro_extracao=poc.erro_extracao,
        modelo_extracao=poc.modelo_extracao,
        resumo_executivo=poc.resumo_executivo,
        parametros_tecnicos=poc.parametros_tecnicos,
        fases=[FaseOut(**f) for f in (poc.fases or [])],
        itens=[ItemOut.model_validate(i) for i in poc.itens],
        prerequisitos=[PrerequisitoOut.model_validate(p) for p in poc.prerequisitos],
        sessoes=[SessaoOut.model_validate(s) for s in poc.sessoes],
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
    Gemini respondeu 503 por sobrecarga) -- sem precisar recriar a PoC do zero. Relê o
    documento original salvo em disco (PDF ou texto/JSON) e refaz a extração em segundo plano."""
    poc = _get_poc_or_404(db, poc_id)
    if poc.status_extracao != StatusExtracao.erro:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Só é possível reprocessar uma PoC cuja extração falhou"
        )

    documento = poc.documentos[-1] if poc.documentos else None
    if documento is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta PoC não tem documento original para reprocessar")

    caminho = pathlib.Path(documento.caminho_arquivo)
    if not caminho.exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "O arquivo original não foi encontrado em disco")

    pdf_bytes: bytes | None = None
    texto: str | None = None
    extensao = caminho.suffix.lower()
    if extensao == ".pdf":
        pdf_bytes = caminho.read_bytes()
    elif extensao in (".xlsx", ".csv"):
        try:
            texto = texto_de_planilha(caminho.read_bytes(), extensao)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    else:
        texto = caminho.read_text(encoding="utf-8")

    poc.status_extracao = StatusExtracao.extraindo
    poc.erro_extracao = None
    db.commit()

    background_tasks.add_task(
        processar_extracao,
        poc.id,
        pdf_bytes,
        texto,
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
def atualizar_item(poc_id: uuid.UUID, item_id: uuid.UUID, payload: ItemUpdate, db: Session = Depends(get_db)):
    item = _get_item_or_404(db, poc_id, item_id)
    dados = payload.model_dump(exclude_unset=True)
    sessao_id = dados.pop("sessao_id", None)

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


def _escapar_html(texto: str) -> str:
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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
        cliente_origem=item.poc.cliente,
        data_origem=None,
        status_valor=StatusProcedimento.validado,
        versao=1,
        html=html,
        api_key=resolve_api_key(current_user),
        dono_id=current_user.id,
    )
    anexo.procedimento_id = procedimento.id
    db.commit()
    db.refresh(item)
    return item
