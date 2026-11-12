import json
import pathlib
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db import get_db
from app.deps import get_current_user
from app.gemini import interpretar_erro_gemini
from app.gemini_key import resolve_api_key, resolve_model
from app.models import User
from app.planner.service import (
    LIMITE_TESTES_ADERENCIA,
    extrair_hidratacao,
    gerar_rascunho_planner,
    sugerir_aderencia,
    validar_catalogo,
)
from app.pocs.planilha_import import texto_de_planilha
from app.pocs.resultados import historico_por_catalogo

# Recursos do "SUSE PoC Planner" (poc-planner/index.html) que precisam de servidor. A maioria é sem
# estado (o registro único da PoC é a ADR 1 do plano de unificação); a exceção é /procedure-draft,
# que cria um Procedimento de verdade (ver gerar_rascunho_planner).
router = APIRouter(prefix="/api/planner", tags=["planner"])

_LIMITE_ARQUIVO = 25 * 1024 * 1024


@router.get("/capabilities")
def capabilities():
    """Sem autenticação e sem corpo de entrada: é como o planejador descobre que está servido por um
    poc-control (e só então mostra os controles extras). Não revela nada além da lista de recursos."""
    return {
        "kind": "poc-control",
        "schema": 1,
        "features": ["hydrate", "feasibility", "procedures", "execution", "history", "draft"],
    }


@router.post("/hydrate")
def hydrate(
    arquivo: UploadFile | None = File(None),
    texto: str | None = Form(None),
    catalogo: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """Documento do cliente -> sugestões para o planejador (formato `suse-poc-hydration`). Síncrono: o
    planejador mostra uma tela de revisão com a resposta. Aceita PDF, XLSX/CSV, JSON/texto (UTF-8) ou texto colado."""
    try:
        cat = validar_catalogo(catalogo)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    pdf_bytes: bytes | None = None
    texto_arquivo: str | None = None
    if arquivo is not None and arquivo.filename:
        conteudo = arquivo.file.read(_LIMITE_ARQUIVO + 1)
        if not conteudo:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Arquivo vazio")
        if len(conteudo) > _LIMITE_ARQUIVO:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Arquivo maior que 25 MB")
        extensao = pathlib.Path(arquivo.filename).suffix.lower()
        if extensao == ".pdf":
            pdf_bytes = conteudo
        elif extensao in (".xlsx", ".csv"):
            try:
                texto_arquivo = texto_de_planilha(conteudo, extensao)
            except ValueError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        else:
            try:
                texto_arquivo = conteudo.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Não foi possível ler o arquivo como texto; envie PDF, XLSX/CSV ou texto/JSON em UTF-8",
                )
    texto_final = (texto or "").strip() or texto_arquivo
    if not pdf_bytes and not texto_final:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Envie um arquivo ou cole o texto")

    try:
        return extrair_hidratacao(
            pdf_bytes, texto_final, cat, resolve_api_key(current_user), resolve_model(current_user)
        )
    except Exception as exc:  # noqa: BLE001 - qualquer erro da chamada ao Gemini vira 502 com mensagem acionável
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, interpretar_erro_gemini(exc))


class TesteAderencia(BaseModel):
    id: str = Field(max_length=80)
    product: str = Field(default="", max_length=40)
    title: str = Field(max_length=300)
    expected: str = Field(default="", max_length=600)


class AderenciaIn(BaseModel):
    lang: str = "pt"
    fits: list[str] = []
    tests: list[TesteAderencia] = Field(min_length=1, max_length=LIMITE_TESTES_ADERENCIA)


@router.post("/feasibility")
def feasibility(payload: AderenciaIn, current_user: User = Depends(get_current_user)):
    """Sugestão de aderência por pesquisa na web (Gemini com grounding), uma categoria do planejador por
    teste. Sem estado: o planejador guarda como sugestão externa não confirmada."""
    api_key, model = resolve_api_key(current_user), resolve_model(current_user)
    resultados = []
    for t in payload.tests:
        try:
            resultados.append(sugerir_aderencia(t.model_dump(), payload.fits, payload.lang, api_key, model))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, interpretar_erro_gemini(exc))
    return {"kind": "suse-poc-feasibility", "schema": 1, "results": resultados}


@router.get("/history")
def history(
    ids: str = Query(..., description="ids de teste do catálogo, separados por vírgula (até 200)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Histórico anônimo de resultados por teste do catálogo do planejador (ADR 1): quantas execuções, quantas sem
    problemas e a aderência mais nativa entre as que deram certo. Só leitura, sem estado, e SÓ uma sugestão: o planejador
    mostra e a pessoa confirma."""
    lista = list(dict.fromkeys(i.strip() for i in ids.split(",") if i.strip()))
    if not lista or len(lista) > 200 or any(len(i) > 80 for i in lista):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Informe de 1 a 200 ids de teste")
    return {"kind": "suse-poc-history", "schema": 1, "results": historico_por_catalogo(db, lista)}


class ProcedureDraftIn(BaseModel):
    test: TesteAderencia
    client: str = Field(default="", max_length=200)
    scope: str = Field(default="", max_length=2000)


class ProcedureDraftOut(BaseModel):
    id: uuid.UUID
    titulo: str
    tags: list[str]
    cliente_origem: str | None
    status: str
    versao: int
    data_origem: date | None
    html_original: str


@router.post("/procedure-draft", response_model=ProcedureDraftOut)
def procedure_draft(
    payload: ProcedureDraftIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rascunho de procedimento guiado por IA pra um teste do planejador sem nenhum procedimento que
    sirva na biblioteca local (mesmo mecanismo de app/classificacao/service.py::gerar_rascunho_procedimento,
    usado pro lado amarelo da execução de PoC -- ver gerar_rascunho_planner). Cria um Procedimento de
    verdade (status=rascunho, gerado_por_ia=True, origem=planejador): some da busca automática de
    candidatos até o próprio usuário confirmar que executou com sucesso e validar, mas já aparece em
    GET /api/procedimentos pro planejador puxar e linkar como se fosse um procedimento do servidor
    (ver serverProcClean/serverProcToLib em poc-planner/index.html). Chamada síncrona de propósito:
    pesquisa + geração + chunking/embedding/tradução pode passar de 1 minuto, mas é o usuário quem
    aciona isso deliberadamente (botão dedicado na tela de vincular procedimento)."""
    try:
        procedimento = gerar_rascunho_planner(
            db,
            payload.test.title,
            payload.test.expected,
            payload.test.product,
            payload.client.strip(),
            payload.scope.strip(),
            current_user.id,
            resolve_api_key(current_user),
            resolve_model(current_user),
        )
    except Exception as exc:  # noqa: BLE001 - qualquer erro da chamada ao Gemini vira 502 com mensagem acionável
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, interpretar_erro_gemini(exc))
    return ProcedureDraftOut(
        id=procedimento.id,
        titulo=procedimento.titulo,
        tags=procedimento.tags,
        cliente_origem=procedimento.cliente_origem,
        status=procedimento.status.value,
        versao=procedimento.versao,
        data_origem=procedimento.data_origem,
        html_original=procedimento.html_original,
    )
