import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _licitacoes_polling_desligado(monkeypatch):
    """O laço periódico de licitações (app/main.py::_laco_licitacoes) dispara de verdade sempre que
    um teste entra no lifespan via `with TestClient(app) as c:` (ex.: test_recuperacao_db.py) --
    sem isto, esses testes bateriam na rede de verdade contra o PNCP a cada rodada. Desligado por
    padrão pro pacote inteiro; um teste que precise do laço em si liga de volta explicitamente
    (monkeypatch.setattr(settings, "licitacoes_polling_ativo", True))."""
    monkeypatch.setattr(settings, "licitacoes_polling_ativo", False)
