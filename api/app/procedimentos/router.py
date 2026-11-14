import logging
import uuid
from datetime import date
from html import escape as _escapar_html

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status as http_status
from pydantic import BaseModel, Field, ValidationError
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
    gerado_por_ia: bool = False,
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
        gerado_por_ia=gerado_por_ia,
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
        traducao = traduzir_procedimento_html(html, "en", titulo, api_key=api_key)
        if traducao.idioma_detectado in _IDIOMAS_SITE:
            procedimento.idioma_original = traducao.idioma_detectado
        if procedimento.idioma_original != "en":
            procedimento.traducoes = {"en": traducao.html_traduzido}
        procedimento.titulo_en = traducao.titulo_traduzido[:255]
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


# ---------------- 4.2: importação/exportação em JSON ----------------
# Schema documentado em docs/procedure-schema.md -- mesmos nomes de campo da API existente
# (ProcedimentoListItem/Detail), pra exportar e reimportar ser um round-trip direto, sem mapear
# nomes. Chunks/embeddings nunca entram no JSON: são sempre re-derivados de html_original, igual
# o upload manual e a sincronização entre instâncias já fazem (_criar_procedimento).


class ProcedimentoImportItem(BaseModel):
    id: uuid.UUID | None = None
    titulo: str = Field(min_length=1, max_length=255)
    titulo_en: str | None = Field(None, max_length=255)
    tags: list[str] = []
    categorias: list[str] = []
    cliente_origem: str | None = Field(None, max_length=255)
    data_origem: date | None = None
    status: StatusProcedimento = StatusProcedimento.rascunho
    versao: int = Field(1, ge=1)
    html_original: str = Field(min_length=1)
    idioma_original: str | None = Field(None, max_length=5)


class PreviaItemImportacao(BaseModel):
    indice: int
    titulo: str
    valido: bool
    erros: list[str]
    duplicado_id: uuid.UUID | None = None
    duplicado_titulo: str | None = None


class ResultadoImportacaoItem(BaseModel):
    indice: int
    titulo: str
    status: str  # "importado" | "sobrescrito" | "pulado" | "erro"
    erro: str | None = None
    id: uuid.UUID | None = None


class ImportarJsonIn(BaseModel):
    itens: list[dict]
    sobrescrever_ids: list[uuid.UUID] = []


def _itens_brutos(payload: list[dict] | dict) -> list[dict]:
    return payload if isinstance(payload, list) else [payload]


def _encontrar_duplicado(db: Session, item: ProcedimentoImportItem) -> Procedimento | None:
    """Por id (se o JSON trouxer um que já existe aqui) ou por título+categorias (proxy de
    "produto", já que Procedimento não tem um campo de produto único -- categorias é o que mais
    se aproxima e já é usado pra afinidade de busca em outro lugar)."""
    if item.id is not None:
        existente = db.get(Procedimento, item.id)
        if existente is not None:
            return existente
    query = db.query(Procedimento).filter(Procedimento.titulo == item.titulo)
    if item.categorias:
        query = query.filter(Procedimento.categorias.overlap(item.categorias))
    return query.first()


def _sobrescrever_conteudo_procedimento(
    db: Session, procedimento: Procedimento, item: ProcedimentoImportItem, api_key: str | None
) -> None:
    """Atualiza um procedimento existente no lugar (mesmo id, pra Classificacao/Anexo/RfiItem que
    já apontam pra ele não perderem o vínculo) em vez de criar um novo -- a escolha de "sobrescrever"
    na importação. Rechunka/reembeda do zero a partir do html novo, como qualquer upload."""
    secoes = extrair_secoes(item.html_original)
    if not secoes:
        raise ValueError("Nenhuma seção encontrada no HTML")
    procedimento.titulo = item.titulo
    procedimento.titulo_en = item.titulo_en[:255] if item.titulo_en else None
    procedimento.tags = item.tags
    procedimento.categorias = sorted({c for c in (normalizar(c) for c in item.categorias) if c})
    procedimento.cliente_origem = item.cliente_origem
    procedimento.data_origem = item.data_origem
    procedimento.status = item.status
    procedimento.versao = item.versao
    procedimento.html_original = item.html_original
    procedimento.idioma_original = item.idioma_original
    procedimento.traducoes = {}
    db.query(ProcedimentoChunk).filter(ProcedimentoChunk.procedimento_id == procedimento.id).delete()
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


@router.post("/importar-json/preview", response_model=list[PreviaItemImportacao])
def preview_importar_json(payload: list[dict] | dict, db: Session = Depends(get_db)):
    """Primeiro passo da importação: valida cada item (sem travar a resposta inteira por um item
    ruim) e aponta duplicados, sem gravar nada -- a tela de preview decide pular/sobrescrever
    antes do POST /importar-json de verdade."""
    previa = []
    for indice, bruto in enumerate(_itens_brutos(payload)):
        titulo_bruto = str(bruto.get("titulo") or "") if isinstance(bruto, dict) else ""
        try:
            item = ProcedimentoImportItem.model_validate(bruto)
        except ValidationError as exc:
            previa.append(
                PreviaItemImportacao(
                    indice=indice, titulo=titulo_bruto, valido=False,
                    erros=[f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()],
                )
            )
            continue
        duplicado = _encontrar_duplicado(db, item)
        previa.append(
            PreviaItemImportacao(
                indice=indice, titulo=item.titulo, valido=True, erros=[],
                duplicado_id=duplicado.id if duplicado else None,
                duplicado_titulo=duplicado.titulo if duplicado else None,
            )
        )
    return previa


@router.post("/importar-json", response_model=list[ResultadoImportacaoItem])
def importar_json(
    payload: ImportarJsonIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Importação de verdade, depois do preview: itens duplicados são pulados a não ser que o id
    do duplicado esteja em sobrescrever_ids (aí atualiza no lugar -- ver
    _sobrescrever_conteudo_procedimento). Um objeto só ou uma lista: o front sempre manda `itens`
    como lista (envolve um objeto único antes de chamar), então essa normalização já fica lá."""
    api_key = resolve_api_key(current_user)
    resultados = []
    for indice, bruto in enumerate(payload.itens):
        titulo_bruto = str(bruto.get("titulo") or "")
        try:
            item = ProcedimentoImportItem.model_validate(bruto)
        except ValidationError as exc:
            resultados.append(
                ResultadoImportacaoItem(
                    indice=indice, titulo=titulo_bruto, status="erro",
                    erro="; ".join(e["msg"] for e in exc.errors()),
                )
            )
            continue
        duplicado = _encontrar_duplicado(db, item)
        if duplicado is not None and duplicado.id not in payload.sobrescrever_ids:
            resultados.append(
                ResultadoImportacaoItem(indice=indice, titulo=item.titulo, status="pulado", id=duplicado.id)
            )
            continue
        try:
            if duplicado is not None:
                _sobrescrever_conteudo_procedimento(db, duplicado, item, api_key)
                resultados.append(
                    ResultadoImportacaoItem(indice=indice, titulo=item.titulo, status="sobrescrito", id=duplicado.id)
                )
            else:
                novo = _criar_procedimento(
                    db,
                    titulo=item.titulo,
                    tags=item.tags,
                    categorias=item.categorias,
                    cliente_origem=item.cliente_origem,
                    data_origem=item.data_origem,
                    status_valor=item.status,
                    versao=item.versao,
                    html=item.html_original,
                    api_key=api_key,
                    dono_id=current_user.id,
                )
                if item.titulo_en:
                    novo.titulo_en = item.titulo_en[:255]
                    db.commit()
                resultados.append(ResultadoImportacaoItem(indice=indice, titulo=item.titulo, status="importado", id=novo.id))
        except Exception as exc:  # noqa: BLE001 - um item com problema não pode travar o lote
            db.rollback()
            logger.exception("Falha ao importar procedimento %r (índice %d)", item.titulo, indice)
            resultados.append(ResultadoImportacaoItem(indice=indice, titulo=item.titulo, status="erro", erro=str(exc)))
    return resultados


class ProcedimentoExportOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    titulo: str
    titulo_en: str | None
    tags: list[str]
    categorias: list[str]
    cliente_origem: str | None
    data_origem: date | None
    status: StatusProcedimento
    versao: int
    html_original: str
    idioma_original: str | None


@router.get("/exportar-json", response_model=list[ProcedimentoExportOut])
def exportar_procedimentos_json(
    ids: str | None = Query(None, description="ids separados por vírgula; omitido = todos"),
    db: Session = Depends(get_db),
):
    query = db.query(Procedimento)
    if ids:
        try:
            lista = [uuid.UUID(x.strip()) for x in ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "ids inválidos")
        query = query.filter(Procedimento.id.in_(lista))
    return query.order_by(Procedimento.created_at.desc()).all()


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
        traducao = traduzir_procedimento_html(procedimento.html_original, lang, procedimento.titulo, api_key=api_key)
    except Exception:
        logger.warning("Falha ao traduzir procedimento %s para %s", procedimento.id, lang, exc_info=True)
        return procedimento.html_original, procedimento.idioma_original

    if traducao.idioma_detectado in _IDIOMAS_SITE:
        procedimento.idioma_original = traducao.idioma_detectado
    # Backfill de titulo_en pra quem a tradução ansiosa do upload falhou (rede, quota) e só deu certo
    # agora, numa visita em inglês -- mesmo titulo_traduzido que a chamada acima já devolveu, sem
    # chamada extra ao Gemini.
    if lang == "en" and not procedimento.titulo_en:
        procedimento.titulo_en = traducao.titulo_traduzido[:255]
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


@router.get("/{procedimento_id}/exportar-json", response_model=ProcedimentoExportOut)
def exportar_procedimento_json(procedimento_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_procedimento_or_404(db, procedimento_id)


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


@router.post("/{procedimento_id}/validar")
def validar_procedimento(
    procedimento_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Eleva um procedimento `rascunho` pra `validado` -- a única forma disso acontecer depois da
    criação (até aqui, status só era fixado no momento de criar: upload manual ou
    _criar_procedimento). Deliberadamente genérico (não só pros rascunhos gerados por IA, ver
    app/classificacao/service.py::gerar_rascunho_procedimento): qualquer rascunho manual antigo
    também ganha um jeito de ser promovido. Sem trava de dono -- mesma política de baixo atrito já
    usada pelo checkbox "Validado" de anexo de PoC (validar_anexo). Passar a validado faz o
    procedimento entrar automaticamente na busca de candidatos pra outros itens
    (_buscar_candidatos já filtra só status=validado) -- nenhuma mudança extra necessária ali."""
    procedimento = _get_procedimento_or_404(db, procedimento_id)
    if procedimento.status != StatusProcedimento.rascunho:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Só um procedimento em rascunho pode ser validado")
    procedimento.status = StatusProcedimento.validado
    db.commit()
    return {"id": procedimento.id, "status": procedimento.status}


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
