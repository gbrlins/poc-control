"""scripts/import_seed.py (Postgres; Gemini simulado): importa como um upload (dono, idioma, título em inglês) e é seguro rodar de novo."""
import importlib.util
import pathlib
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.db import SessionLocal

try:
    with SessionLocal() as _db:
        _db.execute(text("select 1 from procedimentos limit 1"))
except Exception:  # noqa: BLE001
    pytest.skip("sem Postgres", allow_module_level=True)

from app.models import Procedimento, User  # noqa: E402
from app.procedimentos import router as procedimentos_router  # noqa: E402

_SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "import_seed.py"
_SEED = pathlib.Path(__file__).resolve().parent.parent / "seed" / "procedimentos"
if not _SEED.exists():
    pytest.skip("pasta seed/procedimentos não está disponível neste ambiente", allow_module_level=True)


@pytest.fixture()
def script():
    spec = importlib.util.spec_from_file_location("import_seed_sob_teste", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def usuario(db):
    u = User(email=f"seed-{uuid.uuid4().hex[:8]}@teste.example", password_hash="x", is_admin=False)
    db.add(u)
    db.commit()
    db.refresh(u)
    yield u
    db.query(Procedimento).filter(Procedimento.criado_por_id == u.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == u.id).delete(synchronize_session=False)
    db.commit()


@pytest.fixture(autouse=True)
def gemini_falso(monkeypatch):
    monkeypatch.setattr(procedimentos_router, "embed_document", lambda texto, api_key=None: [0.1] * 1536)
    monkeypatch.setattr(
        procedimentos_router,
        "traduzir_procedimento_html",
        lambda html, idioma, titulo, api_key=None: SimpleNamespace(idioma_detectado="pt", titulo_traduzido=f"EN {titulo}", html_traduzido=html),
    )


def test_importa_como_um_upload_com_dono_idioma_e_titulo_em_ingles_e_nao_duplica(script, usuario, db, monkeypatch, capsys):
    # títulos únicos: o teste nunca toca em procedimentos de verdade com os títulos reais
    sufixo = uuid.uuid4().hex[:6]
    monkeypatch.setattr(script, "PROCEDIMENTOS", [{**p, "titulo": f"{p['titulo']} [{sufixo}]"} for p in script.PROCEDIMENTOS])

    assert script.main(["--user", usuario.email]) == 0
    db.expire_all()
    criados = db.query(Procedimento).filter(Procedimento.titulo.like(f"%[{sufixo}]")).all()
    assert len(criados) == 3
    for p in criados:
        assert p.responsavel_id == usuario.id and p.criado_por_id == usuario.id
        assert p.status.value == "validado" and p.idioma_original == "pt" and p.titulo_en == f"EN {p.titulo}"
        assert len(p.chunks) > 0
    assert any("K8S" in p.categorias and "SEC" in p.categorias for p in criados)      # o do Vault tem as duas

    capsys.readouterr()
    assert script.main(["--user", usuario.email]) == 0                                    # de novo: nada é duplicado
    assert capsys.readouterr().out.count("Já existe") == 3
    db.expire_all()
    assert db.query(Procedimento).filter(Procedimento.titulo.like(f"%[{sufixo}]")).count() == 3


def test_usuario_inexistente_para_sem_importar_nada(script, db, capsys):
    antes = db.query(Procedimento).count()
    assert script.main(["--user", "nao-existe@teste.example"]) == 1
    assert "Usuário não encontrado" in capsys.readouterr().err
    assert db.query(Procedimento).count() == antes
