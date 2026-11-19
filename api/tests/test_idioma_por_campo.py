"""Idioma de origem POR CAMPO: texto sem marca vale pt, cada campo é traduzido só quando difere de quem olha, edição à mão muda só a marca
do campo editado, e o relatório sai traduzido sem tocar nas linhas (sem banco: objetos e sessão são falsos)."""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

for chave, valor in {
    "POSTGRES_USER": "x", "POSTGRES_PASSWORD": "x", "POSTGRES_DB": "x", "SESSION_SECRET": "teste",
    "GEMINI_API_KEY": "x", "ADMIN_EMAIL": "a@example.com", "ADMIN_PASSWORD_HASH": "x",
}.items():
    os.environ.setdefault(chave, valor)

from app import idioma, relatorio_visao, traducao_cache  # noqa: E402
from app.pocs import export as export_poc, traducao as pocs_traducao  # noqa: E402
from app.models import FlagClassificacao, StatusItem  # noqa: E402
from app.rfi import export as export_rfi, traducao as rfi_traducao  # noqa: E402


def _falso(monkeypatch):
    chamadas = []

    def fake(textos, idioma_alvo, api_key=None, model=None):
        chamadas.append((list(textos), idioma_alvo))
        return [f"[{idioma_alvo}] {t}" for t in textos]

    monkeypatch.setattr(traducao_cache, "traduzir_textos", fake)
    return chamadas


def _item(**kw):
    base = dict(id=1, titulo="Criar cluster", descricao="Subir o cluster", criterio_aceite="Nós prontos", categoria="Kubernetes", traducoes=None, idiomas=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_padrao_de_quem_olha_e_ingles_mas_texto_sem_marca_continua_pt():
    assert idioma.norm_idioma(None) == idioma.norm_idioma("xx") == "en" and idioma.norm_idioma("pt-BR") == "pt"
    assert idioma.idioma_do_campo(_item(), "titulo") == "pt"          # linha antiga, sem marca
    assert idioma.idioma_do_campo(_item(idiomas={"titulo": "en"}), "titulo") == "en"


def test_texto_sem_marca_em_pt_nao_chama_a_ia_para_quem_le_em_pt_mas_traduz_para_en(monkeypatch):
    chamadas = _falso(monkeypatch)
    item = _item()
    assert pocs_traducao.itens_no_idioma(MagicMock(), [item], "pt") == {} and chamadas == []
    out = pocs_traducao.itens_no_idioma(MagicMock(), [item], "en")
    assert out[1]["titulo"] == "[en] Criar cluster" and len(chamadas) == 1


def test_campo_escrito_em_ingles_e_traduzido_para_quem_le_em_pt_e_so_ele(monkeypatch):
    chamadas = _falso(monkeypatch)
    item = _item(titulo="Create cluster", idiomas={"titulo": "en"})   # o resto continua pt (sem marca)
    out = pocs_traducao.itens_no_idioma(MagicMock(), [item], "pt")
    assert out == {1: {"titulo": "[pt] Create cluster"}} and chamadas == [(["Create cluster"], "pt")]


def test_editar_um_campo_muda_so_a_marca_dele():
    item = _item(idiomas={"titulo": "pt", "descricao": "pt"})
    item.titulo = "Create cluster"
    idioma.marcar_campo(item, "en", "titulo")
    assert item.idiomas == {"titulo": "en", "descricao": "pt"}
    item.descricao = ""                                                # apagar o texto tira a marca
    idioma.marcar_campo(item, "en", "descricao")
    assert item.idiomas == {"titulo": "en"}


def test_lista_da_sessao_vira_texto_de_varias_linhas_e_volta():
    sessao = SimpleNamespace(id=9, pontos_resolvidos=["a", "b"], pontos_falha=[], proximos_passos=["c"], idiomas=None, traducoes=None)
    adaptada = pocs_traducao.TextosDaSessao(sessao)
    assert adaptada.pontos_resolvidos == "a\nb" and adaptada.pontos_falha == ""
    idioma.marcar(adaptada, "es", *pocs_traducao.LISTAS_DA_SESSAO)
    assert sessao.idiomas == {"pontos_resolvidos": "es", "proximos_passos": "es"}


def test_visao_e_somente_leitura():
    v = relatorio_visao.Visao(_item(), titulo="x")
    assert v.titulo == "x" and v.descricao == "Subir o cluster"
    with pytest.raises(AttributeError):
        v.titulo = "y"


def test_titulo_padrao_do_sistema_acompanha_o_idioma_mas_titulo_digitado_nao():
    f = relatorio_visao.titulo_de_sistema_no_idioma
    assert f("PoC sem título", "en") == "Untitled PoC" and f("Untitled RFI", "pt") == "RFI sem título" and f("Meu título", "en") == "Meu título"


def test_mensagem_de_sistema_do_rfi_troca_so_o_invólucro(monkeypatch):
    f = rfi_traducao.mensagem_de_sistema_no_idioma
    assert f('Não foi possível avaliar este item: boom Use "Reavaliar" depois de resolver o problema.', "en") == 'Could not evaluate this item: boom Use "Re-evaluate" after fixing the problem.'
    assert f("O produto atende.", "en") is None and f("", "en") is None


def _poc_falso():
    classificacao = SimpleNamespace(id=5, flag=FlagClassificacao.verde, justificativa="Atende.", procedimento=None, traducoes=None, idiomas=None)
    item = SimpleNamespace(
        id=1, codigo="1.1", titulo="Criar cluster", descricao="d", criterio_aceite="c", categoria="K8s", fase=1, ordem=1,
        status=StatusItem.pendente, classificacao=classificacao, traducoes=None, idiomas=None,
    )
    return SimpleNamespace(
        id=3, titulo="PoC sem título", cliente="ACME", itens=[item], prerequisitos=[], sessoes=[], resumo_executivo=None, traducoes=None,
        idiomas=None, fases=[], parametros_tecnicos=None, escopo=None,
    ), item


def test_relatorio_em_ingles_sai_traduzido_sem_tocar_nas_linhas(monkeypatch):
    chamadas = _falso(monkeypatch)
    poc, item = _poc_falso()
    db = MagicMock()
    visao = relatorio_visao.poc_para_relatorio(db, poc, "en", None, None)
    assert visao.titulo == "Untitled PoC"
    assert visao.itens[0].titulo == "[en] Criar cluster" and visao.itens[0].classificacao.justificativa == "[en] Atende."
    # as linhas de verdade seguem com o original; só o cache (`traducoes`) foi preenchido
    assert item.titulo == "Criar cluster" and item.classificacao.justificativa == "Atende." and poc.titulo == "PoC sem título"
    assert item.traducoes and item.classificacao.traducoes
    assert chamadas  # houve tradução


def test_relatorio_pt_de_texto_pt_nao_chama_a_ia(monkeypatch):
    chamadas = _falso(monkeypatch)
    poc, _ = _poc_falso()
    visao = relatorio_visao.poc_para_relatorio(MagicMock(), poc, "pt", None, None)
    assert visao.itens[0].titulo == "Criar cluster" and chamadas == []


def test_rfi_item_sem_categoria_nao_quebra_e_descricao_nunca_e_traduzida(monkeypatch):
    chamadas = _falso(monkeypatch)
    item = SimpleNamespace(id=1, codigo="1", categoria=None, descricao="Texto literal do edital", justificativa="Atende.", veredito=None, ordem=1, fontes=[], traducoes=None, idiomas=None, origem=None)
    rfi = SimpleNamespace(id=2, titulo="RFI sem título", itens=[item])
    visao = relatorio_visao.rfi_para_relatorio(MagicMock(), rfi, "en", None, None)
    assert visao.titulo == "Untitled RFI" and visao.itens[0].descricao == "Texto literal do edital"
    assert all("Texto literal do edital" not in t for lote, _ in chamadas for t in lote)


def test_os_montadores_de_relatorio_funcionam_com_a_visao_e_mostram_o_texto_traduzido(monkeypatch):
    _falso(monkeypatch)
    from app.pocs.apresentacao import montar_apresentacao_html

    poc, _ = _poc_falso()
    visao = relatorio_visao.poc_para_relatorio(MagicMock(), poc, "en", None, None)
    html = export_poc.montar_export_html(visao, "en")
    assert "[en] Criar cluster" in html and "Untitled PoC" in html and "Test plan" in html
    assert "[en] Criar cluster" in montar_apresentacao_html(visao, "en")


def test_relatorios_do_rfi_html_e_xlsx_usam_a_visao_traduzida(monkeypatch):
    _falso(monkeypatch)
    import io

    import openpyxl

    from app.models import OrigemClassificacao, VeredictoRfi

    item = SimpleNamespace(
        id=1, codigo="1", categoria="Segurança", descricao="Texto literal do edital", justificativa="Atende.", veredito=VeredictoRfi.atende,
        ordem=1, fontes=[], traducoes=None, idiomas=None, origem=OrigemClassificacao.auto, procedimento_titulo=None,
    )
    rfi = SimpleNamespace(id=2, titulo="RFI sem título", itens=[item], orgao="", numero_processo=None)
    visao = relatorio_visao.rfi_para_relatorio(MagicMock(), rfi, "en", None, None)
    html = export_rfi.montar_rfi_export_html(visao, "en")
    assert "[en] Segurança" in html and "[en] Atende." in html and "Texto literal do edital" in html and "Untitled RFI" in html
    ws = openpyxl.load_workbook(io.BytesIO(export_rfi.montar_rfi_export_xlsx(visao, "en"))).active
    linha = [c.value for c in ws[2]]
    assert "[en] Segurança" in linha and "[en] Atende." in linha and "Texto literal do edital" in linha
    assert item.categoria == "Segurança" and item.justificativa == "Atende."   # a linha segue no original
