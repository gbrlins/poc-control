"""A biblioteca exportada pelo planejador ("Export library") também pode ser importada na tela de Procedimentos (sem banco)."""
import os
import uuid

for chave, valor in {
    "POSTGRES_USER": "x", "POSTGRES_PASSWORD": "x", "POSTGRES_DB": "x", "SESSION_SECRET": "teste",
    "GEMINI_API_KEY": "x", "ADMIN_EMAIL": "a@example.com", "ADMIN_PASSWORD_HASH": "x",
}.items():
    os.environ.setdefault(chave, valor)

from app.procedimentos.router import KIND_BIBLIOTECA_PLANEJADOR, _do_formato_do_planejador, _itens_brutos  # noqa: E402

PLANEJADOR = {
    "id": "loc-abc123", "family": "loc-abc123", "title": "Instalar Rancher", "titleEn": "Install Rancher", "products": ["rancher", "security"],
    "tags": ["k3s"], "sourceClient": "ACME", "date": "2026-11-01", "status": "validado", "version": 3,
    "html": "<h2>Objetivo</h2><p>x</p>", "langOriginal": "pt",
}


def test_converte_um_procedimento_do_planejador_para_o_formato_daqui():
    r = _do_formato_do_planejador(PLANEJADOR)
    assert r["titulo"] == "Instalar Rancher" and r["titulo_en"] == "Install Rancher" and r["html_original"] == "<h2>Objetivo</h2><p>x</p>"
    assert r["categorias"] == ["K8S", "SEC"] and r["cliente_origem"] == "ACME" and r["data_origem"] == "2026-11-01"
    assert r["status"] == "validado" and r["versao"] == 3 and r["idioma_original"] == "pt" and r["tags"] == ["k3s"]
    assert r["id"] is None                                     # id local do planejador não existe no servidor


def test_procedimento_do_servidor_guardado_na_biblioteca_mantem_o_id_para_achar_o_duplicado():
    uid = uuid.uuid4()
    assert _do_formato_do_planejador({**PLANEJADOR, "id": f"srv-{uid}"})["id"] == str(uid)
    assert _do_formato_do_planejador({**PLANEJADOR, "id": "srv-nao-e-uuid"})["id"] is None


def test_formato_daqui_passa_direto_sem_mudar():
    daqui = {"titulo": "X", "html_original": "<h2>a</h2>", "categorias": ["K8S"]}
    assert _do_formato_do_planejador(daqui) is daqui
    assert _do_formato_do_planejador("lixo") == "lixo"


def test_itens_brutos_desembrulha_a_biblioteca_e_aceita_lista_ou_objeto():
    biblioteca = {"kind": KIND_BIBLIOTECA_PLANEJADOR, "schema": 1, "procedures": [PLANEJADOR, PLANEJADOR]}
    assert len(_itens_brutos(biblioteca)) == 2 and _itens_brutos(biblioteca)[0]["titulo"] == "Instalar Rancher"
    assert len(_itens_brutos([PLANEJADOR])) == 1 and len(_itens_brutos(PLANEJADOR)) == 1
    assert _itens_brutos({"titulo": "X", "html_original": "<h2>a</h2>"})[0]["titulo"] == "X"


def test_biblioteca_dentro_de_uma_lista_tambem_e_desembrulhada():
    biblioteca = {"kind": KIND_BIBLIOTECA_PLANEJADOR, "schema": 1, "procedures": [PLANEJADOR]}
    r = _itens_brutos([biblioteca, {"titulo": "Outro", "html_original": "<h2>a</h2>"}])
    assert [i["titulo"] for i in r] == ["Instalar Rancher", "Outro"]
