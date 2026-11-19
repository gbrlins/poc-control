"""Importação de procedimentos por JSON (Postgres; Gemini simulado): duplicados por categorias normalizadas, sobrescrever só como dono,
e idioma/título em inglês refeitos ao sobrescrever como num upload."""
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

try:
    with SessionLocal() as _db:
        _db.execute(text("select 1 from procedimentos limit 1"))
except Exception:  # noqa: BLE001
    pytest.skip("sem Postgres", allow_module_level=True)

from types import SimpleNamespace  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.deps import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Procedimento, User  # noqa: E402
from app.procedimentos import router as procedimentos_router  # noqa: E402

HTML = "<h2>Objetivo</h2><p>Fazer.</p><h2>Passo 1</h2><p>Esperado: ok.</p>"


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def _usuario(db, prefixo):
    u = User(email=f"{prefixo}-{uuid.uuid4().hex[:8]}@teste.example", password_hash="x", is_admin=False)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.expunge(u)
    return u


@pytest.fixture()
def dois_usuarios(db):
    a, b = _usuario(db, "dono"), _usuario(db, "outro")
    yield a, b
    db.query(Procedimento).filter(Procedimento.criado_por_id.in_([a.id, b.id])).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_([a.id, b.id])).delete(synchronize_session=False)
    db.commit()
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def gemini_falso(monkeypatch):
    monkeypatch.setattr(procedimentos_router, "embed_document", lambda texto, api_key=None: [0.1] * 1536)
    chamadas = []

    def traduzir(html, idioma, titulo, api_key=None):
        chamadas.append(titulo)
        return SimpleNamespace(idioma_detectado="en", titulo_traduzido=f"EN {titulo}", html_traduzido=html)

    monkeypatch.setattr(procedimentos_router, "traduzir_procedimento_html", traduzir)
    return chamadas


def _como(usuario):
    app.dependency_overrides[get_current_user] = lambda: usuario
    return TestClient(app)


def _item(**kw):
    base = {"titulo": "Instalar Rancher", "html_original": HTML, "categorias": ["K8S"], "status": "rascunho"}
    base.update(kw)
    return base


def test_categoria_em_minuscula_no_json_acha_o_duplicado(dois_usuarios):
    dono, _ = dois_usuarios
    c = _como(dono)
    r = c.post("/api/procedimentos/importar-json", json={"itens": [_item()]})
    assert r.json()[0]["status"] == "importado", r.text
    previa = c.post("/api/procedimentos/importar-json/preview", json=[_item(categorias=["k8s"])]).json()[0]
    assert previa["duplicado_id"] == r.json()[0]["id"]          # "k8s" vs o "K8S" guardado


def test_so_o_dono_sobrescreve(dois_usuarios, db):
    dono, outro = dois_usuarios
    criado = _como(dono).post("/api/procedimentos/importar-json", json={"itens": [_item()]}).json()[0]
    novo = _item(html_original="<h2>Outro</h2><p>Conteúdo trocado.</p>", status="validado")
    r = _como(outro).post("/api/procedimentos/importar-json", json={"itens": [novo], "sobrescrever_ids": [criado["id"]]}).json()[0]
    assert r["status"] == "erro" and "owner" in r["erro"]
    db.expire_all()
    p = db.get(Procedimento, uuid.UUID(criado["id"]))
    assert "Objetivo" in p.html_original and p.status.value == "rascunho"          # nada mudou
    # o dono pode, e o resultado é "sobrescrito"
    r2 = _como(dono).post("/api/procedimentos/importar-json", json={"itens": [novo], "sobrescrever_ids": [criado["id"]]}).json()[0]
    assert r2["status"] == "sobrescrito"
    db.expire_all()
    assert "Conteúdo trocado" in db.get(Procedimento, uuid.UUID(criado["id"])).html_original


def test_sem_ser_pedido_para_sobrescrever_o_duplicado_e_pulado_para_qualquer_um(dois_usuarios):
    dono, outro = dois_usuarios
    criado = _como(dono).post("/api/procedimentos/importar-json", json={"itens": [_item()]}).json()[0]
    assert _como(outro).post("/api/procedimentos/importar-json", json={"itens": [_item()]}).json()[0]["status"] == "pulado"
    assert criado["status"] == "importado"


def test_sobrescrever_refaz_idioma_e_titulo_em_ingles_como_um_upload(dois_usuarios, db, gemini_falso):
    dono, _ = dois_usuarios
    c = _como(dono)
    criado = c.post("/api/procedimentos/importar-json", json={"itens": [_item(titulo_en="Install Rancher", idioma_original="pt")]}).json()[0]
    gemini_falso.clear()
    # JSON sem idioma nem título em inglês: o conteúdo é novo, então os antigos não valem
    r = c.post("/api/procedimentos/importar-json", json={"itens": [_item()], "sobrescrever_ids": [criado["id"]]}).json()[0]
    assert r["status"] == "sobrescrito" and gemini_falso == ["Instalar Rancher"]
    db.expire_all()
    p = db.get(Procedimento, uuid.UUID(criado["id"]))
    assert p.idioma_original == "en" and p.titulo_en == "EN Instalar Rancher"


def test_biblioteca_exportada_pelo_planejador_e_importada_e_reimportada_como_duplicada(dois_usuarios, db):
    dono, _ = dois_usuarios
    c = _como(dono)
    biblioteca = {"kind": "suse-poc-procedure-library", "schema": 1, "procedures": [
        {"id": "loc-1", "title": "Procedimento da biblioteca", "html": HTML, "products": ["rancher"], "status": "rascunho", "version": 1}
    ]}
    previa = c.post("/api/procedimentos/importar-json/preview", json=biblioteca).json()
    assert previa[0]["valido"] and previa[0]["duplicado_id"] is None, previa
    r = c.post("/api/procedimentos/importar-json", json={"itens": [biblioteca]}).json()[0]
    assert r["status"] == "importado", r
    db.expire_all()
    p = db.get(Procedimento, uuid.UUID(r["id"]))
    assert p.titulo == "Procedimento da biblioteca" and p.categorias == ["K8S"] and "Objetivo" in p.html_original
    # a mesma biblioteca de novo: o duplicado (mesmo título + categorias) é reconhecido
    de_novo = c.post("/api/procedimentos/importar-json/preview", json=biblioteca).json()[0]
    assert de_novo["duplicado_id"] == r["id"]
