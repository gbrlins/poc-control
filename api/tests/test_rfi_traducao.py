"""Justificativas de RFI traduzidas sob demanda, com cache por item (sem banco: itens e sessão são falsos)."""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

for chave, valor in {
    "POSTGRES_USER": "x", "POSTGRES_PASSWORD": "x", "POSTGRES_DB": "x", "SESSION_SECRET": "teste",
    "GEMINI_API_KEY": "x", "ADMIN_EMAIL": "a@example.com", "ADMIN_PASSWORD_HASH": "x",
}.items():
    os.environ.setdefault(chave, valor)

from app.models import OrigemClassificacao  # noqa: E402
from app import traducao_cache  # noqa: E402
from app.rfi import traducao  # noqa: E402


def _item(id_, texto, origem=OrigemClassificacao.auto, cache=None):
    return SimpleNamespace(id=id_, justificativa=texto, origem=origem, traducoes=cache)


def _falso(monkeypatch):
    chamadas = []

    def fake(textos, idioma, api_key=None, model=None):
        chamadas.append((list(textos), idioma))
        return [f"[{idioma}] {t}" for t in textos]

    monkeypatch.setattr(traducao_cache, "traduzir_textos", fake)
    return chamadas


def test_pt_nao_traduz_nem_chama_a_ia(monkeypatch):
    chamadas = _falso(monkeypatch)
    assert traducao.justificativas_no_idioma(MagicMock(), [_item(1, "texto")], "pt") == {}
    assert chamadas == []


def test_traduz_texto_de_ia_e_de_pessoas_mas_nunca_as_mensagens_fixas_do_sistema_e_guarda_no_cache(monkeypatch):
    chamadas = _falso(monkeypatch)
    db = MagicMock()
    auto = _item(1, "O produto atende.")
    manual = _item(2, "Escrito por uma pessoa", origem=OrigemClassificacao.manual)
    # A mensagem fixa de erro/interrupção existe nos três idiomas e o front a traduz; nunca vai para o Gemini, em nenhum deles.
    erro_pt = _item(3, 'Não foi possível avaliar este item: x Use "Reavaliar" depois de resolver o problema.')
    erro_en = _item(4, 'Could not evaluate this item: x Use "Re-evaluate" after fixing the problem.')
    erro_es = _item(5, 'No fue posible evaluar este ítem: x Use "Reevaluar" después de resolver el problema.')
    parada = _item(6, 'Evaluation stopped before reaching this item — use "Re-evaluate" (on the item or the RFI) to evaluate it.')
    out = traducao.justificativas_no_idioma(db, [auto, manual, erro_pt, erro_en, erro_es, parada], "es")
    assert out == {1: "[es] O produto atende.", 2: "[es] Escrito por uma pessoa"}
    assert chamadas == [(["O produto atende.", "Escrito por uma pessoa"], "es")]
    db2 = MagicMock()
    auto = _item(1, "O produto atende.")
    chamadas.clear()
    assert traducao.justificativas_no_idioma(db2, [auto], "en") == {1: "[en] O produto atende."}
    assert chamadas == [(["O produto atende."], "en")]
    # segunda abertura: sai do cache, sem nova chamada
    assert traducao.justificativas_no_idioma(db2, [auto], "en") == {1: "[en] O produto atende."}
    assert len(chamadas) == 1


def test_reavaliar_invalida_a_traducao_velha(monkeypatch):
    chamadas = _falso(monkeypatch)
    item = _item(1, "Texto novo")
    item.traducoes = {"en": {"h": "hash-do-texto-antigo", "t": "old translation"}}
    out = traducao.justificativas_no_idioma(MagicMock(), [item], "en")
    assert out == {1: "[en] Texto novo"} and len(chamadas) == 1


def test_falha_da_ia_devolve_vazio_e_a_tela_mostra_o_original(monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("sem chave")

    monkeypatch.setattr(traducao_cache, "traduzir_textos", quebra)
    assert traducao.justificativas_no_idioma(MagicMock(), [_item(1, "texto")], "es") == {}
