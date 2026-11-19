"""RFI com vários documentos: criar, anexar, remover e reavaliar (Postgres, dentro do container da api:
`docker compose exec api sh -c 'pip install -q pytest && python -m pytest tests/test_rfi_documentos_db.py'`).
Gemini é simulado: extrair_itens_rfi devolve itens derivados do texto do documento."""
import io
import pathlib
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

try:
    with SessionLocal() as _db:
        _db.execute(text("select 1 from rfi_documentos limit 1"))
except Exception:  # noqa: BLE001
    pytest.skip("sem Postgres com a migração 0023 aplicada", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app.deps import get_current_user  # noqa: E402
from app.gemini import ExtracaoRfi, ItemRfiExtraido  # noqa: E402
from app.main import app  # noqa: E402
from app.models import OrigemClassificacao, Rfi, RfiItem, StatusExtracao, User, VeredictoRfi  # noqa: E402
from app.rfi import tasks  # noqa: E402


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def usuario(db):
    u = User(email=f"rfi-{uuid.uuid4().hex[:8]}@teste.example", password_hash="x", is_admin=False)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.expunge(u)
    app.dependency_overrides[get_current_user] = lambda: u
    yield u
    app.dependency_overrides.clear()
    db.query(Rfi).filter(Rfi.criado_por_id == u.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == u.id).delete(synchronize_session=False)
    db.commit()


@pytest.fixture(autouse=True)
def gemini_falso(monkeypatch):
    avaliados: list[str] = []

    def extrair(pdf_bytes=None, texto=None, api_key=None, model=None, lang=None):
        if texto and "QUEBRA" in texto:
            raise RuntimeError("falha simulada")
        linhas = [l for l in (texto or "").splitlines() if l.strip()]
        return ExtracaoRfi(
            titulo_sugerido="Edital X",
            orgao_sugerido="Órgão Y",
            numero_processo_sugerido="1/2026",
            itens=[ItemRfiExtraido(codigo=l.split()[0], categoria="K8s", categoria_codigo="K8S", descricao=l) for l in linhas],
        )

    def avaliar(db, item, api_key=None, model=None, lang=None):
        avaliados.append(item.codigo)
        item.veredito = VeredictoRfi.atende
        item.origem = OrigemClassificacao.auto
        db.commit()
        return item

    monkeypatch.setattr(tasks, "extrair_itens_rfi", extrair)
    monkeypatch.setattr(tasks, "avaliar_item_rfi", avaliar)
    return avaliados


def _arq(nome, conteudo):
    return (nome, io.BytesIO(conteudo.encode()), "text/plain")


def _criar(c, *docs, texto=None):
    data = {"texto": texto} if texto else {}
    r = c.post("/api/rfis", data=data, files=[("arquivos", _arq(n, t)) for n, t in docs])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_criar_com_varios_documentos_mantem_itens_repetidos(usuario, gemini_falso):
    c = TestClient(app)
    rid = _criar(c, ("a.txt", "1.1 cluster k8s\n1.2 backup"), ("b.txt", "1.1 cluster k8s"), texto="9.9 colado")
    d = c.get(f"/api/rfis/{rid}").json()
    assert d["status_extracao"] == "pronto"
    assert sorted(x["nome_arquivo"] for x in d["documentos"]) == ["a.txt", "b.txt", "texto-colado.txt"]
    assert len(d["itens"]) == 4  # os dois "1.1" ficam (decisão: manter duplicados)
    assert {x["documento_id"] for x in d["itens"]} == {x["id"] for x in d["documentos"]}
    assert d["total_itens"] == d["itens_avaliados"] == 4
    assert d["titulo"] == "Edital X"
    assert d["processamento_iniciado_em"]  # alimenta o cronômetro do front


def test_arquivo_invalido_nao_cria_nada(usuario, db):
    c = TestClient(app)
    antes = db.query(Rfi).filter(Rfi.criado_por_id == usuario.id).count()
    r = c.post("/api/rfis", files=[("arquivos", _arq("ok.txt", "1 x")), ("arquivos", ("vazio.txt", io.BytesIO(b""), "text/plain"))])
    assert r.status_code == 400
    assert db.query(Rfi).filter(Rfi.criado_por_id == usuario.id).count() == antes


def test_anexar_extrai_so_o_novo_e_preserva_manual(usuario, db, gemini_falso):
    c = TestClient(app)
    rid = _criar(c, ("a.txt", "1.1 cluster"))
    item = db.query(RfiItem).filter(RfiItem.rfi_id == rid).one()
    item.veredito, item.origem = VeredictoRfi.nao_atende, OrigemClassificacao.manual
    db.commit()
    gemini_falso.clear()

    r = c.post(f"/api/rfis/{rid}/documentos", files=[("arquivos", _arq("b.txt", "2.1 storage"))])
    assert r.status_code == 202, r.text
    d = c.get(f"/api/rfis/{rid}").json()
    assert len(d["documentos"]) == 2 and len(d["itens"]) == 2
    assert gemini_falso == ["2.1"]  # só o item novo foi avaliado
    db.expire_all()
    assert db.get(RfiItem, item.id).veredito == VeredictoRfi.nao_atende


def test_remover_documento_leva_os_itens_e_o_arquivo(usuario, db):
    c = TestClient(app)
    rid = _criar(c, ("a.txt", "1.1 x"), ("b.txt", "2.1 y\n2.2 z"))
    d = c.get(f"/api/rfis/{rid}").json()
    b = next(x for x in d["documentos"] if x["nome_arquivo"] == "b.txt")
    assert b["total_itens"] == 2
    caminho = pathlib.Path(db.query(Rfi).get(uuid.UUID(rid)).documentos[1].caminho_arquivo)
    assert c.delete(f"/api/rfis/{rid}/documentos/{b['id']}").status_code == 204
    d = c.get(f"/api/rfis/{rid}").json()
    assert [x["nome_arquivo"] for x in d["documentos"]] == ["a.txt"] and len(d["itens"]) == 1
    assert not caminho.exists()
    assert c.delete(f"/api/rfis/{rid}/documentos/{b['id']}").status_code == 404


def test_baixar_documento_devolve_o_arquivo_original_e_nao_sai_da_pasta(usuario, db):
    c = TestClient(app)
    rid = _criar(c, ("a.txt", "1.1 conteudo original"))
    doc = c.get(f"/api/rfis/{rid}").json()["documentos"][0]
    r = c.get(f"/api/rfis/{rid}/documentos/{doc['id']}/download")
    assert r.status_code == 200 and r.content == b"1.1 conteudo original"
    assert "a.txt" in r.headers["content-disposition"]
    # caminho adulterado no banco (fora da pasta deste RFI) não é servido
    registro = db.query(Rfi).get(uuid.UUID(rid)).documentos[0]
    registro.caminho_arquivo = "/etc/hostname"
    db.commit()
    assert c.get(f"/api/rfis/{rid}/documentos/{doc['id']}/download").status_code == 404
    assert c.get(f"/api/rfis/{rid}/documentos/{uuid.uuid4()}/download").status_code == 404


def test_reavaliar_pula_manuais_por_padrao(usuario, db, gemini_falso):
    c = TestClient(app)
    rid = _criar(c, ("a.txt", "1.1 x\n1.2 y"))
    manual = db.query(RfiItem).filter(RfiItem.rfi_id == rid, RfiItem.codigo == "1.1").one()
    manual.origem = OrigemClassificacao.manual
    db.commit()
    gemini_falso.clear()
    assert c.post(f"/api/rfis/{rid}/reavaliar").status_code == 202
    assert gemini_falso == ["1.2"]
    gemini_falso.clear()
    assert c.post(f"/api/rfis/{rid}/reavaliar?incluir_manuais=true").status_code == 202
    assert sorted(gemini_falso) == ["1.1", "1.2"]
    assert c.get(f"/api/rfis/{rid}").json()["status_extracao"] == "pronto"


def test_409_enquanto_processa(usuario, db):
    c = TestClient(app)
    rid = _criar(c, ("a.txt", "1.1 x"))
    rfi = db.get(Rfi, uuid.UUID(rid))
    rfi.status_extracao = StatusExtracao.extraindo
    db.commit()
    assert c.post(f"/api/rfis/{rid}/reavaliar").status_code == 409
    assert c.post(f"/api/rfis/{rid}/documentos", files=[("arquivos", _arq("b.txt", "2 y"))]).status_code == 409
    doc = c.get(f"/api/rfis/{rid}").json()["documentos"][0]["id"]
    assert c.delete(f"/api/rfis/{rid}/documentos/{doc}").status_code == 409


def test_falha_parcial_vira_aviso_e_falha_total_vira_erro(usuario):
    c = TestClient(app)
    rid = _criar(c, ("ok.txt", "1.1 x"), ("ruim.txt", "QUEBRA"))
    d = c.get(f"/api/rfis/{rid}").json()
    assert d["status_extracao"] == "pronto" and "ruim.txt" in d["erro_extracao"] and len(d["itens"]) == 1
    rid2 = _criar(c, ("ruim.txt", "QUEBRA"))
    d2 = c.get(f"/api/rfis/{rid2}").json()
    assert d2["status_extracao"] == "erro" and d2["titulo"] == "Untitled RFI"


def test_cancelar_marca_itens_pendentes_e_libera_o_rfi(usuario, db, monkeypatch):
    c = TestClient(app)
    visto = []

    def avaliar_e_cancela(db_, item, api_key=None, model=None, lang=None):
        # o usuário aperta "Interromper" durante o primeiro item
        if not visto:
            assert c.post(f"/api/rfis/{item.rfi_id}/cancelar").status_code == 202
        visto.append(item.codigo)
        item.veredito = VeredictoRfi.atende
        item.origem = OrigemClassificacao.auto
        db_.commit()
        return item

    monkeypatch.setattr(tasks, "avaliar_item_rfi", avaliar_e_cancela)
    rid = _criar(c, ("a.txt", "1.1 x\n1.2 y\n1.3 z"))
    d = c.get(f"/api/rfis/{rid}").json()
    assert visto == ["1.1"]
    assert d["status_extracao"] == "pronto" and d["progresso"] is None and d["cancelamento_solicitado"] is False
    por_codigo = {i["codigo"]: i for i in d["itens"]}
    assert por_codigo["1.1"]["veredito"] == "atende"
    assert por_codigo["1.2"]["veredito"] == "sem_evidencia" and "stopped" in por_codigo["1.2"]["justificativa"]
    assert d["itens_avaliados"] == d["total_itens"] == 3  # nada fica "processando" pra sempre


def test_cancelar_sem_processamento_da_409(usuario):
    c = TestClient(app)
    rid = _criar(c, ("a.txt", "1.1 x"))
    assert c.post(f"/api/rfis/{rid}/cancelar").status_code == 409


def test_resolver_fontes_troca_o_redirecionamento_pelo_endereco_real(usuario, db, monkeypatch):
    from app.rfi import router as rfi_router

    c = TestClient(app)
    rid = _criar(c, ("a.txt", "1.1 x"))
    item = db.query(RfiItem).filter(RfiItem.rfi_id == rid).one()
    redir = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
    item.fontes = [{"titulo": "suse.com", "url": redir}, {"titulo": "outro", "url": "https://exemplo.com/x"}]
    db.commit()
    monkeypatch.setattr(rfi_router, "resolver_urls", lambda urls: ["https://documentation.suse.com/real" for _ in urls])
    assert c.post(f"/api/rfis/{rid}/fontes/resolver").json() == {"atualizados": 1}
    db.expire_all()
    fontes = db.query(RfiItem).filter(RfiItem.rfi_id == rid).one().fontes
    assert fontes[0] == {"titulo": "suse.com", "url": "https://documentation.suse.com/real"}
    assert fontes[1]["url"] == "https://exemplo.com/x"
    assert c.post(f"/api/rfis/{rid}/fontes/resolver").json() == {"atualizados": 0}   # idempotente
