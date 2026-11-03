"""Cliente HTTP pra outra instância do poc-control (ver app/sync/router.py) -- login + as mesmas
chamadas que o navegador faria em /api/procedimentos, só que de servidor pra servidor. A senha do
servidor remoto (settings.sync_servidor_*) nunca sai deste processo."""

import httpx

from app.config import settings
from app.models import Procedimento


class RemotoErro(Exception):
    """Mensagem já pronta pra mostrar na UI -- login falhou, servidor fora do ar, item não achado."""


def cliente_remoto() -> httpx.Client:
    if not settings.sync_configurado:
        raise RemotoErro("Sincronização não configurada (SYNC_SERVIDOR_URL/EMAIL/SENHA vazios)")
    cliente = httpx.Client(base_url=settings.sync_servidor_url.rstrip("/"), timeout=30.0)
    try:
        resposta = cliente.post(
            "/api/auth/login",
            json={"email": settings.sync_servidor_email, "password": settings.sync_servidor_senha},
        )
    except httpx.HTTPError as exc:
        cliente.close()
        raise RemotoErro(f"Não foi possível conectar no servidor remoto: {exc}")
    if resposta.status_code != 200:
        cliente.close()
        raise RemotoErro("Login no servidor remoto falhou (e-mail/senha configurados estão corretos?)")
    return cliente


def listar_remotos(cliente: httpx.Client) -> list[dict]:
    resposta = cliente.get("/api/procedimentos")
    if resposta.status_code != 200:
        raise RemotoErro("Não foi possível listar os procedimentos do servidor remoto")
    return resposta.json()


def obter_remoto(cliente: httpx.Client, procedimento_id: str) -> dict:
    resposta = cliente.get(f"/api/procedimentos/{procedimento_id}")
    if resposta.status_code == 404:
        raise RemotoErro("Procedimento não encontrado no servidor (removido entre listar e baixar?)")
    if resposta.status_code != 200:
        raise RemotoErro("Não foi possível obter o procedimento do servidor remoto")
    return resposta.json()


def criar_remoto(cliente: httpx.Client, procedimento: Procedimento) -> dict:
    """Mesmos campos de formulário de criar_procedimento (app/procedimentos/router.py) --
    tags/categorias vão como string separada por vírgula, igual o front já manda."""
    dados = {
        "titulo": procedimento.titulo,
        "tags": ",".join(procedimento.tags),
        "categorias": ",".join(procedimento.categorias),
        "status": procedimento.status.value,
        "versao": str(procedimento.versao),
    }
    if procedimento.cliente_origem:
        dados["cliente_origem"] = procedimento.cliente_origem
    if procedimento.data_origem:
        dados["data_origem"] = procedimento.data_origem.isoformat()
    arquivos = {"arquivo": (f"{procedimento.titulo}.html", procedimento.html_original.encode("utf-8"), "text/html")}
    resposta = cliente.post("/api/procedimentos", data=dados, files=arquivos)
    if resposta.status_code != 201:
        detalhe = ""
        try:
            detalhe = resposta.json().get("detail", "")
        except ValueError:
            pass
        raise RemotoErro(detalhe or f"O servidor remoto recusou o envio (HTTP {resposta.status_code})")
    return resposta.json()
