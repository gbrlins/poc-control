"""Idiomas do app: qual é o padrão de quem olha e qual é o idioma de texto antigo sem marca.

Duas ideias que NÃO devem se misturar:
- IDIOMA_PADRAO: o idioma em que mostramos as coisas quando ninguém escolheu (sem cabeçalho X-UI-Lang, sem ?lang=). É inglês.
- IDIOMA_LEGADO: o idioma de texto gravado ANTES de existir a marca de idioma por campo (`idiomas`), que era sempre pt-BR. Texto sem marca
  continua valendo pt: mudar isso reinterpretaria como inglês todo o conteúdo antigo.

`idiomas` (JSONB nulo) nas tabelas `itens`, `classificacoes` e `rfi_itens` guarda, POR CAMPO, o idioma em que o texto foi escrito
({"titulo": "en", ...}). Por campo e não por linha porque os campos são escritos em momentos e por mãos diferentes (a IA extrai o item
num idioma, a pessoa edita só o título em outro; a categoria do RFI nasce na extração e a justificativa na avaliação)."""
from __future__ import annotations

IDIOMAS = ("pt", "en", "es")
IDIOMA_PADRAO = "en"
IDIOMA_LEGADO = "pt"
# Pedido especial das telas: "me dê o que está gravado, sem traduzir nada" (pintura rápida antes da versão traduzida chegar).
SEM_TRADUCAO = "orig"


def norm_idioma(lang: str | None) -> str:
    """Código pt|en|es a partir de 'pt', 'en-US', 'es_AR'...; ausente ou desconhecido vira o idioma padrão (inglês)."""
    v = (lang or IDIOMA_PADRAO)[:2].lower()
    return v if v in IDIOMAS else IDIOMA_PADRAO


def idioma_do_campo(obj, campo: str) -> str:
    """Idioma em que `obj.<campo>` foi escrito; sem marca é o legado (pt)."""
    marca = (getattr(obj, "idiomas", None) or {}).get(campo)
    return marca if marca in IDIOMAS else IDIOMA_LEGADO


def marcar(obj, lang: str | None, *campos: str) -> None:
    """Registra que os campos foram escritos em `lang`. Cria um dict novo (o JSONB só detecta mudança por atribuição)."""
    idioma = norm_idioma(lang)
    novo = dict(getattr(obj, "idiomas", None) or {})
    for campo in campos:
        if getattr(obj, campo, None):
            novo[campo] = idioma
        else:
            novo.pop(campo, None)
    obj.idiomas = novo


def marcar_campo(obj, lang: str | None, campo: str) -> None:
    """Como `marcar`, para um campo só: um campo editado à mão passa a valer no idioma de quem editou, sem mexer na marca dos outros."""
    marcar(obj, lang, campo)
