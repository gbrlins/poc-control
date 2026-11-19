"""Leitura/gravação dos documentos de um RFI (PDF, Word, planilha, texto). Compartilhado pela
criação do RFI e pela adição de documentos depois (app/rfi/router.py) e pela extração em background
(app/rfi/tasks.py), que relê o arquivo do disco."""

import pathlib
import uuid

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Rfi, RfiDocumento
from app.pocs.planilha_import import texto_de_planilha
from app.rfi.documento_import import texto_de_docx

TEXTO_COLADO_NOME = "texto-colado.txt"


def ler_conteudo(nome: str, conteudo: bytes) -> tuple[bytes | None, str | None]:
    """Devolve (pdf_bytes, texto): PDF vai nativo pro Gemini, o resto vira texto. Levanta
    ValueError com mensagem pro usuário se o arquivo não for legível."""
    if not conteudo:
        raise ValueError(f"Empty file: {nome}")
    extensao = pathlib.Path(nome).suffix.lower()
    if extensao == ".pdf":
        return conteudo, None
    try:
        if extensao in (".xlsx", ".csv"):
            return None, texto_de_planilha(conteudo, extensao)
        if extensao == ".docx":
            return None, texto_de_docx(conteudo)
        return None, conteudo.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(
            f"Could not read {nome} as text; send a PDF, a Word file (.docx), an XLSX/CSV "
            "spreadsheet, or a UTF-8 text file"
        )
    except ValueError as exc:
        raise ValueError(f"{nome}: {exc}")


def salvar_documento(db: Session, rfi: Rfi, nome: str, conteudo: bytes) -> RfiDocumento:
    # .name descarta qualquer diretório que o cliente tenha mandado no filename.
    nome = pathlib.Path(nome).name or "documento"
    pasta = pathlib.Path(settings.uploads_dir) / "rfis" / str(rfi.id)
    pasta.mkdir(parents=True, exist_ok=True)
    # Prefixo único: dois documentos com o mesmo nome no mesmo RFI não podem se sobrescrever.
    caminho = pasta / f"{uuid.uuid4().hex[:8]}_{nome}"
    caminho.write_bytes(conteudo)
    doc = RfiDocumento(rfi_id=rfi.id, nome_arquivo=nome, caminho_arquivo=str(caminho))
    db.add(doc)
    db.flush()
    return doc


def carregar_documento(doc: RfiDocumento) -> tuple[bytes | None, str | None]:
    return ler_conteudo(doc.nome_arquivo, pathlib.Path(doc.caminho_arquivo).read_bytes())


def remover_arquivo(doc: RfiDocumento) -> None:
    pathlib.Path(doc.caminho_arquivo).unlink(missing_ok=True)
