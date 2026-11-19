import io

import openpyxl

_ENCODINGS_CSV = ("utf-8-sig", "cp1252", "latin-1")


def _texto_de_csv(conteudo: bytes) -> str:
    for encoding in _ENCODINGS_CSV:
        try:
            return conteudo.decode(encoding)
        except UnicodeDecodeError:
            continue
    # latin-1 nunca falha (mapeia todo byte), mas o loop acima garante que preferimos
    # utf-8/cp1252 quando o arquivo de fato está num desses encodings.
    return conteudo.decode("latin-1")


def _valores_com_merge(ws) -> dict[tuple[int, int], object]:
    """Planilhas de checklist costumam agrupar categoria/tópico numa célula mesclada que
    cobre várias linhas (ex.: a célula "Armazenamento" mesclada por 5 linhas de
    funcionalidade) — o openpyxl só guarda o valor na célula do canto superior esquerdo do
    merge, as demais vêm `None`. Sem isso, o Gemini veria linhas "sem categoria" em vez de
    repetir a categoria do grupo."""
    mapa: dict[tuple[int, int], object] = {}
    for rng in ws.merged_cells.ranges:
        valor = ws.cell(row=rng.min_row, column=rng.min_col).value
        for row in range(rng.min_row, rng.max_row + 1):
            for col in range(rng.min_col, rng.max_col + 1):
                mapa[(row, col)] = valor
    return mapa


def _texto_de_xlsx(conteudo: bytes) -> str:
    try:
        wb = openpyxl.load_workbook(io.BytesIO(conteudo), data_only=True)
    except Exception as exc:
        raise ValueError(f"Could not read the XLSX spreadsheet: {exc}") from exc

    partes: list[str] = []
    varias_planilhas = len(wb.worksheets) > 1
    for ws in wb.worksheets:
        merges = _valores_com_merge(ws)
        linhas_texto = []
        for row in ws.iter_rows():
            valores = []
            for cell in row:
                valor = cell.value
                if valor is None:
                    valor = merges.get((cell.row, cell.column))
                valores.append("" if valor is None else str(valor).strip())
            while valores and not valores[-1]:
                valores.pop()
            if valores:
                linhas_texto.append(" | ".join(valores))
        if linhas_texto:
            cabecalho = f"## Planilha: {ws.title}\n" if varias_planilhas else ""
            partes.append(cabecalho + "\n".join(linhas_texto))

    if not partes:
        raise ValueError("The spreadsheet is empty")
    return "\n\n".join(partes)


def texto_de_planilha(conteudo: bytes, extensao: str) -> str:
    """Converte CSV/XLSX pra texto tabular simples (linhas ` | `-separadas, com cabeçalho de
    planilha quando há mais de uma aba) pra reaproveitar o mesmo caminho de texto que já ia
    pro Gemini (`extrair_itens_poc`), em vez de ensinar o SDK a ler um tipo de arquivo binário
    novo — o Gemini entende tabela em texto plano tão bem quanto um XLSX nativo, e isso evita
    qualquer limitação de MIME type suportado pela API."""
    if extensao == ".csv":
        return _texto_de_csv(conteudo)
    if extensao == ".xlsx":
        return _texto_de_xlsx(conteudo)
    raise ValueError(f"Unsupported extension: {extensao}")
