"""Sincronização de Procedimentos com outra instância do poc-control (Postgres, dentro do
container da api). Nenhuma chamada HTTP de verdade acontece: cliente_remoto/listar_remotos/
obter_remoto/criar_remoto (app/sync/client.py) são trocados por versões falsas. embed_document
também é falso -- criar um procedimento localmente (fluxo de "baixar") não pode depender do
Gemini de verdade."""
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

try:
    with SessionLocal() as _db:
        _db.execute(text("select 1 from procedimentos limit 1"))
except Exception:  # noqa: BLE001
    pytest.skip("sem Postgres", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app.deps import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Procedimento, User  # noqa: E402
from app.procedimentos import router as procedimentos_router  # noqa: E402
from app.sync import router as sync_router  # noqa: E402
from app.sync.client import RemotoErro  # noqa: E402


class _ClienteFalso:
    def close(self):
        pass


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def usuario(db):
    u = User(email=f"sync-{uuid.uuid4().hex[:8]}@teste.example", password_hash="x", is_admin=False)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.expunge(u)
    app.dependency_overrides[get_current_user] = lambda: u
    yield u
    app.dependency_overrides.clear()
    db.query(Procedimento).filter(Procedimento.criado_por_id == u.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == u.id).delete(synchronize_session=False)
    db.commit()


@pytest.fixture(autouse=True)
def gemini_falso(monkeypatch):
    monkeypatch.setattr(procedimentos_router, "embed_document", lambda texto, api_key=None: [0.1] * 1536)


@pytest.fixture(autouse=True)
def cliente_remoto_falso(monkeypatch):
    monkeypatch.setattr(sync_router, "cliente_remoto", lambda: _ClienteFalso())


def _html(titulo: str) -> str:
    return f"<h2>{titulo}</h2><p>conteúdo</p>"


def test_config_reflete_settings(usuario, monkeypatch):
    c = TestClient(app)
    monkeypatch.setattr(sync_router.settings, "sync_servidor_url", "")
    assert c.get("/api/sync/config").json() == {"configurado": False}
    monkeypatch.setattr(sync_router.settings, "sync_servidor_url", "http://remoto")
    monkeypatch.setattr(sync_router.settings, "sync_servidor_email", "a@b.com")
    monkeypatch.setattr(sync_router.settings, "sync_servidor_senha", "x")
    assert c.get("/api/sync/config").json() == {"configurado": True}


def test_baixar_cria_local_e_erro_num_nao_trava_os_demais(usuario, db, monkeypatch):
    c = TestClient(app)
    id_ok, id_ruim = str(uuid.uuid4()), str(uuid.uuid4())

    def obter_remoto_falso(cliente, procedimento_id):
        if procedimento_id == id_ruim:
            raise RemotoErro("removido no servidor entre listar e baixar")
        return {
            "titulo": "Procedimento remoto",
            "tags": ["k8s"],
            "categorias": ["K8S"],
            "cliente_origem": "Cliente X",
            "data_origem": None,
            "status": "validado",
            "versao": 1,
            "html_original": _html("Procedimento remoto"),
        }

    monkeypatch.setattr(sync_router, "obter_remoto", obter_remoto_falso)
    r = c.post("/api/sync/remoto/baixar", json={"ids": [id_ok, id_ruim]})
    assert r.status_code == 200, r.text
    por_id = {x["id"]: x for x in r.json()}
    assert por_id[id_ok]["status"] == "baixado"
    assert por_id[id_ruim]["status"] == "erro" and "removido" in por_id[id_ruim]["erro"]

    criado = db.query(Procedimento).filter(Procedimento.titulo == "Procedimento remoto").one()
    assert criado.status.value == "validado"
    assert criado.cliente_origem == "Cliente X"
    assert criado.responsavel_id == usuario.id, "quem baixou vira o dono local"


def test_baixar_sem_servidor_configurado_da_502(usuario, monkeypatch):
    c = TestClient(app)
    monkeypatch.setattr(sync_router, "cliente_remoto", lambda: (_ for _ in ()).throw(RemotoErro("não configurado")))
    r = c.post("/api/sync/remoto/baixar", json={"ids": [str(uuid.uuid4())]})
    assert r.status_code == 502


def test_enviar_so_apaga_local_se_servidor_confirmar(usuario, db, monkeypatch):
    c = TestClient(app)
    procedimentos_router._criar_procedimento(
        db,
        titulo="Vai pro servidor",
        tags=["storage"],
        categorias=["STR"],
        cliente_origem=None,
        data_origem=None,
        status_valor=procedimentos_router.StatusProcedimento.validado,
        versao=1,
        html=_html("Vai pro servidor"),
        dono_id=usuario.id,
    )
    procedimentos_router._criar_procedimento(
        db,
        titulo="Falha no servidor",
        tags=[],
        categorias=[],
        cliente_origem=None,
        data_origem=None,
        status_valor=procedimentos_router.StatusProcedimento.rascunho,
        versao=1,
        html=_html("Falha no servidor"),
        dono_id=usuario.id,
    )
    ok = db.query(Procedimento).filter(Procedimento.titulo == "Vai pro servidor").one()
    ruim = db.query(Procedimento).filter(Procedimento.titulo == "Falha no servidor").one()

    def criar_remoto_falso(cliente, procedimento):
        if procedimento.titulo == "Falha no servidor":
            raise RemotoErro("servidor recusou")
        return {"id": str(uuid.uuid4())}

    monkeypatch.setattr(sync_router, "criar_remoto", criar_remoto_falso)
    r = c.post("/api/sync/local/enviar", json={"ids": [str(ok.id), str(ruim.id)]})
    assert r.status_code == 200, r.text
    por_id = {x["id"]: x for x in r.json()}
    assert por_id[str(ok.id)]["status"] == "enviado"
    assert por_id[str(ruim.id)]["status"] == "erro" and "servidor recusou" in por_id[str(ruim.id)]["erro"]

    # db.get() depois de expire_all() num objeto já deletado por OUTRA sessão (a da chamada HTTP)
    # lança ObjectDeletedError em vez de devolver None -- peculiaridade do identity map do
    # SQLAlchemy quando o objeto já estava carregado nesta sessão. Uma query nova não tem esse problema.
    assert db.query(Procedimento).filter(Procedimento.id == ok.id).first() is None, "subiu com sucesso -- apaga local"
    assert db.query(Procedimento).filter(Procedimento.id == ruim.id).first() is not None, "falhou no servidor -- continua local"


def test_enviar_id_inexistente_vira_erro_sem_quebrar_o_lote(usuario):
    c = TestClient(app)
    r = c.post("/api/sync/local/enviar", json={"ids": [str(uuid.uuid4())]})
    assert r.status_code == 200
    assert r.json()[0]["status"] == "erro"
