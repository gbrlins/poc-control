"""Histórico anônimo de resultados (ADR 1) contra um Postgres de verdade. Pula se não houver banco acessível: rode
dentro do container da api (`docker compose exec api python -m pytest tests/test_resultados_db.py`)."""
import json
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

try:
    with SessionLocal() as _db:
        _db.execute(text("select 1 from resultados_catalogo limit 1"))
except Exception:  # noqa: BLE001
    pytest.skip("sem Postgres com a migração 0016 aplicada", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app.deps import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Item, Poc, ResultadoCatalogo, StatusExtracao, StatusHistorico, StatusItem  # noqa: E402
from app.pocs.tasks import _aplicar_planejador  # noqa: E402
from app.pocs.planner_import import itens_do_planejador  # noqa: E402


class _U:
    id = uuid.uuid4()
    gemini_api_key_encrypted = None
    gemini_model = None


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def marca():
    return "t-" + uuid.uuid4().hex[:10]


def _poc_com(db, marca, testes):
    texto = json.dumps({"planner": {"project": {"projectName": "PoC " + marca, "clientOrganization": "C"}}, "tests": testes})
    poc = Poc(titulo="", cliente="", status_extracao=StatusExtracao.extraindo)
    db.add(poc)
    db.commit()
    # documento_id=None: este teste não grava um PocDocumento de verdade, só o efeito colateral
    # de _aplicar_planejador em itens/fases. O status final (pronto) é responsabilidade de quem
    # orquestra a fila (app/pocs/tasks.py::processar_poc), não da função por documento -- simulado
    # aqui pra bater com o fluxo real.
    _aplicar_planejador(db, poc, None, itens_do_planejador(texto))
    poc.status_extracao = StatusExtracao.pronto
    db.commit()
    db.refresh(poc)
    return poc


def _t(marca, n, **kw):
    base = {"id": f"p{n}", "catalogId": f"{marca}-{n}", "product": "virtualization", "productName": "SUSE Virtualization",
            "title": f"Teste {n}", "expected": "ok", "priority": "must", "fit": "native", "led": "suse", "result": "pending", "owner": ""}
    base.update(kw)
    return base


def _limpa(db, marca):
    db.query(ResultadoCatalogo).filter(ResultadoCatalogo.catalogo_id.like(marca + "%")).delete(synchronize_session=False)
    db.query(Poc).filter(Poc.titulo == "PoC " + marca).delete(synchronize_session=False)
    db.commit()


def test_criar_itens_grava_so_resultados_terminais(db, marca):
    try:
        poc = _poc_com(db, marca, [_t(marca, 1, result="pass"), _t(marca, 2, result="fail"), _t(marca, 3, result="pending"), _t(marca, 4, result="na")])
        assert poc.titulo == "PoC " + marca and poc.status_extracao == StatusExtracao.pronto and poc.modelo_extracao == "planejador (sem IA)"
        assert len(poc.itens) == 4 and poc.fases[0]["titulo"] == "SUSE Virtualization"
        linhas = {l.catalogo_id: l for l in db.query(ResultadoCatalogo).filter(ResultadoCatalogo.catalogo_id.like(marca + "%"))}
        assert set(linhas) == {f"{marca}-1", f"{marca}-2"}
        assert linhas[f"{marca}-1"].sucesso is True and linhas[f"{marca}-2"].sucesso is False
        from datetime import date
        assert all(l.executado_em == date.today().replace(day=1) for l in linhas.values()), "só o mês é guardado (dia 1)"
    finally:
        _limpa(db, marca)


def test_bloqueio_depois_do_pass_tira_o_sem_problemas_e_voltar_a_pendente_remove_a_linha(db, marca):
    app.dependency_overrides[get_current_user] = lambda: _U()
    c = TestClient(app)
    try:
        poc = _poc_com(db, marca, [_t(marca, 1, result="pass")])
        item = poc.itens[0]
        url = f"/api/pocs/{poc.id}/itens/{item.id}"
        linha = lambda: db.query(ResultadoCatalogo).filter_by(poc_id=poc.id, catalogo_id=item.catalogo_id).first()  # noqa: E731
        assert linha().sucesso is True
        assert c.patch(url, json={"status": "bloqueado"}).status_code == 200
        db.expire_all()
        assert linha().sucesso is False, "uma transição para bloqueado depois do pass tira o 'sem problemas'"
        assert c.patch(url, json={"resultado": "partial"}).status_code == 200
        db.expire_all()
        assert linha().resultado.value == "partial" and linha().sucesso is False
        assert c.patch(url, json={"resultado": "pending"}).status_code == 200
        db.expire_all()
        assert linha() is None, "resultado que deixou de ser terminal não é mais uma execução"
        assert c.patch(url, json={"resultado": "bogus"}).status_code == 422
    finally:
        app.dependency_overrides.clear()
        _limpa(db, marca)


def test_historico_sobrevive_a_exclusao_da_poc_e_fica_anonimo(db, marca):
    try:
        poc = _poc_com(db, marca, [_t(marca, 1, result="pass", fit="config")])
        poc_id = poc.id
        db.delete(poc)
        db.commit()
        assert db.query(Item).filter(Item.poc_id == poc_id).count() == 0, "os itens saem em cascata"
        linha = db.query(ResultadoCatalogo).filter(ResultadoCatalogo.catalogo_id == f"{marca}-1").one()
        assert linha.poc_id is None and linha.sucesso is True and linha.aderencia.value == "config"
        colunas = {c.name for c in ResultadoCatalogo.__table__.columns}
        assert colunas == {"id", "catalogo_id", "resultado", "aderencia", "sucesso", "executado_em", "poc_id"}, "sem cliente, título, dono nem texto"
    finally:
        _limpa(db, marca)


def test_endpoint_de_historico_sugere_a_aderencia_mais_nativa_entre_os_sucessos(db, marca):
    app.dependency_overrides[get_current_user] = lambda: _U()
    c = TestClient(app)
    ids = []
    try:
        cat = f"{marca}-1"
        for fit, res in (("rancher", "pass"), ("config", "pass"), ("native", "fail"), ("gap", "pass")):
            ids.append(_poc_com(db, marca, [_t(marca, 1, result=res, fit=fit)]).id)
        r = c.get("/api/planner/history", params={"ids": f"{cat},{marca}-9"})
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "suse-poc-history" and body["schema"] == 1
        assert body["results"][cat] == {"runs": 4, "successes": 3, "suggestedFit": "config"}, "a mais nativa entre as COM sucesso (o native falhou)"
        assert body["results"][f"{marca}-9"] == {"runs": 0, "successes": 0, "suggestedFit": None}
        assert c.get("/api/planner/history", params={"ids": ""}).status_code == 400
        assert c.get("/api/planner/history", params={"ids": ",".join(str(n) for n in range(201))}).status_code == 400
        app.dependency_overrides.clear()
        assert TestClient(app).get("/api/planner/history", params={"ids": cat}).status_code == 401
    finally:
        app.dependency_overrides.clear()
        for i in ids:
            db.query(Poc).filter(Poc.id == i).delete(synchronize_session=False)
        db.commit()
        _limpa(db, marca)
