"""itens_do_planejador: a lista plana `tests` do planejador vira itens de execução, sem Gemini e sem banco."""
import json
import os

for chave, valor in {
    "POSTGRES_USER": "x", "POSTGRES_PASSWORD": "x", "POSTGRES_DB": "x", "SESSION_SECRET": "teste",
    "GEMINI_API_KEY": "x", "ADMIN_EMAIL": "a@example.com", "ADMIN_PASSWORD_HASH": "x",
}.items():
    os.environ.setdefault(chave, valor)

from app.pocs.planner_import import itens_do_planejador  # noqa: E402


def _t(**kw):
    base = {"id": "a1", "catalogId": "virt-vm-create", "product": "virtualization", "productName": "SUSE Virtualization",
            "title": "Criar uma VM", "expected": "VM em Running", "priority": "must", "fit": "native", "led": "suse",
            "result": "pending", "owner": "Ana"}
    base.update(kw)
    return base


def _doc(tests, **projeto):
    return json.dumps({"schema": 2, "planner": {"project": {"projectName": "PoC Acme", "clientOrganization": "Acme", **projeto}}, "tests": tests})


def test_cria_itens_com_fases_por_produto_e_mapeia_os_valores():
    r = itens_do_planejador(_doc([
        _t(), _t(id="a2", catalogId="virt-livemig", title="Live migration", result="pass", led="client", fit="config"),
        _t(id="b1", catalogId="rancher-x", product="rancher", productName="Rancher Prime", title="Instalar", result="running", led="partner"),
    ]))
    assert r["titulo"] == "PoC Acme" and r["cliente"] == "Acme"
    assert [f["titulo"] for f in r["fases"]] == ["SUSE Virtualization", "Rancher Prime"]
    assert [i["codigo"] for i in r["itens"]] == ["1.1", "1.2", "2.1"]
    a, b, c = r["itens"]
    assert (a["catalogo_id"], a["planner_id"], a["status"], a["conducao"], a["prioridade"]) == ("virt-vm-create", "a1", "pendente", "suse", "must")
    assert (b["resultado"], b["status"], b["conducao"], b["aderencia"], b["aderencia_origem"]) == ("pass", "concluido", "cliente", "config", "manual")
    assert (c["status"], c["conducao"], c["fase"]) == ("em_andamento", "parceiro", 2)


def test_teste_personalizado_nao_tem_catalogo_id():
    r = itens_do_planejador(_doc([_t(catalogId="", id="c1", title="Teste do cliente", fit="")]))
    i = r["itens"][0]
    assert i["catalogo_id"] is None and i["aderencia"] is None and i["aderencia_origem"] is None


def test_outros_formatos_seguem_o_fluxo_antigo():
    assert itens_do_planejador("texto livre") is None
    assert itens_do_planejador(json.dumps({"planner": {"project": {}}, "testCases": {}})) is None  # sem `tests`
    assert itens_do_planejador(json.dumps({"tests": []})) is None
    assert itens_do_planejador(json.dumps([1, 2])) is None
    assert itens_do_planejador(_doc([{"title": ""}, "x", None])) is None


def test_valores_hostis_viram_padrao_ou_sao_cortados():
    r = itens_do_planejador(_doc([_t(result="hack", fit="x", led="y", priority="z", title="  Título   com   espaços  " + "x" * 800, owner="o" * 500)]))
    i = r["itens"][0]
    assert i["resultado"] == "pending" and i["status"] == "pendente"
    assert i["aderencia"] is None and i["conducao"] is None and i["prioridade"] is None
    assert i["titulo"].startswith("Título com espaços") and len(i["titulo"]) <= 500 and len(i["responsavel"]) <= 255


def test_sem_nome_de_projeto_usa_titulo_padrao_e_limita_a_quantidade():
    r = itens_do_planejador(json.dumps({"planner": {}, "tests": [_t(id=str(n)) for n in range(1500)]}))
    assert r["titulo"] == "Untitled PoC" and r["cliente"] == "" and len(r["itens"]) == 1000


def test_origem_da_aderencia_acompanha_o_fitsource():
    r = itens_do_planejador(_doc([
        _t(id="a", fit="config", fitSource="web"), _t(id="b", fit="native", fitSource="history"),
        _t(id="c", fit="gap"), _t(id="d", fit="gap", fitSource="inventada"), _t(id="e", fit="", fitSource="web"),
    ]))
    origens = {i["planner_id"]: i["aderencia_origem"] for i in r["itens"]}
    assert origens == {"a": "web", "b": "historico", "c": "manual", "d": "manual", "e": None}
