import logging
import math
import time

from google import genai
from google.genai import types
from google.genai import errors as genai_errors
from pydantic import BaseModel

from app.categorias import descricoes_formatadas
from app.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536
_MODEL = "gemini-embedding-001"
_TEXT_MODEL = "gemini-3.8-flash"


def _client(api_key: str | None = None) -> genai.Client:
    return genai.Client(api_key=api_key or settings.gemini_api_key)


def modelo_efetivo(model: str | None) -> str:
    """Nome do modelo de texto que uma chamada vai de fato usar, aplicando a mesma regra
    (`model or _TEXT_MODEL`) usada dentro de cada função deste módulo — pra quem chama poder
    persistir/exibir qual modelo respondeu sem duplicar o fallback."""
    return model or _TEXT_MODEL


class ModeloDisponivel(BaseModel):
    nome: str
    nome_exibicao: str


_PALAVRAS_EXCLUIDAS_SELETOR = ("tts", "image", "transcribe", "computer-use", "robotics", "omni", "banana")


def listar_modelos_texto(api_key: str | None = None) -> list[ModeloDisponivel]:
    """Modelos de texto que a chave de API (pessoal ou compartilhada) tem acesso de verdade,
    pra Minha conta oferecer um seletor em vez de um campo livre onde o usuário tem que
    adivinhar/digitar um nome de modelo que pode nem existir pro plano da chave dele.

    O catálogo completo do Gemini inclui bem mais que os modelos de chat/texto que esta função
    de fato usa (TTS, geração de imagem, transcrição, robótica, etc. — todos respondem
    `generateContent`, mas não servem pros prompts com `response_schema` deste app). Por isso,
    além de exigir o prefixo "gemini-", filtra por palavra-chave em vez de uma lista fixa de
    nomes, que ficaria desatualizada a cada novo lançamento do Google."""
    client = _client(api_key)
    modelos = []
    for m in client.models.list(config={"page_size": 200}):
        if "generateContent" not in (m.supported_actions or []):
            continue
        nome = (m.name or "").removeprefix("models/")
        if not nome.startswith("gemini-"):
            continue
        if any(palavra in nome for palavra in _PALAVRAS_EXCLUIDAS_SELETOR):
            continue
        modelos.append(ModeloDisponivel(nome=nome, nome_exibicao=m.display_name or nome))
    modelos.sort(key=lambda x: x.nome)
    return modelos


def interpretar_erro_gemini(exc: Exception) -> str:
    """Traduz os erros mais comuns da API do Gemini pra uma mensagem acionável, em vez do
    dump cru da exceção (ex.: "503 UNAVAILABLE {'error': {...}}"), que é o que aparecia antes
    em erro_extracao e deixava o usuário sem saber se era pra tentar de novo, trocar a chave
    ou reportar o bug."""
    codigo = getattr(exc, "code", None)
    if codigo == 503:
        return (
            "O Gemini está temporariamente sobrecarregado (alta demanda no modelo configurado). "
            "Não é um problema com a sua chave de API — tente novamente em alguns minutos."
        )
    if codigo == 429:
        return (
            "O limite de uso (quota) da chave de API do Gemini foi atingido. Aguarde um pouco "
            "ou confira o plano da chave em aistudio.google.com."
        )
    if codigo in (401, 403):
        return (
            "A chave de API do Gemini foi recusada (inválida, revogada, ou sem permissão para "
            "este modelo). Confira a chave cadastrada em Minha conta."
        )
    if codigo == 404:
        return (
            "O modelo do Gemini configurado não foi encontrado (nome errado, ou a chave não tem "
            "acesso a ele). Confira o campo \"Modelo do Gemini\" em Minha conta."
        )
    if codigo == 500:
        return "Erro interno do Gemini. Tente novamente em alguns instantes."
    return f"Erro inesperado ao chamar o Gemini: {exc}"


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values))
    if norm == 0:
        return values
    return [v / norm for v in values]


def embed_document(texto: str, api_key: str | None = None) -> list[float]:
    client = _client(api_key)
    result = _com_retry(
        lambda: client.models.embed_content(
            model=_MODEL,
            contents=texto,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=EMBEDDING_DIM,
            ),
        ),
        api_key=api_key,
        contexto="embed_document",
        modelo=_MODEL,
    )
    [embedding] = result.embeddings
    return _normalize(embedding.values)


def embed_query(texto: str, api_key: str | None = None) -> list[float]:
    client = _client(api_key)
    result = _com_retry(
        lambda: client.models.embed_content(
            model=_MODEL,
            contents=texto,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=EMBEDDING_DIM,
            ),
        ),
        api_key=api_key,
        contexto="embed_query",
        modelo=_MODEL,
    )
    [embedding] = result.embeddings
    return _normalize(embedding.values)


class FaseExtraida(BaseModel):
    numero: int
    titulo: str
    descricao: str


class ItemExtraido(BaseModel):
    codigo: str
    titulo: str
    descricao: str
    criterio_aceite: str
    categoria: str
    categoria_codigo: str = ""
    fase: int
    ref: str = ""


class PrerequisitoExtraido(BaseModel):
    titulo: str
    descricao: str


class ExtracaoPoc(BaseModel):
    titulo_sugerido: str
    cliente_sugerido: str
    fases: list[FaseExtraida]
    itens: list[ItemExtraido]
    prerequisitos: list[PrerequisitoExtraido]


_EXTRACAO_PROMPT = """\
Você é um Solutions Architect lendo um documento de escopo/plano de testes de uma PoC (prova de conceito) \
técnica para extrair uma estrutura de acompanhamento.

O documento pode vir em formatos diferentes:
- Um PDF ou texto livre de escopo/plano de testes.
- Um JSON exportado pela ferramenta interna de planejamento de PoC ("SUSE PoC Planner"), com os campos \
de interesse em `project.projectName`, `project.clientOrganization`, `selectedProducts` (produtos \
habilitados) e `testCases` (um array de casos de teste por produto, cada um com `text`, `fit`, `led`, \
`owner`, `evidence`, `notes`) — esses campos podem estar na raiz do JSON (formato antigo) ou dentro de \
um campo `planner` (formato atual: `{schema, planner: {project, selectedProducts, testCases, ...}, eib, \
poc_markdown}` — ignore `eib` e `poc_markdown`, são derivados). Se for esse formato: use \
`project.projectName` como título sugerido e `project.clientOrganization` (ou `project.organization`) \
como cliente sugerido; agrupe os itens por produto (as chaves marcadas `true` em `selectedProducts`) \
como fases; cada entrada de `testCases[<produto>]` é um item, com `titulo` a partir de `text`, \
`categoria` a partir do nome do produto, e `criterio_aceite` inferido do próprio `text` (esse formato \
não tem um campo de critério separado).
- Uma planilha (XLSX/CSV) convertida em texto tabular, com linhas no formato "coluna1 | coluna2 | ...", \
geralmente com uma linha de cabeçalho. É comum ser um caderno de testes/checklist comparando um produto \
de referência (ex. "VMware vCenter") com o produto avaliado, com colunas como categoria/tópico, nome da \
funcionalidade, se o concorrente suporta, se o produto avaliado suporta (S/N ou similar) e uma observação/ \
justificativa. Os nomes exatos das colunas variam de planilha para planilha — identifique pelo conteúdo, \
não por nomes fixos. Trate cada linha de dado (não a de cabeçalho) como um item: `titulo` a partir da \
coluna de funcionalidade/requisito; `categoria` a partir da coluna de tópico/agrupamento (já vem repetida \
em todas as linhas do grupo); `criterio_aceite` enunciando a funcionalidade como requisito de aceite (ex.: \
"Suportar <funcionalidade>"); `descricao` a partir da coluna de observação/justificativa, se houver (senão \
repita o critério de aceite de forma mais detalhada). Agrupe os itens em fases a partir das categorias.

Devolva:
- titulo_sugerido: título curto da PoC (produto/tecnologia principal).
- cliente_sugerido: nome do cliente, se identificável no documento (senão string vazia).
- fases: agrupamento lógico do plano de testes em fases sequenciais (ex.: "Instalação e arquitetura", \
"Redes", "Storage", "Alta disponibilidade"...). Use as fases já indicadas no documento se existirem; \
senão, agrupe os itens por tema técnico em fases sensatas, numeradas a partir de 1.
- itens: cada cenário/caso de teste do plano, com:
  - codigo: identificador curto (reaproveite a numeração do documento se houver, ex. "3.2"; senão gere \
sequencial dentro da fase, ex. "1.1", "1.2").
  - titulo: frase curta do que será testado/demonstrado.
  - descricao: o que o teste envolve.
  - criterio_aceite: o que caracteriza sucesso (se o documento não disser explicitamente, infira algo \
razoável a partir do título/descrição).
  - categoria: área técnica em texto livre (ex.: "Virtualização", "Storage", "Rede", "Segurança", \
"Banco de Dados", "Backup", "DR") -- pode ser mais específica que a lista de categoria_codigo abaixo.
  - categoria_codigo: SE o item se encaixar claramente numa destas áreas do portfólio SUSE, o código \
correspondente (senão string vazia -- não force um código pra item que não seja sobre isso):
{categorias}
  - fase: número da fase (da lista "fases" acima) a que esse item pertence.
  - ref: referência à seção/página do documento original, se houver (senão string vazia).
- prerequisitos: pré-requisitos técnicos mencionados no documento (hardware, rede, acessos, software, \
times envolvidos) como título curto + descrição. Lista vazia se o documento não tratar disso.

Responda só com os dados pedidos, em português, sem inventar itens que não tenham base no documento.
""".replace("{categorias}", descricoes_formatadas())


_RETRY_CODES = {429, 500, 503}


def _com_retry(operacao, *, api_key: str | None, contexto: str, modelo: str | None):
    """Executa `operacao()` com retry/backoff exponencial para erros transitórios do Gemini
    (429/500/503), logando cada tentativa — nunca a chave em si, só se é a pessoal ou a
    compartilhada. É isso que faz `docker logs poc-control-api-1` mostrar o que de fato
    aconteceu numa falha (qual operação, qual modelo, quantas tentativas, qual código), em vez
    de só o 500 genérico que chegava no front antes."""
    tentativas = 4
    espera = 5
    ultimo_erro: Exception | None = None
    origem_chave = "pessoal" if api_key else "compartilhada"

    for tentativa in range(1, tentativas + 1):
        try:
            resultado = operacao()
            if tentativa > 1:
                logger.info(
                    "Gemini [%s] ok na tentativa %d/%d (modelo=%s, chave=%s)",
                    contexto, tentativa, tentativas, modelo, origem_chave,
                )
            return resultado
        except genai_errors.APIError as exc:
            ultimo_erro = exc
            codigo = getattr(exc, "code", None)
            vai_tentar_de_novo = codigo in _RETRY_CODES and tentativa < tentativas
            logger.warning(
                "Gemini [%s] falhou na tentativa %d/%d (modelo=%s, chave=%s): codigo=%s %s%s",
                contexto, tentativa, tentativas, modelo, origem_chave, codigo, exc,
                f" — nova tentativa em {espera}s" if vai_tentar_de_novo else " — desistindo",
            )
            if not vai_tentar_de_novo:
                raise
            time.sleep(espera)
            espera *= 2

    assert ultimo_erro is not None
    raise ultimo_erro


def _gerar_com_retry(
    *, api_key: str | None = None, contexto: str = "gemini", **kwargs
) -> types.GenerateContentResponse:
    client = _client(api_key)
    return _com_retry(
        lambda: client.models.generate_content(**kwargs),
        api_key=api_key,
        contexto=contexto,
        modelo=kwargs.get("model"),
    )


def extrair_itens_poc(
    pdf_bytes: bytes | None = None,
    texto: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> ExtracaoPoc:
    if pdf_bytes:
        conteudo: list = [types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")]
    elif texto:
        conteudo = [texto]
    else:
        raise ValueError("Informe pdf_bytes ou texto")
    conteudo.append(_EXTRACAO_PROMPT)

    response = _gerar_com_retry(
        api_key=api_key,
        contexto="extrair_itens_poc",
        model=model or _TEXT_MODEL,
        contents=conteudo,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtracaoPoc,
        ),
    )
    parsed = response.parsed
    if isinstance(parsed, ExtracaoPoc):
        return parsed
    return ExtracaoPoc.model_validate_json(response.text)


class HidratacaoPlanejador(BaseModel):
    responsavel_sugerido: str = ""
    email_responsavel_sugerido: str = ""
    produtos_detectados: list[str] = []
    rede_cidr_gerenciamento: str = ""
    rede_gateway: str = ""
    rede_vip_cluster: str = ""
    rede_pool_ip_inicio: str = ""
    rede_pool_ip_fim: str = ""


class ExtracaoProjetoPlanejador(ExtracaoPoc):
    hidratacao: HidratacaoPlanejador


_HIDRATACAO_PROMPT = """\

Além da estrutura acima, extraia também dados para pré-popular o assistente de planejamento de PoC \
("SUSE PoC Planner") com o resultado em `hidratacao`:
- responsavel_sugerido: nome da pessoa responsável técnica pela PoC (ex.: Solutions Architect, engenheiro \
líder), só se estiver explícito no documento (senão string vazia — nunca invente um nome).
- email_responsavel_sugerido: e-mail dessa pessoa, só se estiver explícito (senão string vazia).
- produtos_detectados: quais dos produtos abaixo são mencionados ou claramente fazem parte do escopo do \
documento. Use só os ids exatos desta lista (nunca invente outro id):
  - virtualization: SUSE Virtualization (também chamado Harvester)
  - rancher: Rancher Prime
  - security: SUSE Security (também chamado NeuVector)
  - storage: SUSE Storage (também chamado Longhorn)
  - observability: SUSE Observability (também chamado StackState)
  - registry: SUSE Private Registry
  - appcollection: SUSE Application Collection
  - manager: SUSE Multi-Linux Manager
- rede_cidr_gerenciamento, rede_gateway, rede_vip_cluster, rede_pool_ip_inicio, rede_pool_ip_fim: valores \
de rede/IP, só se estiverem explicitamente definidos no documento (CIDR de gerência, gateway, VIP do \
cluster, início/fim do pool de IPs) — string vazia pra qualquer um que não esteja explícito. Nunca \
infira ou estime um IP que não esteja escrito no documento.

Nunca inclua nem infira nenhuma credencial, senha, token ou chave de API — isso não faz parte do que é \
pedido aqui.
"""


def extrair_projeto_planejador(
    pdf_bytes: bytes | None = None,
    texto: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> ExtracaoProjetoPlanejador:
    if pdf_bytes:
        conteudo: list = [types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")]
    elif texto:
        conteudo = [texto]
    else:
        raise ValueError("Informe pdf_bytes ou texto")
    conteudo.append(_EXTRACAO_PROMPT + _HIDRATACAO_PROMPT)

    response = _gerar_com_retry(
        api_key=api_key,
        contexto="extrair_projeto_planejador",
        model=model or _TEXT_MODEL,
        contents=conteudo,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtracaoProjetoPlanejador,
        ),
    )
    parsed = response.parsed
    if isinstance(parsed, ExtracaoProjetoPlanejador):
        return parsed
    return ExtracaoProjetoPlanejador.model_validate_json(response.text)


class ItemRfiExtraido(BaseModel):
    codigo: str
    categoria: str
    categoria_codigo: str = ""
    descricao: str


class ExtracaoRfi(BaseModel):
    titulo_sugerido: str
    orgao_sugerido: str
    numero_processo_sugerido: str
    itens: list[ItemRfiExtraido]


_EXTRACAO_RFI_PROMPT = """\
Você é um Solutions Architect da SUSE fazendo uma triagem inicial de um TR (Termo de Referência) ou \
edital de licitação, pra identificar quais requisitos técnicos dizem respeito ao portfólio da SUSE.

O documento pode ter qualquer estrutura (numeração de 2, 3, 4 ou mais níveis, com ou sem seções \
nomeadas, em um ou mais lotes/itens de licitação) — varra o documento inteiro, não assuma um formato \
fixo.

O portfólio SUSE relevante cobre estas áreas, cada uma com seu código (um requisito só entra na \
triagem se tratar de uma delas):
{categorias}

Ignore explicitamente: cláusulas administrativas/jurídicas, critérios de habilitação da empresa, \
prazos, penalidades, garantias contratuais, modelo de pagamento, tabelas de inventário de hardware \
(specs de servidor/storage físico que não são sobre a camada de software), e cadernos de teste/ \
validação (são passos de aceite, não requisitos de capacidade).

Para cada requisito-folha (o nível mais específico, não os títulos de agrupamento) dentro dessas \
áreas, devolva:
- codigo: a numeração exatamente como aparece no documento original (ex.: "1.1.3.4.3"). Nunca invente \
  ou renumere — copie literalmente.
- categoria: o título da seção ou subseção mais próxima que agrupa esse requisito (ex.: "Storage \
  Definido Por Software (SDS) E Bancos De Dados").
- categoria_codigo: o código (da lista acima) da área do portfólio em que esse requisito se encaixa.
- descricao: o texto do requisito como está no documento, sem resumir nem reescrever o conteúdo \
  técnico (pode normalizar quebras de linha e espaçamento).

Também devolva:
- titulo_sugerido: nome do processo/projeto/edital, se identificável (ex.: nome do pregão ou do \
  objeto da licitação); senão string vazia.
- orgao_sugerido: nome do órgão/cliente que publicou o documento, se identificável; senão string \
  vazia.
- numero_processo_sugerido: número do processo/edital/pregão, se identificável; senão string vazia.

Responda em português, sem inventar itens que não tenham base no documento. Se nenhum requisito do \
documento se encaixar nas áreas acima, devolva uma lista de itens vazia.
""".replace("{categorias}", descricoes_formatadas())


def extrair_itens_rfi(
    pdf_bytes: bytes | None = None,
    texto: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> ExtracaoRfi:
    if pdf_bytes:
        conteudo: list = [types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")]
    elif texto:
        conteudo = [texto]
    else:
        raise ValueError("Informe pdf_bytes ou texto")
    conteudo.append(_EXTRACAO_RFI_PROMPT)

    response = _gerar_com_retry(
        api_key=api_key,
        contexto="extrair_itens_rfi",
        model=model or _TEXT_MODEL,
        contents=conteudo,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtracaoRfi,
        ),
    )
    parsed = response.parsed
    if isinstance(parsed, ExtracaoRfi):
        return parsed
    return ExtracaoRfi.model_validate_json(response.text)


class CandidatoProcedimento(BaseModel):
    titulo_procedimento: str
    heading_title: str
    content_text: str


class ConfirmacaoMatch(BaseModel):
    atende: bool
    indice_candidato: int
    justificativa: str


_CONFIRMACAO_PROMPT = """\
Você é um Solutions Architect avaliando se algum procedimento já validado resolve um item de uma PoC.

Item da PoC a ser testado:
\"\"\"
{item}
\"\"\"

Candidatos encontrados por similaridade na base de procedimentos validados (cada um é um trecho/seção \
de um procedimento):
{candidatos}

Responda:
- atende: true se algum dos candidatos realmente cobre o que o item pede (não basta ser parecido no \
assunto, o passo a passo tem que resolver o item).
- indice_candidato: o número do candidato escolhido (começando em 0), ou -1 se nenhum atende.
- justificativa: 1-2 frases curtas, em português, explicando a decisão.
"""


def confirmar_match(
    item_texto: str,
    candidatos: list[CandidatoProcedimento],
    api_key: str | None = None,
    model: str | None = None,
) -> ConfirmacaoMatch:
    candidatos_texto = "\n\n".join(
        f"[{i}] Procedimento \"{c.titulo_procedimento}\" — seção \"{c.heading_title}\":\n{c.content_text}"
        for i, c in enumerate(candidatos)
    )
    response = _gerar_com_retry(
        api_key=api_key,
        contexto="confirmar_match",
        model=model or _TEXT_MODEL,
        contents=_CONFIRMACAO_PROMPT.format(item=item_texto, candidatos=candidatos_texto),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ConfirmacaoMatch,
        ),
    )
    parsed = response.parsed
    if isinstance(parsed, ConfirmacaoMatch):
        return parsed
    return ConfirmacaoMatch.model_validate_json(response.text)


class FonteEvidencia(BaseModel):
    titulo: str
    url: str


_VIABILIDADE_PROMPT = """\
Pesquise na web se o item de PoC abaixo é viável/suportado ou se há evidência explícita de que NÃO é \
suportado. Responda em português, de forma objetiva, citando o que a pesquisa encontrou.

Item da PoC:
\"\"\"
{item}
\"\"\"
"""


def pesquisar_viabilidade_web(
    item_texto: str, api_key: str | None = None, model: str | None = None
) -> tuple[str, list[FonteEvidencia]]:
    response = _gerar_com_retry(
        api_key=api_key,
        contexto="pesquisar_viabilidade_web",
        model=model or _TEXT_MODEL,
        contents=_VIABILIDADE_PROMPT.format(item=item_texto),
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
    )
    texto = response.text or ""

    fontes: list[FonteEvidencia] = []
    candidate = response.candidates[0] if response.candidates else None
    grounding = getattr(candidate, "grounding_metadata", None) if candidate else None
    for chunk in getattr(grounding, "grounding_chunks", None) or []:
        web = getattr(chunk, "web", None)
        if web is not None and web.uri:
            fontes.append(FonteEvidencia(titulo=web.title or web.uri, url=web.uri))

    return texto, fontes


class AvaliacaoViabilidade(BaseModel):
    nao_suportado: bool
    evidencia_viavel: bool
    justificativa: str


_AVALIACAO_PROMPT = """\
Com base no resultado de pesquisa abaixo sobre a viabilidade de um item de PoC, classifique:

Resultado da pesquisa:
\"\"\"
{pesquisa}
\"\"\"

Responda:
- nao_suportado: true SÓ se o resultado trouxer evidência explícita de que não é suportado/não é viável.
- evidencia_viavel: true se o resultado trouxer evidência de que é viável (ainda que não seja prova \
definitiva).
- justificativa: 1-2 frases curtas, em português, resumindo a evidência (ou a falta dela).
"""


def classificar_viabilidade(
    texto_pesquisa: str, api_key: str | None = None, model: str | None = None
) -> AvaliacaoViabilidade:
    response = _gerar_com_retry(
        api_key=api_key,
        contexto="classificar_viabilidade",
        model=model or _TEXT_MODEL,
        contents=_AVALIACAO_PROMPT.format(pesquisa=texto_pesquisa or "(a pesquisa não retornou texto)"),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AvaliacaoViabilidade,
        ),
    )
    parsed = response.parsed
    if isinstance(parsed, AvaliacaoViabilidade):
        return parsed
    return AvaliacaoViabilidade.model_validate_json(response.text)


_ATENDIMENTO_RFI_PROMPT = """\
Pesquise na web (documentação oficial da SUSE, Rancher, release notes, comparativos técnicos e outras \
fontes confiáveis) se alguma solução do portfólio SUSE (SUSE Linux Enterprise Server, Rancher Prime, \
SUSE Virtualization/Harvester, SUSE Storage/Longhorn, SUSE Security/NeuVector, SUSE Observability, \
SUSE Multi-Linux Manager, SUSE Private Registry, SUSE Application Collection) atende o requisito \
técnico de edital abaixo. Responda em português, de forma objetiva, citando o que a pesquisa \
encontrou sobre cada produto SUSE relevante para este requisito específico.

Requisito do edital:
\"\"\"
{item}
\"\"\"
"""


def pesquisar_atendimento_rfi(
    item_texto: str, api_key: str | None = None, model: str | None = None
) -> tuple[str, list[FonteEvidencia]]:
    response = _gerar_com_retry(
        api_key=api_key,
        contexto="pesquisar_atendimento_rfi",
        model=model or _TEXT_MODEL,
        contents=_ATENDIMENTO_RFI_PROMPT.format(item=item_texto),
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
    )
    texto = response.text or ""

    fontes: list[FonteEvidencia] = []
    candidate = response.candidates[0] if response.candidates else None
    grounding = getattr(candidate, "grounding_metadata", None) if candidate else None
    for chunk in getattr(grounding, "grounding_chunks", None) or []:
        web = getattr(chunk, "web", None)
        if web is not None and web.uri:
            fontes.append(FonteEvidencia(titulo=web.title or web.uri, url=web.uri))

    return texto, fontes


class AvaliacaoAtendimentoRfi(BaseModel):
    nao_atende: bool
    atende_totalmente: bool
    atende_parcialmente: bool
    justificativa: str


_AVALIACAO_ATENDIMENTO_RFI_PROMPT = """\
Com base no resultado de pesquisa abaixo sobre o atendimento de um requisito de edital pelo portfólio \
SUSE, classifique:

Resultado da pesquisa:
\"\"\"
{pesquisa}
\"\"\"

Responda:
- nao_atende: true SÓ se o resultado trouxer evidência explícita de que nenhuma solução SUSE atende \
este requisito (ex.: funcionalidade claramente ausente ou incompatível).
- atende_totalmente: true se o resultado trouxer evidência de que alguma solução SUSE atende o \
requisito integralmente, sem ressalvas relevantes. Nunca marque isso junto com nao_atende.
- atende_parcialmente: true se o resultado trouxer evidência de atendimento incompleto, com \
ressalvas, ou que depende de configuração/produto adicional não óbvio. Nunca marque isso junto com \
atende_totalmente.
- justificativa: 1-2 frases curtas, em português, resumindo a evidência encontrada (ou a falta dela \
e, nesse caso, deixe nao_atende, atende_totalmente e atende_parcialmente todos como false).
"""


def classificar_atendimento_rfi(
    texto_pesquisa: str, api_key: str | None = None, model: str | None = None
) -> AvaliacaoAtendimentoRfi:
    response = _gerar_com_retry(
        api_key=api_key,
        contexto="classificar_atendimento_rfi",
        model=model or _TEXT_MODEL,
        contents=_AVALIACAO_ATENDIMENTO_RFI_PROMPT.format(
            pesquisa=texto_pesquisa or "(a pesquisa não retornou texto)"
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AvaliacaoAtendimentoRfi,
        ),
    )
    parsed = response.parsed
    if isinstance(parsed, AvaliacaoAtendimentoRfi):
        return parsed
    return AvaliacaoAtendimentoRfi.model_validate_json(response.text)


class ResumoSessaoExtraido(BaseModel):
    data: str
    participantes: list[str]
    pontos_resolvidos: list[str]
    pontos_falha: list[str]
    proximos_passos: list[str]


_RESUMO_SESSAO_PROMPT = """\
Você é um Solutions Architect organizando o registro de uma sessão de PoC a partir de um resumo em texto \
livre (gerado por outra ferramenta de IA durante a sessão com o cliente).

Texto da sessão:
\"\"\"
{texto}
\"\"\"

Extraia:
- data: a data da sessão no formato AAAA-MM-DD, se estiver identificável no texto (senão string vazia).
- participantes: nomes de pessoas mencionadas como presentes (senão lista vazia).
- pontos_resolvidos: lista curta dos pontos que foram resolvidos/concluídos na sessão.
- pontos_falha: lista curta dos pontos que falharam, ficaram bloqueados ou têm alguma pendência.
- proximos_passos: lista curta das próximas ações combinadas.

Responda em português, com frases curtas e objetivas em cada item das listas. Não invente informação que \
não esteja no texto; se uma lista não se aplicar, devolva lista vazia.
"""


def extrair_resumo_sessao(
    texto: str, api_key: str | None = None, model: str | None = None
) -> ResumoSessaoExtraido:
    response = _gerar_com_retry(
        api_key=api_key,
        contexto="extrair_resumo_sessao",
        model=model or _TEXT_MODEL,
        contents=_RESUMO_SESSAO_PROMPT.format(texto=texto),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ResumoSessaoExtraido,
        ),
    )
    parsed = response.parsed
    if isinstance(parsed, ResumoSessaoExtraido):
        return parsed
    return ResumoSessaoExtraido.model_validate_json(response.text)


_RESUMO_EMAIL_PROMPT = """\
Você é um Solutions Architect escrevendo um resumo formal para enviar por e-mail ao cliente sobre o \
andamento de uma PoC, com base no que aconteceu numa sessão específica.

Contexto da sessão:
\"\"\"
{contexto}
\"\"\"

Escreva um texto em português, tom formal e neutro, pronto para colar num e-mail, estruturado em:
- Um parágrafo breve de abertura mencionando a data da sessão.
- "Hoje realizamos": o que foi feito, testado ou resolvido.
- "Pendências": o que ficou com falha, bloqueado ou pendente (omita esta seção se não houver nada).
- "Próximos passos": as próximas ações combinadas (omita esta seção se não houver nada).

Não invente informação que não esteja no contexto. Não assine o e-mail nem use placeholders como \
"[Seu nome]".
"""


def gerar_resumo_email(contexto: str, api_key: str | None = None, model: str | None = None) -> str:
    response = _gerar_com_retry(
        api_key=api_key,
        contexto="gerar_resumo_email",
        model=model or _TEXT_MODEL,
        contents=_RESUMO_EMAIL_PROMPT.format(contexto=contexto),
    )
    return response.text or ""


_RESUMO_EXECUTIVO_PROMPT = """\
Você é um Solutions Architect preparando o sumário executivo de uma apresentação de resultados de PoC \
para o cliente, a partir do status consolidado abaixo.

Status consolidado:
\"\"\"
{contexto}
\"\"\"

Escreva um texto em português, tom formal e direto, adequado para abrir uma apresentação ao cliente \
(3 a 5 parágrafos curtos), cobrindo:
- Visão geral do que foi avaliado nesta PoC e o percentual concluído.
- Principais conquistas e pontos validados com sucesso.
- Pendências ou riscos relevantes, com linguagem profissional e sem expor mensagens de erro ou \
detalhes técnicos de depuração internos.
- Próximos passos recomendados.

Não invente informação que não esteja no status consolidado. Não assine o texto nem use placeholders \
como "[Seu nome]".
"""


def gerar_resumo_executivo(contexto: str, api_key: str | None = None, model: str | None = None) -> str:
    response = _gerar_com_retry(
        api_key=api_key,
        contexto="gerar_resumo_executivo",
        model=model or _TEXT_MODEL,
        contents=_RESUMO_EXECUTIVO_PROMPT.format(contexto=contexto),
    )
    return response.text or ""
