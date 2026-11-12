"""Recursos do planejador: importar documento do cliente (sugestão de dados do projeto, rede,
produtos e testes do catálogo do planejador), sugestão de aderência por pesquisa na web e rascunho
de procedimento guiado por IA (gerar_rascunho_planner -- este último é a ÚNICA função aqui que grava
algo no banco, um Procedimento novo; todo o resto é sem estado). Contrato com o
`poc-planner/index.html` (R1/R7 em poc-planner/docs/design-unification.md):

- o catálogo de testes é do PLANEJADOR e vem na requisição; aqui nunca se inventa um id;
- nada de credencial: nem o prompt pede, nem a resposta tem lugar pra isso (lista fechada de campos);
- o que sai daqui são SUGESTÕES -- o planejador mostra uma tela de revisão antes de aplicar."""

import ipaddress
import json
import re
import uuid

from google.genai import types
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.gemini import (
    FonteEvidencia,
    _TEXT_MODEL,
    _gerar_com_retry,
    gerar_procedimento_guiado,
    pesquisar_implementacao_item,
    pesquisar_viabilidade_web,
)
from app.models import OrigemConhecimento, Procedimento, StatusProcedimento
from app.procedimentos.router import _criar_procedimento

PRODUTOS_PLANEJADOR = (
    "virtualization", "rancher", "security", "storage", "observability", "registry", "appcollection", "manager",
)
# Mesmas categorias do TEST_FIT do planejador, com a definição que a IA deve usar.
CATEGORIAS_ADERENCIA = {
    "native": "funciona de forma nativa, sem configuração especial",
    "config": "nativo, mas exige configuração/ajuste documentado",
    "rancher": "só com Rancher Prime (ou outro produto pago da família)",
    "third": "depende de produto ou serviço de terceiros",
    "validate": "não há evidência suficiente: validar em laboratório",
    "gap": "gap conhecido: a documentação diz que não é suportado",
}
LIMITE_TESTES_CATALOGO = 500
LIMITE_TESTES_ADERENCIA = 5
_IDIOMAS = {"pt": "português do Brasil", "en": "English", "es": "español"}


class ProjetoSugerido(BaseModel):
    nome_projeto: str = ""
    cliente: str = ""
    organizacao: str = ""
    responsavel: str = ""
    email_responsavel: str = ""
    data_alvo: str = ""
    caso_de_uso: str = ""
    problema_de_negocio: str = ""
    ambiente_alvo: str = ""


class RedeSugerida(BaseModel):
    cidr_gerenciamento: str = ""
    gateway: str = ""
    vip_cluster: str = ""
    pool_ip_inicio: str = ""
    pool_ip_fim: str = ""
    ntp: str = ""
    dns: str = ""


class TesteSugerido(BaseModel):
    id: str
    motivo: str = ""


class MaquinaSugerida(BaseModel):
    produto: str
    hostname: str = ""
    ip: str = ""


class ExtracaoHidratacao(BaseModel):
    projeto: ProjetoSugerido
    rede: RedeSugerida
    produtos: list[str] = []
    testes: list[TesteSugerido] = []
    maquinas: list[MaquinaSugerida] = []


_HIDRATACAO_PROMPT = """\
Você preenche SUGESTÕES para o assistente de planejamento de PoC SUSE a partir do documento acima \
(e-mail, transcrição de reunião, edital, planilha ou texto). Um engenheiro vai revisar tudo antes de aplicar.

Regras:
- Só preencha o que estiver explícito no documento; o que não estiver, deixe string vazia. Nunca invente \
nomes, e-mails, datas nem IPs.
- projeto: nome_projeto, cliente (empresa/órgão final), organizacao (se diferente do cliente), responsavel \
e email_responsavel (a pessoa técnica responsável pela PoC do lado da SUSE, só se identificável), data_alvo \
(AAAA-MM-DD, prazo/entrega da PoC), caso_de_uso, problema_de_negocio e ambiente_alvo (resumos de 1-2 frases).
- rede: cidr_gerenciamento, gateway, vip_cluster, pool_ip_inicio, pool_ip_fim, ntp, dns, só se estiverem escritos. \
ntp e dns podem ser hostname ou IP, um valor ou uma lista (copie como está escrito no documento).
- produtos: quais destes ids fazem parte do escopo (use só estes ids):
  virtualization (SUSE Virtualization/Harvester), rancher (Rancher Prime), security (SUSE Security/NeuVector), \
storage (SUSE Storage/Longhorn), observability (SUSE Observability/StackState), registry (SUSE Private \
Registry), appcollection (SUSE Application Collection), manager (SUSE Multi-Linux Manager).
- maquinas: para cada máquina/nó que o documento nomear com hostname e/ou IP, emita {{produto, hostname, ip}} \
com "produto" um dos ids da lista acima. Quando um produto tiver mais de uma máquina (ex.: vários nós do \
Virtualization), liste-as NA MESMA ORDEM em que aparecem no documento -- a ordem importa, é assim que o \
planejador associa cada máquina ao nó certo. Só inclua o que estiver escrito; nunca invente hostname nem IP.
- testes: quais testes do CATÁLOGO abaixo o documento pede ou implica (ex.: criar máquinas virtuais implica \
SUSE Virtualization e o teste de criar VM). Use só os ids do catálogo, com um "motivo" curto citando o trecho \
ou a ideia do documento. Se nada se aplicar, lista vazia.
- NUNCA inclua, repita nem infira senhas, tokens, chaves, licenças ou qualquer credencial, mesmo que apareçam \
no documento. Não preencha dimensionamento (CPU/RAM/disco), portas nem arquitetura.

CATÁLOGO DE TESTES (id | produto | título):
{catalogo}
"""


def validar_catalogo(bruto: str) -> dict:
    """Valida o catálogo enviado pelo planejador (JSON em texto). Levanta ValueError se estiver torto."""
    try:
        cat = json.loads(bruto)
    except (TypeError, ValueError):
        raise ValueError("catálogo inválido")
    if not isinstance(cat, dict) or not isinstance(cat.get("tests"), list) or len(cat["tests"]) > LIMITE_TESTES_CATALOGO:
        raise ValueError("catálogo inválido")
    testes = {}
    for t in cat["tests"]:
        if not isinstance(t, dict) or not all(isinstance(t.get(k), str) for k in ("id", "product", "title")):
            raise ValueError("catálogo inválido")
        testes[t["id"][:80]] = {"product": t["product"][:40], "title": t["title"][:200]}
    return {"tests": testes}


def _texto(v, limite: int) -> str:
    return re.sub(r"\s+", " ", v).strip()[:limite] if isinstance(v, str) else ""


def _ip(v: str) -> str:
    try:
        return str(ipaddress.IPv4Address(v.strip()))
    except ValueError:
        return ""


def _cidr(v: str) -> str:
    try:
        return str(ipaddress.IPv4Interface(v.strip()).with_prefixlen) if "/" in v else ""
    except ValueError:
        return ""


def montar_hidratacao(extraido: ExtracaoHidratacao, catalogo: dict) -> dict:
    """Resposta no formato `suse-poc-hydration` (chaves do próprio planejador). Descarta o que não for do
    catálogo e o que não tiver cara de dado válido; o planejador valida de novo do lado dele."""
    p, r = extraido.projeto, extraido.rede
    email = _texto(p.email_responsavel, 120)
    data = _texto(p.data_alvo, 10)
    projeto = {
        "projectName": _texto(p.nome_projeto, 120),
        "clientOrganization": _texto(p.cliente, 120),
        "organization": _texto(p.organizacao, 120),
        "leadEngineer": _texto(p.responsavel, 120),
        "leadEmail": email if re.fullmatch(r"[^\s@<>\"']+@[^\s@<>\"']+\.[^\s@<>\"']+", email) else "",
        "targetDate": data if re.fullmatch(r"\d{4}-\d{2}-\d{2}", data) else "",
        "presalesUseCase": _texto(p.caso_de_uso, 600),
        "businessIssue": _texto(p.problema_de_negocio, 600),
        "targetInfrastructure": _texto(p.ambiente_alvo, 600),
    }
    rede = {
        "managementCidr": _cidr(r.cidr_gerenciamento), "gatewayIp": _ip(r.gateway), "clusterVip": _ip(r.vip_cluster),
        "ipPoolStart": _ip(r.pool_ip_inicio), "ipPoolEnd": _ip(r.pool_ip_fim),
        # Texto livre (hostname ou IP, um valor ou lista) -- não dá pra validar como IP estrito, o
        # próprio planejador guarda isso como string livre (state.network.ntpServers/dnsServers).
        "ntpServers": _texto(r.ntp, 200), "dnsServers": _texto(r.dns, 200),
    }
    vistos: set[str] = set()
    testes = []
    for t in extraido.testes:
        if t.id in catalogo["tests"] and t.id not in vistos:
            vistos.add(t.id)
            testes.append({"id": t.id, "reason": _texto(t.motivo, 300)})
    maquinas = []
    for m in extraido.maquinas:
        if m.produto not in PRODUTOS_PLANEJADOR:
            continue
        hostname, ip = _texto(m.hostname, 255), _ip(m.ip)
        if hostname or ip:
            maquinas.append({"product": m.produto, "hostname": hostname, "ip": ip})
    return {
        "kind": "suse-poc-hydration",
        "schema": 1,
        "project": {k: v for k, v in projeto.items() if v},
        "network": {k: v for k, v in rede.items() if v},
        "selectedProducts": {pid: True for pid in PRODUTOS_PLANEJADOR if pid in extraido.produtos},
        "tests": testes,
        "vms": maquinas,
    }


def extrair_hidratacao(
    pdf_bytes: bytes | None, texto: str | None, catalogo: dict, api_key: str | None, model: str | None
) -> dict:
    if pdf_bytes:
        conteudo: list = [types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")]
    elif texto:
        conteudo = [texto]
    else:
        raise ValueError("Informe pdf_bytes ou texto")
    linhas = "\n".join(f"{i} | {t['product']} | {t['title']}" for i, t in catalogo["tests"].items())
    conteudo.append(_HIDRATACAO_PROMPT.format(catalogo=linhas))
    response = _gerar_com_retry(
        api_key=api_key,
        contexto="planner_hidratar",
        model=model or _TEXT_MODEL,
        contents=conteudo,
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=ExtracaoHidratacao),
    )
    parsed = response.parsed
    extraido = parsed if isinstance(parsed, ExtracaoHidratacao) else ExtracaoHidratacao.model_validate_json(response.text)
    return montar_hidratacao(extraido, catalogo)


class AvaliacaoAderencia(BaseModel):
    categoria: str
    justificativa: str


_ADERENCIA_PROMPT = """\
Com base na pesquisa abaixo, classifique a ADERÊNCIA do teste de PoC no produto SUSE, escolhendo UMA categoria:
{categorias}

Teste: {titulo}
Resultado esperado: {esperado}

Pesquisa:
\"\"\"
{pesquisa}
\"\"\"

Se a pesquisa não trouxer evidência clara, use "validate" (nunca "native" por palavras genéricas). Use "gap" só \
com evidência explícita de que não é suportado. Responda em {idioma}; justificativa: 1-2 frases objetivas.
"""


def sugerir_aderencia(teste: dict, fits: list[str], lang: str, api_key: str | None, model: str | None) -> dict:
    """Pesquisa na web (Gemini com grounding) e classifica numa categoria do planejador. Sem estado."""
    permitidas = [f for f in fits if f in CATEGORIAS_ADERENCIA] or list(CATEGORIAS_ADERENCIA)
    consulta = f"Produto SUSE ({teste['product']}): {teste['title']}. Resultado esperado: {teste['expected']}"
    pesquisa, fontes = pesquisar_viabilidade_web(consulta, api_key=api_key, model=model)
    response = _gerar_com_retry(
        api_key=api_key,
        contexto="planner_aderencia",
        model=model or _TEXT_MODEL,
        contents=_ADERENCIA_PROMPT.format(
            categorias="\n".join(f'- {c}: {CATEGORIAS_ADERENCIA[c]}' for c in permitidas),
            titulo=teste["title"], esperado=teste["expected"] or "-", pesquisa=pesquisa or "(sem resultado)",
            idioma=_IDIOMAS.get(lang, _IDIOMAS["pt"]),
        ),
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=AvaliacaoAderencia),
    )
    parsed = response.parsed
    av = parsed if isinstance(parsed, AvaliacaoAderencia) else AvaliacaoAderencia.model_validate_json(response.text)
    return montar_aderencia(teste["id"], av, fontes, permitidas)


def montar_aderencia(teste_id: str, av: AvaliacaoAderencia, fontes: list[FonteEvidencia], permitidas: list[str]) -> dict:
    # Categoria fora da lista (ou sem fontes para sustentar mais que "validar") nunca vira certeza.
    fit = av.categoria if av.categoria in permitidas else "validate"
    if not fontes and fit in ("native", "config", "gap") and "validate" in permitidas:
        fit = "validate"
    return {
        "id": teste_id,
        "fit": fit,
        "rationale": _texto(av.justificativa, 600),
        "sources": _fontes_unicas(fontes),
    }


def _fontes_unicas(fontes: list[FonteEvidencia]) -> list[dict]:
    """O grounding do Gemini repete a mesma fonte; mostra cada URL http(s) uma vez, no máximo 5."""
    vistas: set[str] = set()
    out = []
    for f in fontes:
        if re.match(r"https?://", f.url) and f.url not in vistas:
            vistas.add(f.url)
            out.append({"title": _texto(f.titulo, 150) or f.url, "url": f.url})
    return out[:5]


def _contexto_planner(produto: str, cliente: str, escopo: str) -> str:
    partes = [f"Produto SUSE: {produto}"] if produto else []
    if cliente:
        partes.append(f"Cliente: {cliente}")
    if escopo:
        partes.append(f"Escopo da PoC: {escopo}")
    return "\n".join(partes)


def gerar_rascunho_planner(
    db: Session,
    titulo: str,
    esperado: str,
    produto: str,
    cliente: str,
    escopo: str,
    dono_id: uuid.UUID,
    api_key: str | None,
    model: str | None,
) -> Procedimento:
    """Mesmo mecanismo de app/classificacao/service.py::gerar_rascunho_procedimento (pesquisa com
    grounding + geração estruturada do HTML), só que pra um teste do planejador em vez de um
    Item/Classificacao de PoC -- o teste ainda não tem Item nenhum nesse ponto (só ganha um se/
    quando o plano for "habilitado" como execução, ver execution_payload no poc-control). Cria como
    status=rascunho (invisível pra _buscar_candidatos até o usuário validar) e
    origem=OrigemConhecimento.planejador, pra distinguir de um rascunho nascido de um Item de PoC
    de verdade."""
    item_texto = f"{titulo}\nResultado esperado: {esperado}" if esperado else titulo
    contexto = _contexto_planner(produto, cliente, escopo)
    pesquisa_texto, fontes = pesquisar_implementacao_item(item_texto, contexto, api_key=api_key, model=model)
    rascunho = gerar_procedimento_guiado(item_texto, contexto, pesquisa_texto, fontes, api_key=api_key, model=model)
    return _criar_procedimento(
        db,
        titulo=rascunho.titulo[:255],
        tags=[produto] if produto else [],
        categorias=[],
        cliente_origem=cliente or None,
        data_origem=None,
        status_valor=StatusProcedimento.rascunho,
        versao=1,
        html=rascunho.html,
        api_key=api_key,
        dono_id=dono_id,
        origem=OrigemConhecimento.planejador,
        gerado_por_ia=True,
    )
