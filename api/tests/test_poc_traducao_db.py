"""Justificativa da classificação traduzida na tela da PoC (Postgres; Gemini simulado): só o texto da IA, com cache, guiada por X-UI-Lang."""
import json
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

try:
    with SessionLocal() as _db:
        _db.execute(text("select traducoes from classificacoes limit 1"))
except Exception:  # noqa: BLE001
    pytest.skip("sem Postgres com a migração 0032 aplicada", allow_module_level=True)

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
    u = User(email=f"poc-{uuid.uuid4().hex[:8]}@teste.example", password_hash="x", is_admin=False)
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


def _poc_com_duas_classificacoes(c, db):
    doc = {"schema": 2, "planner": {"project": {"projectName": "P", "clientOrganization": "C"}},
           "tests": [{"id": "a", "title": "Teste A", "product": "rancher", "productName": "Rancher"},
                     {"id": "b", "title": "Teste B", "product": "rancher", "productName": "Rancher"}]}
    r = c.post("/api/pocs/importar-planejador", data={"texto": json.dumps(doc)})
    assert r.status_code == 201, r.text
    pid = uuid.UUID(r.json()["id"])
    itens = db.query(Item).filter(Item.poc_id == pid).order_by(Item.ordem).all()
    db.add(Classificacao(item_id=itens[0].id, flag=FlagClassificacao.verde, origem=OrigemClassificacao.auto, justificativa="Atende de forma nativa.", fontes=[]))
    db.add(Classificacao(item_id=itens[1].id, flag=FlagClassificacao.amarelo, origem=OrigemClassificacao.manual, justificativa="Escrito por mim.", fontes=[]))
    db.commit()
    return str(pid)


def test_traduz_justificativas_e_itens_para_outro_idioma_e_guarda_em_cache(usuario, db, monkeypatch):
    chamadas = []

    def fake(textos, idioma, api_key=None, model=None):
        chamadas.append(list(textos))
        return [f"[{idioma}] {t}" for t in textos]

    monkeypatch.setattr(traducao_cache, "traduzir_textos", fake)
    c = TestClient(app)
    pid = _poc_com_duas_classificacoes(c, db)

    em_en = c.get(f"/api/pocs/{pid}", headers={"X-UI-Lang": "en"}).json()["itens"]
    # O título do item também sai traduzido agora (itens_no_idioma): a chave é o título original sem o prefixo do dublê.
    justs = {i["titulo"].removeprefix("[en] "): i["classificacao"]["justificativa"] for i in em_en}
    # O texto digitado por uma pessoa também é mostrado traduzido a quem lê em outro idioma (o banco guarda o que ela escreveu).
    assert justs == {"Teste A": "[en] Atende de forma nativa.", "Teste B": "[en] Escrito por mim."}
    # Duas levas: as justificativas e os textos dos itens.
    assert sorted(chamadas[0]) == ["Atende de forma nativa.", "Escrito por mim."] and {"Teste A", "Teste B"} <= set(chamadas[1])

    c.get(f"/api/pocs/{pid}", headers={"X-UI-Lang": "en"})            # segunda abertura: cache, sem nova chamada
    assert len(chamadas) == 2
    em_pt = c.get(f"/api/pocs/{pid}", headers={"X-UI-Lang": "pt"}).json()["itens"]   # texto pt visto em pt: original intacto, sem tradução
    assert {i["classificacao"]["justificativa"] for i in em_pt} == {"Atende de forma nativa.", "Escrito por mim."}
