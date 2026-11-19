import html as html_lib
import io
from datetime import date

import openpyxl
from openpyxl.styles import Font

from app.models import Rfi, VeredictoRfi
from app.relatorio_i18n import fmt_data, html_lang, t

def _veredito_label(lang, v) -> str:
    return t(lang, f"veredito.{v.value}")


_VEREDITO_COLOR = {
    VeredictoRfi.atende: "#1f9a5e",
    VeredictoRfi.atende_parcial: "#92660a",
    VeredictoRfi.nao_atende: "#c2412f",
    VeredictoRfi.sem_evidencia: "#56706a",
}


def _esc(valor: str | None) -> str:
    return html_lib.escape(valor or "")


def _itens_por_categoria(rfi: Rfi, lang: str = "en") -> dict[str, list]:
    por_categoria: dict[str, list] = {}
    for item in sorted(rfi.itens, key=lambda i: i.ordem):
        por_categoria.setdefault(item.categoria or t(lang, "rfi.sem_categoria"), []).append(item)
    return por_categoria


def _fontes_texto(item) -> str:
    return "; ".join(f.get("titulo") or f.get("url", "") for f in (item.fontes or []))


def montar_rfi_export_html(rfi: Rfi, lang: str = "en") -> str:
    total = len(rfi.itens)
    avaliados = sum(1 for i in rfi.itens if i.veredito is not None)
    contagem = {v: sum(1 for i in rfi.itens if i.veredito == v) for v in VeredictoRfi}
    score = round(100 * contagem[VeredictoRfi.atende] / total, 1) if total > 0 else None
    resumo_html = ""
    if score is not None:
        partes_resumo = " · ".join(
            f"{contagem[v]} {_veredito_label(lang, v).lower()}" for v in VeredictoRfi if contagem[v] > 0
        )
        resumo_html = f'<p class="pct">{t(lang, 'rfi.atendimento')}: {score}% ({partes_resumo})</p>'

    linhas = []
    for categoria, itens in _itens_por_categoria(rfi, lang).items():
        linhas.append(f'<tr class="categoria-row"><td colspan="5"><strong>{_esc(categoria)}</strong></td></tr>')
        for item in itens:
            if item.veredito is not None:
                cor = _VEREDITO_COLOR[item.veredito]
                veredito_html = f'<span style="color:{cor};font-weight:600">{_veredito_label(lang, item.veredito)}</span>'
            else:
                veredito_html = f'<span style="color:#888">{t(lang, "rfi.processando")}</span>'
            fontes_html = "".join(
                f'<div><a href="{_esc(f.get("url",""))}" target="_blank" rel="noreferrer">{_esc(f.get("titulo") or f.get("url",""))}</a></div>'
                for f in (item.fontes or [])
            )
            linhas.append(
                f"<tr><td>{_esc(item.codigo)}</td><td>{_esc(item.descricao)}</td>"
                f"<td>{veredito_html}</td><td>{_esc(item.justificativa)}</td><td>{fontes_html}</td></tr>"
            )

    return f"""<!doctype html>
<html lang="{html_lang(lang)}">
<head>
<meta charset="utf-8">
<title>{_esc(rfi.titulo)} — {t(lang, 'rfi.titulo')}</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; max-width: 1100px; margin: 40px auto; padding: 0 20px; }}
  h1 {{ margin-bottom: 4px; }}
  .sub {{ color: #555; margin-bottom: 20px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 8px; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; font-size: 13px; vertical-align: top; }}
  th {{ background: #f0f0f0; }}
  .categoria-row td {{ background: #fafafa; }}
  .pct {{ font-size: 20px; font-weight: 700; margin: 0 0 20px; }}
  @media print {{ body {{ margin: 0; }} }}
</style>
</head>
<body>
  <h1>{_esc(rfi.titulo)}</h1>
  <div class="sub">
    {_esc(rfi.orgao)}{f" · {t(lang, 'rfi.processo')} {_esc(rfi.numero_processo)}" if rfi.numero_processo else ""}
    · {t(lang, 'comum.gerado_em')} {fmt_data(lang, date.today())}
  </div>
  <p class="pct">{t(lang, 'rfi.avaliados', a=avaliados, t=total)}</p>
  {resumo_html}

  <table>
    <thead><tr><th>{t(lang, 'comum.item')}</th><th>{t(lang, 'rfi.col_desc')}</th><th>{t(lang, 'rfi.col_veredito')}</th><th>{t(lang, 'rfi.col_just')}</th><th>{t(lang, 'rfi.col_fontes')}</th></tr></thead>
    <tbody>{"".join(linhas)}</tbody>
  </table>
</body>
</html>"""


def montar_rfi_export_xlsx(rfi: Rfi, lang: str = "en") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "RFI"

    cabecalho = [t(lang, "comum.item"), t(lang, "rfi.col_categoria"), t(lang, "rfi.col_desc"), t(lang, "rfi.col_veredito"), t(lang, "rfi.col_just"), t(lang, "rfi.col_fontes")]
    ws.append(cabecalho)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for item in sorted(rfi.itens, key=lambda i: i.ordem):
        veredito = _veredito_label(lang, item.veredito) if item.veredito is not None else t(lang, "rfi.processando_xlsx")
        ws.append(
            [
                item.codigo,
                item.categoria or "",
                item.descricao,
                veredito,
                item.justificativa or "",
                _fontes_texto(item),
            ]
        )

    larguras = [12, 28, 60, 16, 50, 40]
    for i, largura in enumerate(larguras, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = largura

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
