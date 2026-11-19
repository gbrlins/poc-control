"""Relatórios exportados nos 3 idiomas (sem banco): os rótulos fixos seguem o ?lang=, o resto (dados da PoC/IA) não é tocado."""
import os
from datetime import date
from types import SimpleNamespace

for chave, valor in {
    "POSTGRES_USER": "x", "POSTGRES_PASSWORD": "x", "POSTGRES_DB": "x", "SESSION_SECRET": "teste",
    "GEMINI_API_KEY": "x", "ADMIN_EMAIL": "a@example.com", "ADMIN_PASSWORD_HASH": "x",
}.items():
    os.environ.setdefault(chave, valor)

import pytest  # noqa: E402

from app.models import StatusItem  # noqa: E402
from app.pocs.apresentacao import montar_apresentacao_html  # noqa: E402
from app.pocs.export import montar_export_html  # noqa: E402
from app.pocs.roteiro import montar_roteiro_html  # noqa: E402
from app.relatorio_i18n import LANGS, _TEXTOS, fmt_data, html_lang, norm_lang, t  # noqa: E402


def _poc():
    item = SimpleNamespace(codigo="1.1", titulo="Instalar o Rancher", descricao="d", criterio_aceite="ok", fase=1, ordem=1,
                           status=StatusItem.concluido, classificacao=None)
    return SimpleNamespace(titulo="PoC Teste", cliente="ACME", itens=[item], fases=[], prerequisitos=[], sessoes=[],
                           parametros_tecnicos=None, resumo_executivo="")


def test_todo_texto_tem_os_tres_idiomas_preenchidos():
    for chave, tupla in _TEXTOS.items():
        assert len(tupla) == len(LANGS), chave
        assert all(isinstance(x, str) and x for x in tupla), chave


def test_idioma_desconhecido_cai_em_ingles_e_datas_seguem_o_idioma():
    # Padrão de quem olha sem ter escolhido nada: inglês (app/idioma.py); pt só quando pedido.
    assert norm_lang("xx") == "en" and norm_lang(None) == "en" and norm_lang("EN-us") == "en" and norm_lang("pt_BR") == "pt"
    assert t("zz", "export.plano") == t("en", "export.plano") != t("pt", "export.plano")
    d = date(2026, 11, 5)
    assert fmt_data("pt", d) == "05/11/2026" and fmt_data("es", d) == "05/11/2026" and fmt_data("en", d) == "2026-11-05"
    assert html_lang("pt") == "pt-BR" and html_lang("en") == "en"


@pytest.mark.parametrize("lang,esperado,ausente", [
    ("pt", "Plano de testes", "Test plan"),
    ("en", "Test plan", "Plano de testes"),
    ("es", "Plan de pruebas", "Test plan"),
])
def test_relatorio_de_status_segue_o_idioma(lang, esperado, ausente):
    html = montar_export_html(_poc(), lang)
    assert esperado in html and ausente not in html
    assert "PoC Teste" in html and "Instalar o Rancher" in html   # dados da PoC não são traduzidos


def test_apresentacao_e_roteiro_em_ingles():
    apres = montar_apresentacao_html(_poc(), "en")
    assert "Executive summary" in apres and "Sumário executivo" not in apres and 'lang="en"' in apres
    rot = montar_roteiro_html(_poc(), _poc().itens, "en")
    assert "Day script" in rot and "Roteiro do dia" not in rot and "Item not classified yet." in rot


def test_padrao_e_ingles_e_pt_so_quando_pedido():
    assert "Executive summary" in montar_apresentacao_html(_poc())
    assert "Sumário executivo" in montar_apresentacao_html(_poc(), "pt")
