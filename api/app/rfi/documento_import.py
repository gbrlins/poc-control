import io

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph


def _iter_block_items(doc: Document):
    """Percorre parágrafos e tabelas na ordem em que aparecem no documento (python-docx expõe \
    as duas coleções separadas por padrão, o que embaralharia a ordem de leitura de um edital \
    com tabelas intercaladas no meio do texto)."""
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, doc)
        elif isinstance(child, CT_Tbl):
            yield Table(child, doc)


def texto_de_docx(conteudo: bytes) -> str:
    """Converte um .docx pra texto simples (parágrafos + tabelas como linhas ` | `-separadas, \
    mesmo espírito de `app/pocs/planilha_import.py::_texto_de_xlsx`), pra reaproveitar o mesmo \
    caminho de texto que já vai pro Gemini."""
    try:
        doc = Document(io.BytesIO(conteudo))
    except Exception as exc:
        raise ValueError(f"Could not read the Word file: {exc}") from exc

    linhas: list[str] = []
    for item in _iter_block_items(doc):
        if isinstance(item, Table):
            for row in item.rows:
                valores = [cell.text.strip() for cell in row.cells]
                while valores and not valores[-1]:
                    valores.pop()
                if valores:
                    linhas.append(" | ".join(valores))
        else:
            texto = item.text.strip()
            if texto:
                linhas.append(texto)

    if not linhas:
        raise ValueError("The Word document is empty")
    return "\n".join(linhas)
