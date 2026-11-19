"""resolver_urls: troca o redirecionamento do grounding pelo endereço real; qualquer falha devolve o link original."""
import os

for chave, valor in {
    "POSTGRES_USER": "x", "POSTGRES_PASSWORD": "x", "POSTGRES_DB": "x", "SESSION_SECRET": "teste",
    "GEMINI_API_KEY": "x", "ADMIN_EMAIL": "a@example.com", "ADMIN_PASSWORD_HASH": "x",
}.items():
    os.environ.setdefault(chave, valor)

import httpx  # noqa: E402

from app import url_real  # noqa: E402

REDIR = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"


def _com_transporte(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(url_real.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))


def test_resolve_o_redirecionamento_e_mantem_a_ordem(monkeypatch):
    _com_transporte(monkeypatch, lambda req: httpx.Response(302, headers={"location": "https://docs.suse.com/x"}))
    out = url_real.resolver_urls(["https://exemplo.com/a", REDIR])
    assert out == ["https://exemplo.com/a", "https://docs.suse.com/x"]   # só o host de redirecionamento é seguido


def test_falha_ou_destino_estranho_devolve_o_original(monkeypatch):
    _com_transporte(monkeypatch, lambda req: httpx.Response(200))
    assert url_real.resolver_urls([REDIR]) == [REDIR]
    _com_transporte(monkeypatch, lambda req: httpx.Response(302, headers={"location": "javascript:alert(1)"}))
    assert url_real.resolver_urls([REDIR]) == [REDIR]

    def explode(req):
        raise httpx.ConnectTimeout("lento")
    _com_transporte(monkeypatch, explode)
    assert url_real.resolver_urls([REDIR]) == [REDIR]
    assert url_real.resolver_urls([]) == []
