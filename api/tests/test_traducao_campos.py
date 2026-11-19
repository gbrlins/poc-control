"""Textos do item de PoC e categoria do RFI traduzidos sob demanda (sem banco: objetos e sessão são falsos), e o idioma dos textos de uso único."""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

for chave, valor in {
    "POSTGRES_USER": "x", "POSTGRES_PASSWORD": "x", "POSTGRES_DB": "x", "SESSION_SECRET": "teste",
    "GEMINI_API_KEY": "x", "ADMIN_EMAIL": "a@example.com", "ADMIN_PASSWORD_HASH": "x",
}.items():
    os.environ.setdefault(chave, valor)

from app import gemini, traducao_cache  # noqa: E402
from app.models import OrigemClassificacao  # noqa: E402
from app.pocs import traducao as pocs_traducao  # noqa: E402
from app.rfi import traducao as rfi_traducao  # noqa: E402


def _falso(monkeypatch):
    chamadas = []

    def fake(textos, idioma, api_key=None, model=None):
        chamadas.append((list(textos), idioma))
        return [f"[{idioma}] {t}" for t in textos]

    monkeypatch.setattr(traducao_cache, "traduzir_textos", fake)
    return chamadas


def _item(**kw):
    base = dict(id=1, titulo="Criar cluster", descricao="Subir o cluster", criterio_aceite="Nós prontos", categoria="Kubernetes", traducoes=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_item_traduz_os_quatro_campos_numa_chamada_so(monkeypatch):
    chamadas = _falso(monkeypatch)
    db, item = MagicMock(), _item()
    out = pocs_traducao.itens_no_idioma(db, [item], "en")
    assert out == {1: {"titulo": "[en] Criar cluster", "descricao": "[en] Subir o cluster", "criterio_aceite": "[en] Nós prontos", "categoria": "[en] Kubernetes"}}
    assert len(chamadas) == 1 and len(chamadas[0][0]) == 4
    assert set(item.traducoes) == {"en:titulo", "en:descricao", "en:criterio_aceite", "en:categoria"} and db.commit.called
    # segunda abertura sai do cache; pt nunca chama a IA
    assert pocs_traducao.itens_no_idioma(db, [item], "en") == out and len(chamadas) == 1
    assert pocs_traducao.itens_no_idioma(db, [item], "pt") == {} and len(chamadas) == 1


def test_editar_um_campo_retraduz_so_ele(monkeypatch):
    chamadas = _falso(monkeypatch)
    db, item = MagicMock(), _item()
    pocs_traducao.itens_no_idioma(db, [item], "es")
    item.titulo = "Criar cluster HA"
    out = pocs_traducao.itens_no_idioma(db, [item], "es")
    assert out[1]["titulo"] == "[es] Criar cluster HA" and out[1]["descricao"] == "[es] Subir o cluster"
    assert chamadas[-1] == (["Criar cluster HA"], "es")


def test_campos_vazios_nao_sao_enviados(monkeypatch):
    chamadas = _falso(monkeypatch)
    item = _item(descricao=None, criterio_aceite="", categoria=None)
    assert pocs_traducao.itens_no_idioma(MagicMock(), [item], "en") == {1: {"titulo": "[en] Criar cluster"}}
    assert chamadas == [(["Criar cluster"], "en")]


def test_rfi_traduz_justificativa_e_categoria_mas_nunca_a_descricao(monkeypatch):
    chamadas = _falso(monkeypatch)
    item = SimpleNamespace(
        id=7, justificativa="O produto atende.", categoria="Segurança", descricao="Texto literal do edital", origem=OrigemClassificacao.auto, traducoes=None
    )
    out = rfi_traducao.textos_rfi_no_idioma(MagicMock(), [item], "en")
    assert out == {7: {"justificativa": "[en] O produto atende.", "categoria": "[en] Segurança"}}
    assert all("Texto literal do edital" not in lote for lote, _ in chamadas for lote in lote)
    # formato antigo preservado: a justificativa continua sob a chave só do idioma
    assert "en" in item.traducoes and "en:categoria" in item.traducoes


def test_rfi_justificativa_digitada_por_uma_pessoa_tambem_e_traduzida_para_quem_le_em_outro_idioma(monkeypatch):
    _falso(monkeypatch)
    item = SimpleNamespace(
        id=8, justificativa="Escrito por uma pessoa", categoria="Rede", descricao="x", origem=OrigemClassificacao.manual, traducoes=None
    )
    out = rfi_traducao.textos_rfi_no_idioma(MagicMock(), [item], "en")
    assert out == {8: {"justificativa": "[en] Escrito por uma pessoa", "categoria": "[en] Rede"}}


def test_idioma_dos_textos_de_uso_unico(monkeypatch):
    prompts = []

    def fake(**kw):
        prompts.append(kw["contents"] if isinstance(kw["contents"], str) else kw["contents"][0])
        return SimpleNamespace(text="ok")

    monkeypatch.setattr(gemini, "_gerar_com_retry", fake)
    gemini.gerar_resumo_email("ctx", lang="en")
    gemini.gerar_resumo_executivo("ctx", lang="es")
    gemini.gerar_resumo_email("ctx")
    # Sem idioma informado o padrão é o inglês (app/idioma.py); português só quando pedido.
    assert "em inglês" in prompts[0] and "em espanhol" in prompts[1] and "em inglês" in prompts[2]
    assert gemini._nome_idioma("xx") == gemini._nome_idioma(None) == "inglês" and gemini._nome_idioma("pt") == "português (pt-BR)"
