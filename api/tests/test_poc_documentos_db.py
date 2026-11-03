"""PoC com vários documentos: criar, anexar, remover, reextrair e cancelar (Postgres, dentro do
container da api: `docker compose exec api sh -c 'pip install -q pytest && python -m pytest
tests/test_poc_documentos_db.py'`). Mesmo desenho de test_rfi_documentos_db.py. Gemini é simulado:
extrair_itens_poc devolve fases/itens derivados do texto do documento; classificar_pendentes é
desligado (cobre só a fila de extração, não a classificação)."""
import io
import pathlib
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

try:
    with SessionLocal() as _db:
        _db.execute(text("select documento_id from itens limit 1"))
except Exception:  # noqa: BLE001
    pytest.skip("sem Postgres com a migração 0025 aplicada", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app.deps import get_current_user  # noqa: E402
from app.gemini import ExtracaoPoc, FaseExtraida, ItemExtraido  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Item, Poc, StatusExtracao, User  # noqa: E402
from app.pocs import tasks  # noqa: E402


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


@pytest.fixture(autouse=True)
def gemini_falso(monkeypatch):
    """Cada linha do documento vira uma fase + um item dentro dela (fase "1" sempre, dentro de uma
    só chamada) -- o que importa pro teste de deslocamento é que todo documento gera fases
    numeradas a partir de 1, pra provar que o 2º documento não pisa no 1º."""

    def extrair(pdf_bytes=None, texto=None, api_key=None, model=None):
        if texto and "QUEBRA" in texto:
            raise RuntimeError("falha simulada")
        linhas = [l for l in (texto or "").splitlines() if l.strip()]
        return ExtracaoPoc(
            titulo_sugerido="PoC X",
            cliente_sugerido="Cliente Y",
            fases=[FaseExtraida(numero=1, titulo="Fase única", descricao="")],
            itens=[
                ItemExtraido(codigo=l.split()[0], titulo=l, descricao=l, criterio_aceite="ok", categoria="K8s", categoria_codigo="K8S", fase=1)
                for l in linhas
            ],
            prerequisitos=[],
        )

    monkeypatch.setattr(tasks, "extrair_itens_poc", extrair)
    monkeypatch.setattr(tasks, "classificar_pendentes", lambda *a, **k: None)
    return extrair


def _arq(nome, conteudo):
    return (nome, io.BytesIO(conteudo.encode()), "text/plain")


def _criar(c, *docs, texto=None, titulo="T", cliente="C"):
    data = {"titulo": titulo, "cliente": cliente}
    if texto:
        data["texto"] = texto
    r = c.post("/api/pocs", data=data, files=[("arquivos", _arq(n, t)) for n, t in docs])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_criar_com_varios_documentos_desloca_as_fases(usuario):
    c = TestClient(app)
    pid = _criar(c, ("a.txt", "1.1 cluster k8s\n1.2 backup"), ("b.txt", "2.1 storage"))
    d = c.get(f"/api/pocs/{pid}").json()
    assert d["status_extracao"] == "pronto"
    assert sorted(x["nome_arquivo"] for x in d["documentos"]) == ["a.txt", "b.txt"]
    assert len(d["itens"]) == 3
    # cada documento gerou "fase 1" na chamada ao Gemini -- o 2º precisa vir deslocado pra "fase 2"
    # na PoC final, senão colidiria com a fase do 1º documento.
    assert sorted(f["numero"] for f in d["fases"]) == [1, 2]
    fase_de = {f["numero"]: f["titulo"] for f in d["fases"]}
    itens_por_doc = {x["id"]: [] for x in d["documentos"]}
    for item in d["itens"]:
        itens_por_doc[item["documento_id"]].append(item)
    doc_a = next(x for x in d["documentos"] if x["nome_arquivo"] == "a.txt")
    doc_b = next(x for x in d["documentos"] if x["nome_arquivo"] == "b.txt")
    assert {i["fase"] for i in itens_por_doc[doc_a["id"]]} == {1}
    assert {i["fase"] for i in itens_por_doc[doc_b["id"]]} == {2}
    # ordem continua entre documentos, não reinicia em 0 no 2º
    ordens = sorted(i["ordem"] for i in d["itens"])
    assert ordens == list(range(len(ordens)))


def test_arquivo_invalido_nao_cria_nada(usuario, db):
    c = TestClient(app)
    antes = db.query(Poc).filter(Poc.criado_por_id == usuario.id).count()
    r = c.post(
        "/api/pocs",
        data={"titulo": "T", "cliente": "C"},
        files=[("arquivos", _arq("ok.txt", "1 x")), ("arquivos", ("vazio.txt", io.BytesIO(b""), "text/plain"))],
    )
    assert r.status_code == 400
    assert db.query(Poc).filter(Poc.criado_por_id == usuario.id).count() == antes


def test_anexar_extrai_so_o_novo_e_continua_a_ordem(usuario, db):
    c = TestClient(app)
    pid = _criar(c, ("a.txt", "1.1 cluster"))
    r = c.post(f"/api/pocs/{pid}/documentos", files=[("arquivos", _arq("b.txt", "2.1 storage"))])
    assert r.status_code == 202, r.text
    d = c.get(f"/api/pocs/{pid}").json()
    assert len(d["documentos"]) == 2 and len(d["itens"]) == 2
    assert sorted(f["numero"] for f in d["fases"]) == [1, 2]
    assert sorted(i["ordem"] for i in d["itens"]) == [0, 1]


def test_remover_documento_leva_os_itens_e_o_arquivo(usuario, db):
    c = TestClient(app)
    pid = _criar(c, ("a.txt", "1.1 x"), ("b.txt", "2.1 y\n2.2 z"))
    d = c.get(f"/api/pocs/{pid}").json()
    b = next(x for x in d["documentos"] if x["nome_arquivo"] == "b.txt")
    assert b["total_itens"] == 2
    caminho = pathlib.Path(db.query(Poc).get(uuid.UUID(pid)).documentos[1].caminho_arquivo)
    assert c.delete(f"/api/pocs/{pid}/documentos/{b['id']}").status_code == 204
    d = c.get(f"/api/pocs/{pid}").json()
    assert [x["nome_arquivo"] for x in d["documentos"]] == ["a.txt"] and len(d["itens"]) == 1
    assert not caminho.exists()
    assert c.delete(f"/api/pocs/{pid}/documentos/{b['id']}").status_code == 404


def test_409_enquanto_processa(usuario, db):
    c = TestClient(app)
    pid = _criar(c, ("a.txt", "1.1 x"))
    poc = db.get(Poc, uuid.UUID(pid))
    poc.status_extracao = StatusExtracao.extraindo
    db.commit()
    assert c.post(f"/api/pocs/{pid}/documentos", files=[("arquivos", _arq("b.txt", "2 y"))]).status_code == 409
    doc = c.get(f"/api/pocs/{pid}").json()["documentos"][0]["id"]
    assert c.delete(f"/api/pocs/{pid}/documentos/{doc}").status_code == 409
    assert c.post(f"/api/pocs/{pid}/cancelar").status_code == 202


def test_falha_parcial_vira_aviso_e_falha_total_vira_erro(usuario):
    c = TestClient(app)
    pid = _criar(c, ("ok.txt", "1.1 x"), ("ruim.txt", "QUEBRA"))
    d = c.get(f"/api/pocs/{pid}").json()
    assert d["status_extracao"] == "pronto" and "ruim.txt" in d["erro_extracao"] and len(d["itens"]) == 1

    pid2 = _criar(c, ("ruim.txt", "QUEBRA"))
    d2 = c.get(f"/api/pocs/{pid2}").json()
    assert d2["status_extracao"] == "erro" and len(d2["itens"]) == 0


def test_reextrair_reprocessa_todos_os_documentos(usuario, db):
    c = TestClient(app)
    pid = _criar(c, ("ruim.txt", "QUEBRA"))
    assert c.get(f"/api/pocs/{pid}").json()["status_extracao"] == "erro"

    # troca o conteúdo do arquivo em disco (como se o Gemini tivesse voltado a funcionar pro
    # mesmo texto) e tenta de novo -- reextrair relê do disco, não precisa reenviar nada.
    poc = db.get(Poc, uuid.UUID(pid))
    caminho = pathlib.Path(poc.documentos[0].caminho_arquivo)
    caminho.write_text("1.1 agora funciona", encoding="utf-8")

    assert c.post(f"/api/pocs/{pid}/reextrair").status_code == 202
    d = c.get(f"/api/pocs/{pid}").json()
    assert d["status_extracao"] == "pronto" and len(d["itens"]) == 1


def test_cancelar_sem_processamento_da_409(usuario):
    c = TestClient(app)
    pid = _criar(c, ("a.txt", "1.1 x"))
    assert c.post(f"/api/pocs/{pid}/cancelar").status_code == 409


def test_cancelar_durante_o_processamento_para_entre_documentos(usuario, monkeypatch):
    # carregar_documento (não extrair_itens_poc) recebe o PocDocumento de verdade, com poc_id --
    # é o gancho certo pra simular "apertar Interromper" sem precisar do id da PoC antes dela
    # existir (a extração do 1º documento roda dentro do próprio POST que cria a PoC).
    c = TestClient(app)
    visto: list[str] = []
    original_carregar = tasks.carregar_documento

    def carregar_e_cancela(doc):
        if not visto:
            assert c.post(f"/api/pocs/{doc.poc_id}/cancelar").status_code == 202
        visto.append(doc.nome_arquivo)
        return original_carregar(doc)

    monkeypatch.setattr(tasks, "carregar_documento", carregar_e_cancela)
    monkeypatch.setattr(tasks, "classificar_pendentes", lambda *a, **k: None)
    pid = _criar(c, ("a.txt", "1.1 x"), ("b.txt", "2.1 y"))
    d = c.get(f"/api/pocs/{pid}").json()
    assert visto == ["a.txt"], "o 2º documento nunca chega a ser lido"
    assert d["status_extracao"] == "pronto" and d["cancelamento_solicitado"] is False
    assert [x["nome_arquivo"] for x in d["documentos"]] == ["a.txt", "b.txt"], "o documento continua anexado"
    assert len(d["itens"]) == 1
