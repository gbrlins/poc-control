"""Testes do contrato com o planejador (sem Gemini e sem banco): a IA é trocada por respostas fixas, e o que
importa aqui é o que o servidor deixa passar. Rodar: `cd api && python -m pytest tests`."""
import json
import os

for chave, valor in {
    "POSTGRES_USER": "x", "POSTGRES_PASSWORD": "x", "POSTGRES_DB": "x", "SESSION_SECRET": "teste",
    "GEMINI_API_KEY": "x", "ADMIN_EMAIL": "a@example.com", "ADMIN_PASSWORD_HASH": "x",
}.items():
    os.environ.setdefault(chave, valor)

from fastapi.testclient import TestClient  # noqa: E402

from app.deps import get_current_user  # noqa: E402
from app.gemini import FonteEvidencia  # noqa: E402
from app.main import app  # noqa: E402
from app.planner import router as planner_router  # noqa: E402
from app.planner import service  # noqa: E402

CATALOGO = {"lang": "pt", "products": ["virtualization"], "tests": [
    {"id": "virt-vm-create", "product": "virtualization", "title": "Criar uma VM"},
    {"id": "virt-livemig", "product": "virtualization", "title": "Live migration"}]}


class _Usuario:
    id = "u"
    gemini_api_key_encrypted = None
    gemini_model = None


def _cliente(autenticado=True):
    app.dependency_overrides.clear()
    if autenticado:
        app.dependency_overrides[get_current_user] = lambda: _Usuario()
    return TestClient(app)


def _extraido(**kw):
    base = dict(
        projeto=service.ProjetoSugerido(nome_projeto="PoC Acme", cliente="Acme", responsavel="Ana", email_responsavel="não-é-email",
                                        data_alvo="amanhã"),
        rede=service.RedeSugerida(cidr_gerenciamento="10.0.0.0/24", gateway="10.0.0.999", vip_cluster="10.0.0.10"),
        produtos=["virtualization", "inventado"],
        testes=[service.TesteSugerido(id="virt-vm-create", motivo="cita criar VMs"), service.TesteSugerido(id="nao-existe"),
                service.TesteSugerido(id="virt-vm-create")],
    )
    base.update(kw)
    return service.ExtracaoHidratacao(**base)


def test_capabilities_sem_autenticacao():
    r = _cliente(autenticado=False).get("/api/planner/capabilities")
    assert r.status_code == 200
    assert r.json() == {
        "kind": "poc-control",
        "schema": 1,
        "features": ["hydrate", "feasibility", "procedures", "execution", "history", "draft"],
    }


def test_hydrate_e_feasibility_exigem_login():
    c = _cliente(autenticado=False)
    assert c.post("/api/planner/hydrate", data={"texto": "x", "catalogo": json.dumps(CATALOGO)}).status_code == 401
    assert c.post("/api/planner/feasibility", json={"tests": [{"id": "a", "title": "t"}]}).status_code == 401
    assert c.post("/api/planner/procedure-draft", json={"test": {"id": "a", "title": "t"}}).status_code == 401


def test_montar_hidratacao_descarta_o_que_nao_e_valido():
    out = service.montar_hidratacao(_extraido(), service.validar_catalogo(json.dumps(CATALOGO)))
    assert out["kind"] == "suse-poc-hydration" and out["schema"] == 1
    assert out["project"] == {"projectName": "PoC Acme", "clientOrganization": "Acme", "leadEngineer": "Ana"}
    assert out["network"] == {"managementCidr": "10.0.0.0/24", "clusterVip": "10.0.0.10"}
    assert out["selectedProducts"] == {"virtualization": True}
    assert out["tests"] == [{"id": "virt-vm-create", "reason": "cita criar VMs"}]
    assert "credentials" not in out and "password" not in json.dumps(out).lower()


def test_hydrate_texto_colado(monkeypatch):
    chamado = {}

    def falso(pdf, texto, cat, key, model):
        chamado.update(texto=texto, ids=sorted(cat["tests"]))
        return service.montar_hidratacao(_extraido(), cat)

    monkeypatch.setattr(planner_router, "extrair_hidratacao", falso)
    r = _cliente().post("/api/planner/hydrate", data={"texto": "queremos criar VMs", "catalogo": json.dumps(CATALOGO)})
    assert r.status_code == 200 and r.json()["tests"][0]["id"] == "virt-vm-create"
    assert chamado == {"texto": "queremos criar VMs", "ids": ["virt-livemig", "virt-vm-create"]}


def test_hydrate_entradas_ruins():
    c = _cliente()
    assert c.post("/api/planner/hydrate", data={"texto": "x", "catalogo": "{nao json"}).status_code == 400
    assert c.post("/api/planner/hydrate", data={"texto": "x", "catalogo": json.dumps({"tests": [{"id": 1}]})}).status_code == 400
    assert c.post("/api/planner/hydrate", data={"texto": "  ", "catalogo": json.dumps(CATALOGO)}).status_code == 400
    r = c.post("/api/planner/hydrate", files={"arquivo": ("x.bin", b"\xff\xfe\x00")}, data={"catalogo": json.dumps(CATALOGO)})
    assert r.status_code == 400


def test_hydrate_falha_do_gemini_vira_502(monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(planner_router, "extrair_hidratacao", quebra)
    r = _cliente().post("/api/planner/hydrate", data={"texto": "x", "catalogo": json.dumps(CATALOGO)})
    assert r.status_code == 502


def test_aderencia_nunca_vira_certeza_sem_fonte():
    av = service.AvaliacaoAderencia(categoria="native", justificativa="parece nativo")
    sem = service.montar_aderencia("t1", av, [], list(service.CATEGORIAS_ADERENCIA))
    assert sem["fit"] == "validate" and sem["sources"] == []
    fonte = [FonteEvidencia(titulo="Docs", url="https://documentation.suse.com/x"), FonteEvidencia(titulo="x", url="javascript:alert(1)")]
    com = service.montar_aderencia("t1", av, fonte, list(service.CATEGORIAS_ADERENCIA))
    assert com["fit"] == "native" and [s["url"] for s in com["sources"]] == ["https://documentation.suse.com/x"]
    repetidas = [FonteEvidencia(titulo="A", url="https://a.example/x")] * 3 + [FonteEvidencia(titulo="B", url="https://b.example/y")]
    assert [x["url"] for x in service.montar_aderencia("t1", av, repetidas, ["native", "validate"])["sources"]] == ["https://a.example/x", "https://b.example/y"]
    fora = service.montar_aderencia("t1", service.AvaliacaoAderencia(categoria="inventada", justificativa=""), fonte, ["native", "validate"])
    assert fora["fit"] == "validate"


def test_feasibility_contrato(monkeypatch):
    def falso(teste, fits, lang, key, model):
        assert fits == ["native", "gap"] and lang == "pt"
        return {"id": teste["id"], "fit": "native", "rationale": "ok", "sources": []}

    monkeypatch.setattr(planner_router, "sugerir_aderencia", falso)
    c = _cliente()
    r = c.post("/api/planner/feasibility", json={"lang": "pt", "fits": ["native", "gap"], "tests": [{"id": "a", "product": "p", "title": "t"}]})
    assert r.status_code == 200 and r.json() == {"kind": "suse-poc-feasibility", "schema": 1, "results": [{"id": "a", "fit": "native", "rationale": "ok", "sources": []}]}
    muitos = [{"id": str(i), "title": "t"} for i in range(service.LIMITE_TESTES_ADERENCIA + 1)]
    assert c.post("/api/planner/feasibility", json={"tests": muitos}).status_code == 422
    assert c.post("/api/planner/feasibility", json={"tests": []}).status_code == 422


def test_procedure_draft_contrato(monkeypatch):
    import uuid

    from app.models import OrigemConhecimento, Procedimento, StatusProcedimento

    chamado = {}

    def falso(db, titulo, esperado, produto, cliente, escopo, dono_id, api_key, model):
        chamado.update(titulo=titulo, esperado=esperado, produto=produto, cliente=cliente, escopo=escopo)
        return Procedimento(
            id=uuid.uuid4(), titulo="Criar VM no Harvester (rascunho)", tags=["virtualization"],
            cliente_origem=cliente or None, status=StatusProcedimento.rascunho,
            origem_conhecimento=OrigemConhecimento.planejador, gerado_por_ia=True, versao=1,
            html_original="<h2>Objetivo</h2><p>x</p>", idioma_original="pt",
        )

    monkeypatch.setattr(planner_router, "gerar_rascunho_planner", falso)
    c = _cliente()
    body = {
        "test": {"id": "virt-vm-create", "product": "virtualization", "title": "Criar VM", "expected": "VM criada"},
        "client": "Acme", "scope": "Substituição de VMware",
    }
    r = c.post("/api/planner/procedure-draft", json=body)
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "rascunho" and j["tags"] == ["virtualization"] and j["html_original"].startswith("<h2>")
    assert j["idioma_original"] == "pt"
    assert chamado == {
        "titulo": "Criar VM", "esperado": "VM criada", "produto": "virtualization",
        "cliente": "Acme", "escopo": "Substituição de VMware",
    }


def test_procedure_draft_falha_do_gemini_vira_502(monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(planner_router, "gerar_rascunho_planner", quebra)
    c = _cliente()
    r = c.post("/api/planner/procedure-draft", json={"test": {"id": "a", "product": "p", "title": "t"}})
    assert r.status_code == 502
