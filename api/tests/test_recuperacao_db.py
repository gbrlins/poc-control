"""Recuperação de extrações interrompidas (ADR 7) contra um Postgres de verdade. Pula se não houver banco: rode dentro do
container da api (`docker compose exec api python -m pytest tests/test_recuperacao_db.py`)."""
import logging
import pathlib
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

try:
    with SessionLocal() as _db:
        _db.execute(text("select 1 from pocs limit 1"))
except Exception:  # noqa: BLE001
    pytest.skip("sem Postgres acessível", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main_mod  # noqa: E402
import app.pocs.router as pocs_router  # noqa: E402
from app.config import settings  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Poc, PocDocumento, Rfi, StatusExtracao, User  # noqa: E402
from app.recuperacao import MENSAGEM_REINICIO, recuperar_extracoes_interrompidas  # noqa: E402


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
def limpo(db):
    """Cada teste começa sem nenhuma linha `extraindo` do banco (a recuperação varre o banco todo)."""
    db.query(Poc).filter(Poc.status_extracao == StatusExtracao.extraindo).update({"status_extracao": StatusExtracao.pronto})
    db.query(Rfi).filter(Rfi.status_extracao == StatusExtracao.extraindo).update({"status_extracao": StatusExtracao.pronto})
    db.commit()
    criados = {"pocs": [], "rfis": [], "users": []}
    yield criados
    for i in criados["pocs"]:
        db.query(Poc).filter(Poc.id == i).delete()
    for i in criados["rfis"]:
        db.query(Rfi).filter(Rfi.id == i).delete()
    for i in criados["users"]:
        db.query(User).filter(User.id == i).delete()
    db.commit()


def _poc(db, limpo, status, erro=None):
    p = Poc(titulo="PoC " + uuid.uuid4().hex[:6], cliente="C", status_extracao=status, erro_extracao=erro)
    db.add(p)
    db.commit()
    limpo["pocs"].append(p.id)
    return p


def _rfi(db, limpo, status):
    u = User(email=f"{uuid.uuid4().hex[:8]}@teste.example", password_hash="x")
    db.add(u)
    db.commit()
    limpo["users"].append(u.id)
    r = Rfi(titulo="RFI", orgao="O", status_extracao=status, nome_arquivo="e.pdf", caminho_arquivo="", criado_por_id=u.id)
    db.add(r)
    db.commit()
    limpo["rfis"].append(r.id)
    return r


def test_marca_como_erro_so_o_que_estava_extraindo(db, limpo):
    preso, pronto = _poc(db, limpo, StatusExtracao.extraindo), _poc(db, limpo, StatusExtracao.pronto)
    falhou = _poc(db, limpo, StatusExtracao.erro, erro="503 do Gemini")
    rfi_preso, rfi_pronto = _rfi(db, limpo, StatusExtracao.extraindo), _rfi(db, limpo, StatusExtracao.pronto)
    assert recuperar_extracoes_interrompidas(db) == {"pocs": 1, "rfis": 1}
    db.expire_all()
    assert db.get(Poc, preso.id).status_extracao == StatusExtracao.erro and db.get(Poc, preso.id).erro_extracao == MENSAGEM_REINICIO
    assert db.get(Rfi, rfi_preso.id).status_extracao == StatusExtracao.erro and db.get(Rfi, rfi_preso.id).erro_extracao == MENSAGEM_REINICIO
    assert db.get(Poc, pronto.id).status_extracao == StatusExtracao.pronto and db.get(Rfi, rfi_pronto.id).status_extracao == StatusExtracao.pronto
    assert db.get(Poc, falhou.id).erro_extracao == "503 do Gemini", "um erro real anterior não é sobrescrito"
    assert recuperar_extracoes_interrompidas(db) == {"pocs": 0, "rfis": 0}, "idempotente"


def test_ao_subir_a_api_recupera_e_o_tentar_de_novo_volta_a_funcionar(db, limpo, monkeypatch, tmp_path):
    preso = _poc(db, limpo, StatusExtracao.extraindo)
    arquivo = tmp_path / "plano.txt"
    arquivo.write_text("texto do plano")
    doc = PocDocumento(poc_id=preso.id, nome_arquivo="plano.txt", caminho_arquivo=str(arquivo))
    db.add(doc)
    db.commit()
    chamadas = []
    monkeypatch.setattr(pocs_router, "processar_poc", lambda *a, **k: chamadas.append((a, k)))
    app.dependency_overrides[get_current_user] = lambda: _U()
    try:
        with TestClient(app) as c:  # entrar no contexto dispara o lifespan (a "inicialização")
            db.expire_all()
            assert db.get(Poc, preso.id).status_extracao == StatusExtracao.erro
            r = c.post(f"/api/pocs/{preso.id}/reextrair")
            assert r.status_code == 202, "o botão de nova tentativa, que só aceitava erro, agora alcança a PoC"
        db.expire_all()
        assert db.get(Poc, preso.id).status_extracao == StatusExtracao.extraindo and db.get(Poc, preso.id).erro_extracao is None
        assert len(chamadas) == 1 and chamadas[0][0][0] == preso.id and chamadas[0][0][1] == [doc.id]
    finally:
        app.dependency_overrides.clear()


def test_desligado_nao_mexe_em_nada(db, limpo, monkeypatch):
    preso = _poc(db, limpo, StatusExtracao.extraindo)
    monkeypatch.setattr(settings, "extracao_recuperar_no_inicio", False)
    with TestClient(app):
        pass
    db.expire_all()
    assert db.get(Poc, preso.id).status_extracao == StatusExtracao.extraindo


def test_falha_na_recuperacao_nunca_impede_a_api_de_subir(db, limpo, monkeypatch, caplog):
    def quebra(_):
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(main_mod, "recuperar_extracoes_interrompidas", quebra)
    with caplog.at_level(logging.ERROR):
        with TestClient(app) as c:
            assert c.get("/api/health").status_code == 200
    assert "Não consegui recuperar as extrações interrompidas" in caplog.text


def test_quem_nao_estava_preso_e_deixado_em_paz_no_banco_inteiro(db, limpo):
    # nada em `extraindo`: a varredura não toca em nenhuma linha
    antes = db.query(Poc).filter(Poc.status_extracao == StatusExtracao.erro).count()
    assert recuperar_extracoes_interrompidas(db) == {"pocs": 0, "rfis": 0}
    assert db.query(Poc).filter(Poc.status_extracao == StatusExtracao.erro).count() == antes
