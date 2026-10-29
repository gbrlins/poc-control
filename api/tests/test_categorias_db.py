"""Busca por afinidade de categoria (_buscar_candidatos) contra um Postgres de verdade. Pula se não houver banco com a
migração 0018 aplicada: rode dentro do container da api (`docker compose exec api python -m pytest tests/test_categorias_db.py`).

Usa vetores arbitrários (não chama o Gemini) -- o que importa aqui é o filtro por `categorias` e o fallback, não a
qualidade semântica da busca."""
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.gemini import EMBEDDING_DIM

try:
    with SessionLocal() as _db:
        _db.execute(text("select categorias from procedimentos limit 1"))
except Exception:  # noqa: BLE001
    pytest.skip("sem Postgres com a migração 0018 aplicada", allow_module_level=True)

from app.classificacao.service import _buscar_candidatos  # noqa: E402
from app.models import Procedimento, ProcedimentoChunk, StatusProcedimento  # noqa: E402


def _vetor(seed: int) -> list[float]:
    valores = [((seed * 97 + i) % 1000) / 1000 for i in range(EMBEDDING_DIM)]
    norma = sum(v * v for v in valores) ** 0.5
    return [v / norma for v in valores]


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def _procedimento(db, *, categorias, seed, status=StatusProcedimento.validado):
    proc = Procedimento(
        titulo="Procedimento " + uuid.uuid4().hex[:6],
        html_original="<h2>x</h2>",
        categorias=categorias,
        status=status,
    )
    db.add(proc)
    db.flush()
    chunk = ProcedimentoChunk(
        procedimento_id=proc.id,
        heading_level=2,
        heading_title="Seção",
        parent_heading_title=None,
        order_index=0,
        content_text="conteúdo",
        embedding=_vetor(seed),
    )
    db.add(chunk)
    db.commit()
    return proc


def test_restringe_a_categoria_quando_ha_procedimento_marcado(db):
    # limit alto de propósito: o que este teste verifica é o FILTRO por categoria (nunca deixar passar outra
    # categoria), não a posição no ranking -- isso evita que o teste seja afetado por outros procedimentos já no banco.
    de_storage = _procedimento(db, categorias=["STR"], seed=1)
    de_k8s = _procedimento(db, categorias=["K8S"], seed=2)
    try:
        achados = _buscar_candidatos(db, _vetor(1), categorias_afinidade=["STR"], limit=1000)
        ids = {c.procedimento_id for c in achados}
        assert de_storage.id in ids and de_k8s.id not in ids, "a busca restrita não deve trazer procedimento de outra categoria"
    finally:
        db.query(Procedimento).filter(Procedimento.id.in_([de_storage.id, de_k8s.id])).delete(synchronize_session=False)
        db.commit()


def test_cai_pro_fallback_quando_categoria_nao_tem_nenhum_procedimento(db):
    existe_edge = db.query(Procedimento).filter(Procedimento.categorias.overlap(["EDGE"])).first()
    if existe_edge is not None:
        pytest.skip("já existe procedimento EDGE no banco -- este teste exige a categoria vazia pra testar o fallback")
    de_k8s = _procedimento(db, categorias=["K8S"], seed=3)
    try:
        achados = _buscar_candidatos(db, _vetor(3), categorias_afinidade=["EDGE"], limit=1000)
        assert any(c.procedimento_id == de_k8s.id for c in achados), "sem nenhum procedimento EDGE, cai pro fallback sem filtro"
    finally:
        db.query(Procedimento).filter(Procedimento.id == de_k8s.id).delete(synchronize_session=False)
        db.commit()


def test_procedimento_rascunho_nao_entra_nem_restrito_nem_no_fallback(db):
    rascunho = _procedimento(db, categorias=["STR"], seed=4, status=StatusProcedimento.rascunho)
    try:
        assert not any(c.procedimento_id == rascunho.id for c in _buscar_candidatos(db, _vetor(4), categorias_afinidade=["STR"], limit=1000))
        assert not any(c.procedimento_id == rascunho.id for c in _buscar_candidatos(db, _vetor(4), categorias_afinidade=None, limit=1000))
    finally:
        db.query(Procedimento).filter(Procedimento.id == rascunho.id).delete(synchronize_session=False)
        db.commit()


def test_procedimento_com_duas_categorias_aparece_nas_duas_buscas(db):
    duplo = _procedimento(db, categorias=["K8S", "SEC"], seed=5)
    try:
        for categoria in ("K8S", "SEC"):
            achados = _buscar_candidatos(db, _vetor(5), categorias_afinidade=[categoria], limit=1000)
            assert any(c.procedimento_id == duplo.id for c in achados)
    finally:
        db.query(Procedimento).filter(Procedimento.id == duplo.id).delete(synchronize_session=False)
        db.commit()
