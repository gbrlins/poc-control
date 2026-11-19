"""Ponta a ponta contra Postgres (Gemini simulado): plano importado em ESPANHOL, visto em inglês na tela e nos relatórios, com o banco intacto."""
import json
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

try:
    with SessionLocal() as _db:
        _db.execute(text("select idiomas, traducoes from itens limit 1"))
        _db.execute(text("select idiomas, traducoes from sessoes limit 1"))
except Exception:  # noqa: BLE001
    pytest.skip("sem Postgres com a migração 0034 aplicada", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app import traducao_cache  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Classificacao, FlagClassificacao, Item, OrigemClassificacao, Poc, User  # noqa: E402


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def usuario(db):
    u = User(email=f"rel-{uuid.uuid4().hex[:8]}@teste.example", password_hash="x", is_admin=False)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.expunge(u)
    app.dependency_overrides[get_current_user] = lambda: u
    yield u
    app.dependency_overrides.clear()
    db.query(Poc).filter(Poc.criado_por_id == u.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == u.id).delete(synchronize_session=False)
    db.commit()


def _falso(monkeypatch):
    chamadas = []

    def fake(textos, idioma, api_key=None, model=None):
        chamadas.append((list(textos), idioma))
        return [f"[{idioma}] {t}" for t in textos]

    monkeypatch.setattr(traducao_cache, "traduzir_textos", fake)
    return chamadas


def _poc_em_espanhol(c, db, lang="es"):
    doc = {"schema": 2, "planner": {"lang": lang, "project": {"projectName": "Proyecto", "clientOrganization": "ACME"}},
           "tests": [{"id": "a", "title": "Crear el clúster", "expected": "Nodos listos", "product": "rancher", "productName": "Rancher"}]}
    r = c.post("/api/pocs/importar-planejador", data={"texto": json.dumps(doc)})
    assert r.status_code == 201, r.text
    pid = uuid.UUID(r.json()["id"])
    item = db.query(Item).filter(Item.poc_id == pid).one()
    db.add(Classificacao(item_id=item.id, flag=FlagClassificacao.verde, origem=OrigemClassificacao.auto, justificativa="Atiende de forma nativa.", fontes=[], idiomas={"justificativa": lang}))
    db.commit()
    return pid, item.id


def test_item_do_planejador_fica_marcado_no_idioma_do_plano_e_so_nos_campos_que_tem(usuario, db):
    pid, iid = _poc_em_espanhol(TestClient(app), db)
    item = db.get(Item, iid)
    assert item.idiomas == {"titulo": "es", "criterio_aceite": "es", "categoria": "es"}      # sem descricao: nada a marcar


def test_plano_sem_lang_fica_sem_marca_e_vale_pt(usuario, db):
    doc = {"schema": 2, "planner": {"project": {"projectName": "P", "clientOrganization": "C"}},
           "tests": [{"id": "a", "title": "Teste A", "product": "rancher", "productName": "Rancher"}]}
    r = TestClient(app).post("/api/pocs/importar-planejador", data={"texto": json.dumps(doc)})
    item = db.query(Item).filter(Item.poc_id == uuid.UUID(r.json()["id"])).one()
    assert item.idiomas is None


def test_tela_em_es_nao_traduz_o_que_ja_esta_em_es_mas_em_en_sim_e_orig_nao_traduz_nunca(usuario, db, monkeypatch):
    chamadas = _falso(monkeypatch)
    c = TestClient(app)
    pid, _ = _poc_em_espanhol(c, db)
    itens = lambda lang: c.get(f"/api/pocs/{pid}", headers={"X-UI-Lang": lang}).json()["itens"]
    assert itens("es")[0]["titulo"] == "Crear el clúster" and chamadas == []          # mesmo idioma: original
    assert itens("orig")[0]["titulo"] == "Crear el clúster" and chamadas == []        # pedido explícito de "como está gravado"
    em_en = itens("en")[0]
    assert em_en["titulo"] == "[en] Crear el clúster" and em_en["classificacao"]["justificativa"] == "[en] Atiende de forma nativa."
    db.expire_all()
    assert db.query(Item).filter(Item.poc_id == pid).one().titulo == "Crear el clúster"     # o banco nunca recebe a tradução


def test_relatorios_da_poc_saem_no_idioma_pedido_e_o_banco_fica_intacto(usuario, db, monkeypatch):
    _falso(monkeypatch)
    c = TestClient(app)
    pid, iid = _poc_em_espanhol(c, db)
    for rota in ("export", "apresentacao"):
        html = c.get(f"/api/pocs/{pid}/{rota}?lang=en").text
        assert "[en] Crear el clúster" in html, rota
        assert "Crear el clúster" in c.get(f"/api/pocs/{pid}/{rota}?lang=es").text.replace("[en] ", "")
    roteiro = c.get(f"/api/pocs/{pid}/roteiro?lang=en&item_ids={iid}").text
    assert "[en] Crear el clúster" in roteiro and "[en] Nodos listos" in roteiro
    # o idioma padrão sem ?lang= é o inglês
    assert "[en] Crear el clúster" in c.get(f"/api/pocs/{pid}/export").text
    db.expire_all()
    item = db.get(Item, iid)
    assert item.titulo == "Crear el clúster" and db.get(Item, iid).classificacao.justificativa == "Atiende de forma nativa."


def test_resumo_executivo_e_pontos_da_sessao_marcados_e_traduzidos_no_relatorio(usuario, db, monkeypatch):
    _falso(monkeypatch)
    c = TestClient(app)
    pid, _ = _poc_em_espanhol(c, db)
    r = c.patch(f"/api/pocs/{pid}/apresentacao/resumo", json={"resumo_executivo": "Resumen en español."}, headers={"X-UI-Lang": "es"})
    assert r.status_code == 200, r.text
    from app.models import Sessao
    s = Sessao(poc_id=pid, data=__import__("datetime").date.today(), participantes=["Ana"], pontos_resolvidos=["Todo listo"], pontos_falha=[], proximos_passos=["Seguir"])
    from app.idioma import marcar
    from app.pocs.traducao import LISTAS_DA_SESSAO, TextosDaSessao
    marcar(TextosDaSessao(s), "es", *LISTAS_DA_SESSAO)
    db.add(s)
    db.commit()
    poc = db.get(Poc, pid)
    assert poc.idiomas == {"resumo_executivo": "es"}
    html = c.get(f"/api/pocs/{pid}/apresentacao?lang=en").text
    assert "[en] Resumen en español." in html and "[en] Todo listo" in html and "[en] Seguir" in html
