"""Licitações ao vivo (beta): casamento de termo, upsert por numero_controle_pncp, e os endpoints
do router (Postgres, dentro do container da api:
`docker compose exec api sh -c 'pip install -q pytest && python -m pytest tests/test_licitacoes_db.py'`).
A rede nunca é batida de verdade -- app.licitacoes.service.buscar_publicacoes é sempre mockado."""
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

try:
    with SessionLocal() as _db:
        _db.execute(text("select 1 from licitacoes limit 1"))
except Exception:  # noqa: BLE001
    pytest.skip("sem Postgres com a migração 0027 aplicada", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app.deps import get_current_user  # noqa: E402
from app.licitacoes import router as licitacoes_router_module  # noqa: E402
from app.licitacoes import service  # noqa: E402
from app.licitacoes.matching import termos_que_batem  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Licitacao, TermoBuscaLicitacao, User  # noqa: E402


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def usuario(db):
    u = User(email=f"lic-{uuid.uuid4().hex[:8]}@teste.example", password_hash="x", is_admin=False)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.expunge(u)
    app.dependency_overrides[get_current_user] = lambda: u
    yield u
    app.dependency_overrides.clear()
    db.query(User).filter(User.id == u.id).delete(synchronize_session=False)
    db.commit()


@pytest.fixture()
def admin(db):
    u = User(email=f"lic-admin-{uuid.uuid4().hex[:8]}@teste.example", password_hash="x", is_admin=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.expunge(u)
    app.dependency_overrides[get_current_user] = lambda: u
    yield u
    app.dependency_overrides.clear()
    db.query(User).filter(User.id == u.id).delete(synchronize_session=False)
    db.commit()


def _termo(db, termo, categoria_codigo=None, ativo=True):
    t = TermoBuscaLicitacao(termo=termo, categoria_codigo=categoria_codigo, ativo=ativo)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _item_pncp(numero_controle, objeto, *, cnpj="12345678000100", ano=2026, sequencial=1):
    return {
        "numeroControlePNCP": numero_controle,
        "objetoCompra": objeto,
        "orgaoEntidade": {"razaoSocial": "Órgão de Teste", "cnpj": cnpj},
        "unidadeOrgao": {"nomeUnidade": "Unidade X", "ufSigla": "SP", "municipioNome": "São Paulo"},
        "dataPublicacaoPncp": "2026-11-05T10:00:00",
        "dataAberturaProposta": None,
        "dataEncerramentoProposta": None,
        "valorTotalEstimado": 10000.5,
        "anoCompra": ano,
        "sequencialCompra": sequencial,
    }


def test_termos_que_batem_ignora_acento_e_caixa():
    assert termos_que_batem("Fornecimento de CONTÊINERES para o datacenter", ["conteineres"]) == ["conteineres"]
    assert termos_que_batem("Virtualização de servidores", ["Virtualização"]) == ["Virtualização"]


def test_termos_que_batem_sem_match_devolve_vazio():
    assert termos_que_batem("Aquisição de papel A4", ["zzz-termo-inexistente"]) == []


def test_verificar_licitacoes_insere_nova_e_nao_duplica_na_proxima_rodada(db, monkeypatch):
    termo_texto = f"termo-teste-{uuid.uuid4().hex[:8]}"
    termo = _termo(db, termo_texto)
    numero = f"TESTE-{uuid.uuid4().hex[:8]}"
    item = _item_pncp(numero, f"Contratação de solução envolvendo {termo_texto}")

    def busca_falsa(data_inicial, data_final, codigo_modalidade):
        return [item] if codigo_modalidade == 6 else []

    monkeypatch.setattr(service, "buscar_publicacoes", busca_falsa)

    try:
        novas = service.verificar_licitacoes(db)
        assert novas == 1

        gravada = db.query(Licitacao).filter(Licitacao.numero_controle_pncp == numero).one()
        assert gravada.termos_encontrados == [termo_texto]
        assert gravada.modalidade_codigo == 6
        link_esperado = (
            f"https://pncp.gov.br/app/editais/{item['orgaoEntidade']['cnpj']}/"
            f"{item['anoCompra']}/{item['sequencialCompra']}"
        )
        assert gravada.link_pncp == link_esperado

        # roda de novo com o mesmo item: não duplica, só atualiza
        novas_de_novo = service.verificar_licitacoes(db)
        assert novas_de_novo == 0
        assert db.query(Licitacao).filter(Licitacao.numero_controle_pncp == numero).count() == 1
    finally:
        db.query(Licitacao).filter(Licitacao.numero_controle_pncp == numero).delete(synchronize_session=False)
        db.query(TermoBuscaLicitacao).filter(TermoBuscaLicitacao.id == termo.id).delete(synchronize_session=False)
        db.commit()


def test_verificar_licitacoes_ignora_item_sem_termo_batendo(db, monkeypatch):
    termo_texto = f"termo-teste-{uuid.uuid4().hex[:8]}"
    termo = _termo(db, termo_texto)
    numero = f"TESTE-{uuid.uuid4().hex[:8]}"
    item = _item_pncp(numero, "Aquisição de material de limpeza")

    def busca_falsa(data_inicial, data_final, codigo_modalidade):
        return [item] if codigo_modalidade == 6 else []

    monkeypatch.setattr(service, "buscar_publicacoes", busca_falsa)
    try:
        novas = service.verificar_licitacoes(db)
        assert novas == 0
        assert db.query(Licitacao).filter(Licitacao.numero_controle_pncp == numero).count() == 0
    finally:
        db.query(TermoBuscaLicitacao).filter(TermoBuscaLicitacao.id == termo.id).delete(synchronize_session=False)
        db.commit()


def test_rota_listar_exige_login_mas_nao_admin(usuario):
    c = TestClient(app)
    r = c.get("/api/licitacoes")
    assert r.status_code == 200


def test_rota_atualizar_dispara_em_segundo_plano_e_responde_na_hora(usuario, monkeypatch):
    # TestClient roda background tasks de forma síncrona (faz parte do ciclo ASGI do próprio
    # processo, não um worker à parte), então dá pra checar que a tarefa rodou sem precisar de
    # polling aqui -- mas o ponto da mudança (ver router.py) é não segurar a resposta HTTP
    # esperando a rodada inteira terminar, por isso o status 202 (aceito, ainda processando).
    chamadas = []
    monkeypatch.setattr(licitacoes_router_module, "verificar_licitacoes_em_segundo_plano", lambda: chamadas.append(1))
    c = TestClient(app)
    r = c.post("/api/licitacoes/atualizar")
    assert r.status_code == 202 and r.json() == {"iniciado": True}
    assert chamadas == [1]


def test_rota_status_reflete_a_trava_em_memoria(usuario, monkeypatch):
    c = TestClient(app)
    monkeypatch.setattr(service, "_em_andamento", False)
    assert c.get("/api/licitacoes/status").json() == {"em_andamento": False}
    monkeypatch.setattr(service, "_em_andamento", True)
    assert c.get("/api/licitacoes/status").json() == {"em_andamento": True}


def test_termos_crud_exige_admin(usuario):
    c = TestClient(app)
    assert c.get("/api/licitacoes/termos").status_code == 403
    assert c.post("/api/licitacoes/termos", json={"termo": "x"}).status_code == 403


def test_termos_crud_admin(db, admin):
    c = TestClient(app)
    termo_texto = f"termo-teste-{uuid.uuid4().hex[:8]}"
    r = c.post("/api/licitacoes/termos", json={"termo": termo_texto, "categoria_codigo": "K8S"})
    assert r.status_code == 201
    termo_id = r.json()["id"]
    assert r.json()["ativo"] is True

    r2 = c.get("/api/licitacoes/termos")
    assert r2.status_code == 200 and any(t["id"] == termo_id for t in r2.json())

    r3 = c.patch(f"/api/licitacoes/termos/{termo_id}")
    assert r3.status_code == 200 and r3.json()["ativo"] is False

    r4 = c.delete(f"/api/licitacoes/termos/{termo_id}")
    assert r4.status_code == 204
    assert not any(t["id"] == termo_id for t in c.get("/api/licitacoes/termos").json())


def test_nao_pode_criar_termo_duplicado(db, admin):
    termo_texto = f"termo-teste-{uuid.uuid4().hex[:8]}"
    t = _termo(db, termo_texto)
    try:
        c = TestClient(app)
        r = c.post("/api/licitacoes/termos", json={"termo": termo_texto})
        assert r.status_code == 409
    finally:
        db.query(TermoBuscaLicitacao).filter(TermoBuscaLicitacao.id == t.id).delete(synchronize_session=False)
        db.commit()
