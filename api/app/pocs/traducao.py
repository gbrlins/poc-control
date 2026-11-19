"""Textos da PoC no idioma da tela, pelo mecanismo genérico de app/traducao_cache.py: as justificativas da classificação (semáforo) e os textos do item (título, descrição,
critério, categoria)."""
from sqlalchemy.orm import Session

from app.models import Classificacao, Item, Poc, Prerequisito, Sessao
from app.traducao_cache import campos_no_idioma, textos_no_idioma


def justificativas_no_idioma(
    db: Session, classificacoes: list[Classificacao], lang: str | None, api_key: str | None = None, model: str | None = None
) -> dict:
    return textos_no_idioma(db, classificacoes, "justificativa", lang, api_key, model)


def itens_no_idioma(db: Session, itens: list[Item], lang: str | None, api_key: str | None = None, model: str | None = None) -> dict:
    """{item.id: {campo: texto}} com título, descrição, critério de aceite e categoria do item no idioma da tela. Ao contrário da
    justificativa, o item não tem `origem`: um texto editado por alguém também é exibido traduzido (o hash do original invalida o cache
    quando a pessoa edita), porque o que importa aqui é a tela acompanhar o idioma escolhido."""
    todos = lambda _item: True  # noqa: E731
    return campos_no_idioma(
        db, itens, {"titulo": todos, "descricao": todos, "criterio_aceite": todos, "categoria": todos}, lang, api_key, model
    )


# Os pontos de uma sessão são listas de frases; para usar o mesmo cache de texto único (com hash e marca de idioma), cada lista vira
# um texto de várias linhas ao traduzir e é separada de volta na leitura.
LISTAS_DA_SESSAO = ("pontos_resolvidos", "pontos_falha", "proximos_passos")


class TextosDaSessao:
    """Adaptador de uma `Sessao`: as três listas aparecem como texto de várias linhas (uma frase por linha) e tudo o mais (id, traducoes,
    idiomas) passa direto para a linha de verdade, então `campos_no_idioma`/`marcar` funcionam sem saber de listas."""

    def __init__(self, sessao: Sessao):
        object.__setattr__(self, "_sessao", sessao)

    def __getattr__(self, nome: str):
        if nome in LISTAS_DA_SESSAO:
            return "\n".join(getattr(self._sessao, nome) or [])
        return getattr(self._sessao, nome)

    def __setattr__(self, nome: str, valor) -> None:
        setattr(self._sessao, nome, valor)


def textos_da_poc_no_idioma(db: Session, poc: Poc, lang: str | None, api_key: str | None = None, model: str | None = None) -> dict:
    """Para os relatórios: {"resumo_executivo": ..., "prerequisitos": {id: {campo: texto}}, "sessoes": {id: {lista: [frases]}}} só com o que
    precisou ser traduzido. Nunca altera o texto das linhas (só o cache em `traducoes`)."""
    todos = lambda _o: True  # noqa: E731
    resumo = campos_no_idioma(db, [poc], {"resumo_executivo": todos}, lang, api_key, model).get(poc.id, {})
    prereqs = campos_no_idioma(db, list(poc.prerequisitos), {"titulo": todos, "descricao": todos}, lang, api_key, model)
    sessoes: dict = {}
    adaptadas = [TextosDaSessao(s) for s in poc.sessoes]
    traduzidas = campos_no_idioma(db, adaptadas, {c: todos for c in LISTAS_DA_SESSAO}, lang, api_key, model)
    for sessao in poc.sessoes:
        for lista, texto in (traduzidas.get(sessao.id) or {}).items():
            original = getattr(sessao, lista) or []
            frases = texto.split("\n")
            # Se o Gemini juntou ou separou frases, a contagem muda: melhor mostrar o original do que misturar.
            if len(frases) == len(original):
                sessoes.setdefault(sessao.id, {})[lista] = frases
    return {"resumo_executivo": resumo.get("resumo_executivo"), "prerequisitos": prereqs, "sessoes": sessoes}
