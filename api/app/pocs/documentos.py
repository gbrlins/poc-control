"""Leitura/gravação dos documentos de uma PoC (PDF, planilha, texto/JSON). Compartilhado pela
criação da PoC e pela adição de documentos depois (app/pocs/router.py) e pela extração em
background (app/pocs/tasks.py), que relê o arquivo do disco. Espelha app/rfi/documentos.py."""

import pathlib
import uuid

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Poc, PocDocumento
from app.pocs.planilha_import import texto_de_planilha

TEXTO_COLADO_NOME = "texto-colado.txt"


def ler_conteudo(nome: str, conteudo: bytes) -> tuple[bytes | None, str | None]:
    """Devolve (pdf_bytes, texto): PDF vai nativo pro Gemini, o resto vira texto. Levanta
    ValueError com mensagem pro usuário se o arquivo não for legível."""
    if not conteudo:
        raise ValueError(f"Arquivo vazio: {nome}")
    extensao = pathlib.Path(nome).suffix.lower()
    if extensao == ".pdf":
        return conteudo, None
    try:
        if extensao in (".xlsx", ".csv"):
            return None, texto_de_planilha(conteudo, extensao)
        return None, conteudo.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(
            f"Não foi possível ler {nome} como texto; envie um PDF, uma planilha XLSX/CSV, "
            "ou um arquivo de texto/JSON em UTF-8"
        )
    except ValueError as exc:
        raise ValueError(f"{nome}: {exc}")


def salvar_documento(db: Session, poc: Poc, nome: str, conteudo: bytes) -> PocDocumento:
    # .name descarta qualquer diretório que o cliente tenha mandado no filename.
    nome = pathlib.Path(nome).name or "documento"
    pasta = pathlib.Path(settings.uploads_dir) / "pocs" / str(poc.id)
    pasta.mkdir(parents=True, exist_ok=True)
    # Prefixo único: dois documentos com o mesmo nome na mesma PoC não podem se sobrescrever.
    caminho = pasta / f"{uuid.uuid4().hex[:8]}_{nome}"
    caminho.write_bytes(conteudo)
    doc = PocDocumento(poc_id=poc.id, nome_arquivo=nome, caminho_arquivo=str(caminho))
    db.add(doc)
    db.flush()
    return doc


def carregar_documento(doc: PocDocumento) -> tuple[bytes | None, str | None]:
    return ler_conteudo(doc.nome_arquivo, pathlib.Path(doc.caminho_arquivo).read_bytes())


def remover_arquivo(doc: PocDocumento) -> None:
    pathlib.Path(doc.caminho_arquivo).unlink(missing_ok=True)
