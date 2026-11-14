import logging

from sqlalchemy.orm import Session

from app.gemini import traduzir_campos_texto

logger = logging.getLogger(__name__)

_IDIOMAS_SITE = ("pt", "en", "es")


def campos_no_idioma(
    db: Session, obj, lang: str, campos: dict[str, str], *, api_key: str | None = None
) -> dict[str, str]:
    """Generaliza api/app/procedimentos/router.py::_html_no_idioma pra um objeto qualquer com
    `idioma_original`/`traducoes` (Item, Classificacao, RfiItem -- migração 0031) e um dict
    {nome_do_campo: valor_atual}, em vez de um único HTML. Devolve {nome_do_campo: valor_no_idioma
    pedido}, cacheando a tradução em `obj.traducoes` -- mesma filosofia: nunca quebra a página por
    causa de tradução (uma falha do Gemini devolve os valores originais, sem cache).

    Linhas de antes da migração 0031 (ou extraídas/avaliadas antes deste mecanismo existir) ficam
    com idioma_original nulo -- tratado aqui como "pt", já que era a única opção até então."""
    if lang not in _IDIOMAS_SITE:
        lang = "pt"
    original = obj.idioma_original or "pt"
    if original == lang:
        return campos

    cache = (obj.traducoes or {}).get(lang)
    if cache:
        # Um campo que não existia quando a tradução foi cacheada (ex.: schema mudou depois)
        # cai pro valor original em vez de KeyError.
        return {chave: cache.get(chave, valor) for chave, valor in campos.items()}

    chaves = list(campos.keys())
    valores = [campos[chave] for chave in chaves]
    try:
        traduzidos = traduzir_campos_texto(valores, lang, api_key=api_key)
    except Exception:
        logger.warning("Falha ao traduzir campos de %s %s para %s", type(obj).__name__, obj.id, lang, exc_info=True)
        return campos

    resultado = dict(zip(chaves, traduzidos))
    traducoes = dict(obj.traducoes or {})
    traducoes[lang] = resultado
    obj.traducoes = traducoes
    if obj.idioma_original is None:
        obj.idioma_original = "pt"
    db.commit()
    return resultado
