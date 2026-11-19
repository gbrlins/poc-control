"""Textos de RFI no idioma da tela: usa o mecanismo genérico de app/traducao_cache.py (a marca de idioma de cada campo vem de app/idioma.py).
Não traduz as mensagens fixas de erro/interrupção do próprio sistema, que já existem nos três idiomas e o front traduz na exibição
(mensagensServidor.ts), nem a `descricao` do requisito, que é cópia literal do edital."""
from sqlalchemy.orm import Session

from app.idioma import norm_idioma
from app.models import RfiItem
from app.rfi.service import _JUSTIFICATIVA_ERRO
from app.rfi.tasks import _JUSTIFICATIVA_INTERROMPIDO
from app.traducao_cache import campos_no_idioma, textos_no_idioma

# Início de cada mensagem fixa (a de erro tem um {erro} no meio, então só vale o que vem antes dele), em qualquer idioma.
_MARCAS_SISTEMA = tuple(
    m for m in (
        *(v.split("{erro}")[0] for v in _JUSTIFICATIVA_ERRO.values()),
        *(v.split(" —")[0] for v in _JUSTIFICATIVA_INTERROMPIDO.values()),
    ) if m
)


def _traduzivel(item: RfiItem) -> bool:
    return not (item.justificativa or "").startswith(_MARCAS_SISTEMA)


def justificativas_no_idioma(
    db: Session, itens: list[RfiItem], lang: str | None, api_key: str | None = None, model: str | None = None
) -> dict:
    return textos_no_idioma(db, itens, "justificativa", lang, api_key, model, _traduzivel)


def textos_rfi_no_idioma(
    db: Session, itens: list[RfiItem], lang: str | None, api_key: str | None = None, model: str | None = None
) -> dict:
    """{item.id: {"justificativa": ..., "categoria": ...}} no idioma da tela, em lotes comuns. A `descricao` NUNCA entra: é cópia literal do
    edital, e traduzi-la desvirtuaria o requisito de origem."""
    return campos_no_idioma(db, itens, {"justificativa": _traduzivel, "categoria": lambda _i: True}, lang, api_key, model)


def mensagem_de_sistema_no_idioma(texto: str | None, lang: str | None) -> str | None:
    """Se `texto` é uma mensagem fixa de erro/interrupção do próprio sistema (em qualquer idioma em que tenha sido gravada), devolve a mesma
    mensagem no idioma pedido; senão None. Só o invólucro muda: o erro técnico dentro da mensagem de erro segue como foi gravado."""
    if not texto:
        return None
    idioma = norm_idioma(lang)
    for forma in _JUSTIFICATIVA_ERRO.values():
        antes, depois = forma.split("{erro}")
        if texto.startswith(antes) and texto.endswith(depois) and len(texto) >= len(antes) + len(depois):
            return _JUSTIFICATIVA_ERRO[idioma].format(erro=texto[len(antes) : len(texto) - len(depois)])
    if texto in _JUSTIFICATIVA_INTERROMPIDO.values():
        return _JUSTIFICATIVA_INTERROMPIDO[idioma]
    return None
