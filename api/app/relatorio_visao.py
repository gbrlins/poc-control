"""Visões SÓ DE LEITURA de PoC e RFI para os relatórios (HTML/XLSX), com todo texto escrito em outro idioma já traduzido.

Os montadores de relatório (pocs/export.py, apresentacao.py, roteiro.py, rfi/export.py) leem atributos das linhas do banco. Em vez de mudar
cada um, eles recebem uma `Visao`: um invólucro que devolve o texto traduzido nos campos que foram traduzidos e delega todo o resto à
linha de verdade. A tradução nunca é atribuída à linha (o ORM gravaria no próximo commit): ela só existe aqui, e o cache vive em `traducoes`
(app/traducao_cache.py). Se o Gemini falhar, o relatório sai com o original, como as telas."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.idioma import norm_idioma
from app.models import Item, Poc, Rfi
from app.procedimentos.html_processing import extrair_secoes
from app.procedimentos.router import _html_no_idioma
from app.pocs.traducao import itens_no_idioma, justificativas_no_idioma, textos_da_poc_no_idioma
from app.rfi.traducao import mensagem_de_sistema_no_idioma, textos_rfi_no_idioma

# Textos que o PRÓPRIO sistema grava quando não há título (PoC/RFI sem título); gravados em pt ou em inglês conforme a versão.
_TITULOS_PADRAO = (
    ("PoC sem título", "Untitled PoC", "PoC sin título"),
    ("RFI sem título", "Untitled RFI", "RFI sin título"),
)
_COLUNA = {"pt": 0, "en": 1, "es": 2}


def titulo_de_sistema_no_idioma(titulo: str | None, lang: str | None) -> str | None:
    """Troca um título padrão do sistema (em qualquer idioma) pelo do idioma pedido; qualquer outro título (digitado por uma pessoa) fica."""
    for trio in _TITULOS_PADRAO:
        if titulo in trio:
            return trio[_COLUNA[norm_idioma(lang)]]
    return titulo


class Visao:
    """Invólucro de leitura: `Visao(obj, campo=valor)` responde `valor` em `campo` e delega o resto a `obj`."""

    def __init__(self, obj, **sobrescritas):
        object.__setattr__(self, "_obj", obj)
        object.__setattr__(self, "_sobrescritas", sobrescritas)

    def __getattr__(self, nome: str):
        if nome in self._sobrescritas:
            return self._sobrescritas[nome]
        return getattr(self._obj, nome)

    def __setattr__(self, nome: str, valor) -> None:  # pragma: no cover - guarda contra gravar tradução na linha por engano
        raise AttributeError("Visao é somente leitura")


def _procedimento_para_relatorio(db: Session, proc, lang: str, api_key: str | None, com_conteudo: bool):
    """O procedimento guarda o título original e um título em inglês (`titulo_en`): em inglês usa este; nos demais idiomas, o original.
    Com `com_conteudo` (o roteiro do dia imprime os passos) o corpo também vem no idioma pedido, pela tradução em cache do próprio
    procedimento (Procedimento.traducoes) re-dividida em seções; se a tradução falhar, saem as seções originais."""
    if proc is None:
        return None
    sobrescritas: dict = {}
    if lang == "en" and getattr(proc, "titulo_en", None):
        sobrescritas["titulo"] = proc.titulo_en
    if com_conteudo and (proc.idioma_original or "pt") != lang:
        html, idioma_mostrado = _html_no_idioma(db, proc, lang, api_key=api_key)
        if idioma_mostrado == lang:
            sobrescritas["chunks"] = extrair_secoes(html)
            if lang == "en" and proc.titulo_en:
                sobrescritas["titulo"] = proc.titulo_en
    return Visao(proc, **sobrescritas) if sobrescritas else proc


def itens_para_relatorio(
    db: Session, itens: list[Item], lang: str | None, api_key: str | None, model: str | None, com_conteudo: bool = False
) -> list[Visao]:
    idioma = norm_idioma(lang)
    classificacoes = [i.classificacao for i in itens if i.classificacao is not None]
    justificativas = justificativas_no_idioma(db, classificacoes, idioma, api_key, model)
    textos = itens_no_idioma(db, itens, idioma, api_key, model)
    out = []
    for item in itens:
        classificacao = item.classificacao
        visao_classificacao = None
        if classificacao is not None:
            visao_classificacao = Visao(
                classificacao,
                justificativa=justificativas.get(classificacao.id, classificacao.justificativa),
                procedimento=_procedimento_para_relatorio(db, classificacao.procedimento, idioma, api_key, com_conteudo),
            )
        out.append(Visao(item, **textos.get(item.id, {}), classificacao=visao_classificacao))
    return out


def poc_para_relatorio(db: Session, poc: Poc, lang: str | None, api_key: str | None, model: str | None) -> Visao:
    idioma = norm_idioma(lang)
    extras = textos_da_poc_no_idioma(db, poc, idioma, api_key, model)
    prereqs = [Visao(p, **extras["prerequisitos"].get(p.id, {})) for p in poc.prerequisitos]
    sessoes = [Visao(s, **extras["sessoes"].get(s.id, {})) for s in poc.sessoes]
    return Visao(
        poc,
        titulo=titulo_de_sistema_no_idioma(poc.titulo, idioma),
        resumo_executivo=extras["resumo_executivo"] or poc.resumo_executivo,
        itens=itens_para_relatorio(db, list(poc.itens), idioma, api_key, model),
        prerequisitos=prereqs,
        sessoes=sessoes,
    )


def cabecalho_para_relatorio(poc: Poc, lang: str | None) -> Visao:
    """Só o que um relatório de itens escolhidos (o roteiro do dia) imprime da PoC além dos itens: o título. Evita traduzir a PoC inteira
    (todos os itens, sessões, pré-requisitos e o resumo) quando se pediu um punhado de itens."""
    return Visao(poc, titulo=titulo_de_sistema_no_idioma(poc.titulo, lang))


def rfi_para_relatorio(db: Session, rfi: Rfi, lang: str | None, api_key: str | None, model: str | None) -> Visao:
    idioma = norm_idioma(lang)
    itens = list(rfi.itens)
    traduzidos = textos_rfi_no_idioma(db, itens, idioma, api_key, model)
    visoes = []
    for item in itens:
        extra = dict(traduzidos.get(item.id, {}))
        sistema = mensagem_de_sistema_no_idioma(item.justificativa, idioma)
        if sistema is not None:
            extra["justificativa"] = sistema
        visoes.append(Visao(item, **extra))
    return Visao(rfi, titulo=titulo_de_sistema_no_idioma(rfi.titulo, idioma), itens=visoes)
