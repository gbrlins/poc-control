"""Texto escrito pela IA (em pt-BR) exibido no idioma da tela, traduzido SOB DEMANDA e com cache.

Serve a qualquer linha com colunas de texto e uma coluna JSONB `traducoes` (hoje: `Item` título/descrição/critério/categoria,
`Classificacao.justificativa` e `RfiItem` justificativa/categoria). A tradução fica em `obj.traducoes[chave] = {"h": <hash do original>,
"t": <tradução>}`, com chave `<idioma>` para a justificativa (formato original, já gravado) e `<idioma>:<campo>` para os demais campos:
se o texto original mudar (reavaliar, edição), o hash deixa de bater e a tradução velha é ignorada. Só traduz o que a IA escreveu (o chamador decide em `pode_traduzir`);
texto digitado por uma pessoa nunca é reescrito. Qualquer falha (sem chave, tempo esgotado, resposta torta) devolve o original: a tela
nunca quebra por causa da tradução."""
import hashlib
import logging
from typing import Callable

from sqlalchemy.orm import Session

from app.gemini import traduzir_textos
from app.idioma import SEM_TRADUCAO, idioma_do_campo, norm_idioma

logger = logging.getLogger(__name__)

_LOTE = 40


def _hash(texto: str) -> str:
    return hashlib.sha1(texto.encode()).hexdigest()[:12]


def _chave(idioma: str, campo: str) -> str:
    # A justificativa já era cacheada sob a chave "<idioma>" antes de existirem outros campos; manter evita invalidar o cache existente.
    return idioma if campo == "justificativa" else f"{idioma}:{campo}"


def campos_no_idioma(
    db: Session,
    objetos: list,
    campos: dict[str, Callable[[object], bool]],
    lang: str | None,
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
    """{objeto.id: {campo: texto no idioma pedido}} só para o que precisou ser traduzido: o campo escrito no idioma pedido fica de fora (a tela mostra o original).
    `campos` mapeia cada campo ao teste que diz se aquele objeto pode ter o campo traduzido. Tudo o que falta traduzir (de todos os objetos e
    campos) vai em lotes comuns, então abrir uma PoC inteira custa poucas chamadas."""
    if lang == SEM_TRADUCAO:
        return {}
    idioma = norm_idioma(lang)
    resultado: dict = {}
    faltando: list[tuple[object, str]] = []
    for obj in objetos:
        for campo, pode_traduzir in campos.items():
            texto = getattr(obj, campo)
            if not texto or not pode_traduzir(obj):
                continue
            if idioma_do_campo(obj, campo) == idioma:
                continue  # já está no idioma de quem olha (a marca vem de app/idioma.py; sem marca vale pt): mostra o original
            cache = (obj.traducoes or {}).get(_chave(idioma, campo))
            if cache and cache.get("h") == _hash(texto):
                resultado.setdefault(obj.id, {})[campo] = cache["t"]
            else:
                faltando.append((obj, campo))
    for ini in range(0, len(faltando), _LOTE):
        lote = faltando[ini : ini + _LOTE]
        try:
            traduzidos = traduzir_textos([getattr(o, c) for o, c in lote], idioma, api_key, model)
        except Exception:  # noqa: BLE001 -- tradução é conveniência; sem ela a tela mostra o original
            logger.warning("Falha ao traduzir textos para %s", idioma, exc_info=True)
            continue
        for (obj, campo), texto in zip(lote, traduzidos):
            novo = dict(obj.traducoes or {})
            novo[_chave(idioma, campo)] = {"h": _hash(getattr(obj, campo)), "t": texto}
            obj.traducoes = novo
            resultado.setdefault(obj.id, {})[campo] = texto
        try:
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.warning("Falha ao gravar o cache de traduções", exc_info=True)
    return resultado


def textos_no_idioma(
    db: Session,
    objetos: list,
    campo: str,
    lang: str | None,
    api_key: str | None = None,
    model: str | None = None,
    pode_traduzir: Callable[[object], bool] = lambda o: True,
) -> dict:
    """{objeto.id: texto no idioma pedido} para um único campo (atalho de `campos_no_idioma`)."""
    por_objeto = campos_no_idioma(db, objetos, {campo: pode_traduzir}, lang, api_key, model)
    return {oid: valores[campo] for oid, valores in por_objeto.items()}
