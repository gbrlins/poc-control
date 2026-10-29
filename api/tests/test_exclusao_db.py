"""Propriedade e exclusão permanente (ADR 4) contra um Postgres de verdade. Pula se não houver banco com a migração 0017:
rode dentro do container da api (`docker compose exec api python -m pytest tests/test_exclusao_db.py`)."""
import json
import logging
import pathlib
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

try:
    with SessionLocal() as _db:
        _db.execute(text("select 1 from exclusoes limit 1"))
except Exception:  # noqa: BLE001
    pytest.skip("sem Postgres com a migração 0017 aplicada", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app import exclusao as excl  # noqa: E402
from app.config import settings  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Anexo, Classificacao, Exclusao, FlagClassificacao, Item, Nota, OrigemClassificacao, Poc, PocDocumento, Procedimento,
    ResultadoCatalogo, ResultadoItem, Rfi, RfiItem, Sessao, StatusExtracao, User,
)

SEGREDO_DO_CLIENTE = "Banco Aurora S.A."


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def usuarios(db):
    marca = uuid.uuid4().hex[:8]
    out = {}
    for nome, admin in (("alice", False), ("bob", False), ("carol", True)):
        u = User(email=f"{nome}-{marca}@teste.example", password_hash="x", is_admin=admin)
        db.add(u)
        db.commit()
        db.refresh(u)
        db.expunge(u)
        out[nome] = u
    yield out
    # as linhas criadas pelos testes saem em cada teste; aqui só os usuários
    for u in out.values():
        db.query(Exclusao).filter(Exclusao.excluido_por_id == u.id).delete(synchronize_session=False)
        db.query(Rfi).filter(Rfi.criado_por_id == u.id).delete(synchronize_session=False)
        db.query(Poc).filter((Poc.responsavel_id == u.id) | (Poc.criado_por_id == u.id)).delete(synchronize_session=False)
        db.query(User).filter(User.id == u.id).delete(synchronize_session=False)
    db.commit()


def como(usuario):
    app.dependency_overrides[get_current_user] = lambda: usuario
    return TestClient(app)


@pytest.fixture(autouse=True)
def _limpa_overrides():
    yield
    app.dependency_overrides.clear()


def _pasta_poc(poc_id):
    return pathlib.Path(settings.uploads_dir) / "pocs" / str(poc_id)


def _poc(db, dono=None, titulo=None):
    poc = Poc(titulo=titulo or "PoC " + uuid.uuid4().hex[:6], cliente=SEGREDO_DO_CLIENTE, status_extracao=StatusExtracao.pronto,
              criado_por_id=dono.id if dono else None, responsavel_id=dono.id if dono else None)
    db.add(poc)
    db.commit()
    db.refresh(poc)
    return poc


def _poc_completa(db, dono):
    poc = _poc(db, dono)
    item = Item(poc_id=poc.id, codigo="1.1", titulo="Criar VM", fase=1, catalogo_id="cat-" + uuid.uuid4().hex[:6], resultado=ResultadoItem.pass_)
    db.add(item)
    db.flush()
    db.add(Nota(item_id=item.id, texto="nota"))
    sessao = Sessao(poc_id=poc.id, data=__import__("datetime").date.today())
    db.add(sessao)
    pasta = _pasta_poc(poc.id)
    (pasta / "anexos" / str(item.id)).mkdir(parents=True)
    (pasta / "plano.txt").write_text("doc")
    (pasta / "anexos" / str(item.id) / "log.txt").write_text("log")
    db.add(PocDocumento(poc_id=poc.id, nome_arquivo="plano.txt", caminho_arquivo=str(pasta / "plano.txt")))
    proc = Procedimento(titulo="Procedimento promovido", html_original="<h2>x</h2>", cliente_origem=SEGREDO_DO_CLIENTE)
    db.add(proc)
    db.flush()
    db.add(Anexo(item_id=item.id, nome_arquivo="log.txt", caminho_arquivo=str(pasta / "anexos" / str(item.id) / "log.txt"), procedimento_id=proc.id))
    from app.pocs.resultados import sincronizar_resultado_catalogo
    sincronizar_resultado_catalogo(db, item)
    db.commit()
    return poc, item, proc


def test_dono_exclui_e_o_que_deve_sobreviver_sobrevive(db, usuarios):
    alice = usuarios["alice"]
    poc, item, proc = _poc_completa(db, alice)
    poc_id, item_id, proc_id, cat, titulo = poc.id, item.id, proc.id, item.catalogo_id, poc.titulo
    c = como(alice)
    prev = c.get(f"/api/pocs/{poc_id}/exclusao").json()
    assert prev["podeExcluir"] is True and prev["contagens"] == {"itens": 1, "notas": 1, "anexos": 1, "sessoes": 1, "arquivos": 2}
    assert prev["procedimentosQuePermanecem"] == [{"id": str(proc_id), "titulo": "Procedimento promovido"}]
    assert c.request("DELETE", f"/api/pocs/{poc_id}", json={"confirmar": "errado"}).status_code == 400
    assert db.get(Poc, poc_id) is not None and _pasta_poc(poc_id).exists(), "título errado não apaga nada"
    r = c.request("DELETE", f"/api/pocs/{poc_id}", json={"confirmar": f"  {titulo}  "})
    assert r.status_code == 204
    db.expire_all()
    assert db.get(Poc, poc_id) is None and db.get(Item, item_id) is None
    assert db.query(Nota).filter(Nota.item_id == item_id).count() == 0 and db.query(Anexo).filter(Anexo.item_id == item_id).count() == 0
    assert not _pasta_poc(poc_id).exists(), "os arquivos também saem"
    assert db.get(Procedimento, proc_id) is not None, "o procedimento promovido fica para reutilização"
    linha = db.query(ResultadoCatalogo).filter(ResultadoCatalogo.catalogo_id == cat).one()
    assert linha.poc_id is None and linha.sucesso is True, "o histórico anônimo sobrevive"
    aud = db.query(Exclusao).filter(Exclusao.excluido_por_id == alice.id).one()
    assert aud.tipo == "poc" and aud.titulo == titulo and aud.contagens["itens"] == 1
    assert SEGREDO_DO_CLIENTE not in json.dumps([aud.titulo, aud.tipo, aud.contagens]), "a auditoria não guarda o cliente"
    db.query(ResultadoCatalogo).filter(ResultadoCatalogo.catalogo_id == cat).delete()
    db.query(Procedimento).filter(Procedimento.id == proc_id).delete()
    db.commit()


def test_so_o_dono_exclui_nem_admin_nem_sem_dono(db, usuarios):
    alice, bob, carol = usuarios["alice"], usuarios["bob"], usuarios["carol"]
    de_alice, sem_dono = _poc(db, alice), _poc(db, None)
    for quem in (bob, carol):
        r = como(quem).request("DELETE", f"/api/pocs/{de_alice.id}", json={"confirmar": de_alice.titulo})
        assert r.status_code == 403, f"{quem.email} (admin={quem.is_admin}) não pode excluir a PoC de outra pessoa"
    r = como(alice).request("DELETE", f"/api/pocs/{sem_dono.id}", json={"confirmar": sem_dono.titulo})
    assert r.status_code == 403 and "assuma" in r.json()["detail"], "sem dono: ninguém exclui até assumir"
    assert como(carol).request("DELETE", f"/api/pocs/{sem_dono.id}", json={"confirmar": sem_dono.titulo}).status_code == 403
    assert db.get(Poc, de_alice.id) is not None and db.get(Poc, sem_dono.id) is not None
    assert como(alice).request("DELETE", f"/api/pocs/{uuid.uuid4()}", json={"confirmar": "x"}).status_code == 404
    assert como(alice).request("DELETE", f"/api/pocs/{de_alice.id}", json={}).status_code == 422
    db.query(Poc).filter(Poc.id == sem_dono.id).delete()
    db.commit()


def test_assumir_transferir_e_reatribuir(db, usuarios):
    alice, bob, carol = usuarios["alice"], usuarios["bob"], usuarios["carol"]
    poc = _poc(db, None)
    url = f"/api/pocs/{poc.id}/responsavel"
    assert como(bob).put(url, json={"responsavel_id": str(alice.id)}).status_code == 403, "assumir só vale para si mesmo"
    assert como(bob).put(url, json={"responsavel_id": str(bob.id)}).status_code == 200, "linha sem dono: qualquer engenheiro assume"
    db.expire_all()
    assert db.get(Poc, poc.id).responsavel_id == bob.id
    assert como(alice).put(url, json={"responsavel_id": str(alice.id)}).status_code == 403, "com dono, não se assume"
    assert como(bob).put(url, json={"responsavel_id": str(alice.id)}).status_code == 200, "o dono transfere"
    assert como(bob).put(url, json={"responsavel_id": str(bob.id)}).status_code == 403, "quem transferiu não é mais dono"
    assert como(carol).put(url, json={"responsavel_id": str(bob.id)}).status_code == 200, "o administrador reatribui"
    assert como(carol).request("DELETE", f"/api/pocs/{poc.id}", json={"confirmar": poc.titulo}).status_code == 403, "mas não exclui"
    assert como(bob).put(url, json={"responsavel_id": str(uuid.uuid4())}).status_code == 404
    db.query(Poc).filter(Poc.id == poc.id).delete()
    db.commit()


def test_rfi_mesmas_regras(db, usuarios):
    alice, bob = usuarios["alice"], usuarios["bob"]
    rfi = Rfi(titulo="RFI " + uuid.uuid4().hex[:6], orgao=SEGREDO_DO_CLIENTE, status_extracao=StatusExtracao.pronto, nome_arquivo="e.pdf",
              caminho_arquivo="", criado_por_id=alice.id, responsavel_id=alice.id)
    db.add(rfi)
    db.commit()
    db.add(RfiItem(rfi_id=rfi.id, codigo="1", descricao="req"))
    pasta = pathlib.Path(settings.uploads_dir) / "rfis" / str(rfi.id)
    pasta.mkdir(parents=True)
    (pasta / "edital.pdf").write_text("x")
    db.commit()
    rid = rfi.id
    assert como(bob).request("DELETE", f"/api/rfis/{rid}", json={"confirmar": rfi.titulo}).status_code == 403
    assert como(alice).get(f"/api/rfis/{rid}/exclusao").json()["contagens"] == {"itens": 1, "arquivos": 1}
    assert como(alice).request("DELETE", f"/api/rfis/{rid}", json={"confirmar": "x"}).status_code == 400
    assert como(alice).request("DELETE", f"/api/rfis/{rid}", json={"confirmar": rfi.titulo}).status_code == 204
    db.expire_all()
    assert db.get(Rfi, rid) is None and db.query(RfiItem).filter(RfiItem.rfi_id == rid).count() == 0 and not pasta.exists()
    aud = db.query(Exclusao).filter(Exclusao.excluido_por_id == alice.id, Exclusao.tipo == "rfi").one()
    assert SEGREDO_DO_CLIENTE not in json.dumps([aud.titulo, aud.contagens])


def test_falha_ao_apagar_arquivo_nao_desfaz_a_exclusao(db, usuarios, monkeypatch, caplog):
    alice = usuarios["alice"]
    poc, _, proc = _poc_completa(db, alice)
    poc_id, proc_id = poc.id, proc.id
    pasta = _pasta_poc(poc_id)

    def quebra(_):
        raise PermissionError("sem permissão")

    monkeypatch.setattr(excl.shutil, "rmtree", quebra)
    with caplog.at_level(logging.ERROR):
        assert como(alice).request("DELETE", f"/api/pocs/{poc_id}", json={"confirmar": poc.titulo}).status_code == 204
    db.expire_all()
    assert db.get(Poc, poc_id) is None, "as linhas já saíram"
    assert pasta.exists() and "Não consegui apagar" in caplog.text, "a sobra fica registrada em log"
    monkeypatch.undo()
    from scripts.limpar_orfaos import orfaos
    assert pasta in orfaos(db), "e o script de varredura a encontra"
    import shutil
    shutil.rmtree(pasta)
    db.query(Procedimento).filter(Procedimento.id == proc_id).delete()
    db.query(ResultadoCatalogo).filter(ResultadoCatalogo.poc_id.is_(None), ResultadoCatalogo.catalogo_id.like("cat-%")).delete(synchronize_session=False)
    db.commit()


def test_caminho_guardado_no_banco_nunca_e_seguido(db, usuarios, tmp_path):
    alice = usuarios["alice"]
    fora = tmp_path / "importante.txt"
    fora.write_text("não apague")
    poc = _poc(db, alice)
    db.add(PocDocumento(poc_id=poc.id, nome_arquivo="x", caminho_arquivo=str(fora)))
    db.commit()
    assert como(alice).request("DELETE", f"/api/pocs/{poc.id}", json={"confirmar": poc.titulo}).status_code == 204
    assert fora.read_text() == "não apague", "só a pasta montada a partir do id é removida"


def test_varredura_de_orfaos_so_toca_pastas_com_uuid_sem_registro(db, usuarios):
    from scripts.limpar_orfaos import orfaos
    alice = usuarios["alice"]
    existente = _poc(db, alice)
    raiz = pathlib.Path(settings.uploads_dir) / "pocs"
    (raiz / str(existente.id)).mkdir(parents=True, exist_ok=True)
    orfa, estranha = raiz / str(uuid.uuid4()), raiz / "nao-e-uuid"
    orfa.mkdir(parents=True)
    estranha.mkdir(parents=True, exist_ok=True)
    try:
        achadas = orfaos(db)
        assert orfa in achadas and (raiz / str(existente.id)) not in achadas and estranha not in achadas
    finally:
        import shutil
        for p in (orfa, estranha, raiz / str(existente.id)):
            shutil.rmtree(p, ignore_errors=True)
        db.query(Poc).filter(Poc.id == existente.id).delete()
        db.commit()


def test_quem_cria_uma_poc_vira_o_dono(db, usuarios):
    alice = usuarios["alice"]
    planner = {"schema": 2, "planner": {"project": {"projectName": "PoC dono " + uuid.uuid4().hex[:6], "clientOrganization": "C"}},
               "tests": [{"id": "t1", "catalogId": "cat-dono", "product": "virtualization", "productName": "SUSE Virtualization",
                          "title": "Criar VM", "expected": "ok", "priority": "must", "fit": "native", "led": "suse", "result": "pending", "owner": ""}]}
    r = como(alice).post("/api/pocs/importar-planejador", data={"texto": json.dumps(planner)})
    assert r.status_code == 201
    pid = uuid.UUID(r.json()["id"])
    db.expire_all()
    poc = db.get(Poc, pid)
    assert poc.criado_por_id == alice.id and poc.responsavel_id == alice.id and r.json()["responsavel_id"] == str(alice.id)
    como(alice).request("DELETE", f"/api/pocs/{pid}", json={"confirmar": poc.titulo})
    db.query(ResultadoCatalogo).filter(ResultadoCatalogo.catalogo_id == "cat-dono").delete()
    db.commit()


def test_procedimento_mesmas_regras_e_vinculos_viram_null(db, usuarios):
    alice, bob = usuarios["alice"], usuarios["bob"]
    proc = Procedimento(
        titulo="Procedimento " + uuid.uuid4().hex[:6],
        html_original="<h2>x</h2>",
        cliente_origem=SEGREDO_DO_CLIENTE,
        categorias=["K8S"],
        criado_por_id=alice.id,
        responsavel_id=alice.id,
    )
    db.add(proc)
    db.commit()

    # PoC e RFI citando o procedimento -- excluir não deve quebrar nenhum dos dois, só soltar o vínculo (SET NULL).
    poc = _poc(db, alice)
    item = Item(poc_id=poc.id, codigo="1.1", titulo="Criar VM", fase=1)
    db.add(item)
    db.flush()
    db.add(Classificacao(item_id=item.id, flag=FlagClassificacao.verde, origem=OrigemClassificacao.auto, procedimento_id=proc.id))
    rfi = Rfi(titulo="RFI " + uuid.uuid4().hex[:6], orgao=SEGREDO_DO_CLIENTE, status_extracao=StatusExtracao.pronto,
              nome_arquivo="e.pdf", caminho_arquivo="", criado_por_id=alice.id, responsavel_id=alice.id)
    db.add(rfi)
    db.commit()
    rfi_item = RfiItem(rfi_id=rfi.id, codigo="1", descricao="req", procedimento_id=proc.id)
    db.add(rfi_item)
    db.commit()
    proc_id, item_id, rfi_item_id = proc.id, item.id, rfi_item.id

    # como() sobrescreve app.dependency_overrides (estado global do app) -- chamar de novo pra cada request,
    # nunca reaproveitar um client guardado numa variável entre chamadas de usuários diferentes (ver test_rfi_mesmas_regras).
    assert como(alice).request("DELETE", f"/api/procedimentos/{proc_id}", json={"confirmar": "errado"}).status_code == 400
    assert como(bob).request("DELETE", f"/api/procedimentos/{proc_id}", json={"confirmar": proc.titulo}).status_code == 403

    prev = como(alice).get(f"/api/procedimentos/{proc_id}/exclusao").json()
    assert prev["podeExcluir"] is True and prev["contagens"]["vinculos"] >= 1
    vinculos = {v["id"] for v in prev["vinculosQuePerdemProcedimento"]}
    assert str(poc.id) in vinculos and str(rfi.id) in vinculos

    assert como(alice).request("DELETE", f"/api/procedimentos/{proc_id}", json={"confirmar": proc.titulo}).status_code == 204
    db.expire_all()
    assert db.get(Procedimento, proc_id) is None
    assert db.get(Item, item_id) is not None, "a PoC continua existindo"
    assert db.query(Classificacao).filter(Classificacao.item_id == item_id).one().procedimento_id is None, "o vínculo da classificação vira NULL"
    assert db.query(RfiItem).filter(RfiItem.id == rfi_item_id).one().procedimento_id is None, "o vínculo do RFI vira NULL"

    aud = db.query(Exclusao).filter(Exclusao.excluido_por_id == alice.id, Exclusao.tipo == "procedimento").one()
    assert SEGREDO_DO_CLIENTE not in json.dumps([aud.titulo, aud.contagens])
    db.query(Poc).filter(Poc.id == poc.id).delete()
    db.query(Rfi).filter(Rfi.id == rfi.id).delete()
    db.commit()


def test_procedimento_assumir_e_transferir(db, usuarios):
    alice, bob = usuarios["alice"], usuarios["bob"]
    proc = Procedimento(titulo="Procedimento " + uuid.uuid4().hex[:6], html_original="<h2>x</h2>")
    db.add(proc)
    db.commit()
    url = f"/api/procedimentos/{proc.id}/responsavel"
    assert como(bob).put(url, json={"responsavel_id": str(alice.id)}).status_code == 403
    assert como(bob).put(url, json={"responsavel_id": str(bob.id)}).status_code == 200
    db.expire_all()
    assert db.get(Procedimento, proc.id).responsavel_id == bob.id
    db.query(Procedimento).filter(Procedimento.id == proc.id).delete()
    db.commit()


def test_detalhe_mostra_o_mesmo_dono_que_a_listagem(db, usuarios):
    """Bug real: o detalhe (GET /{id}) montava a resposta campo a campo e esquecia `responsavel_id`, sempre devolvendo
    null mesmo com dono -- a listagem (que usa `_list_item` nos dois casos) já devolvia o valor certo."""
    alice = usuarios["alice"]
    poc = _poc(db, alice)
    rfi = Rfi(titulo="RFI " + uuid.uuid4().hex[:6], orgao=SEGREDO_DO_CLIENTE, status_extracao=StatusExtracao.pronto,
              nome_arquivo="e.pdf", caminho_arquivo="", criado_por_id=alice.id, responsavel_id=alice.id)
    db.add(rfi)
    db.commit()
    c = como(alice)
    assert c.get(f"/api/pocs/{poc.id}").json()["responsavel_id"] == str(alice.id)
    assert c.get(f"/api/rfis/{rfi.id}").json()["responsavel_id"] == str(alice.id)
    db.query(Poc).filter(Poc.id == poc.id).delete()
    db.query(Rfi).filter(Rfi.id == rfi.id).delete()
    db.commit()
