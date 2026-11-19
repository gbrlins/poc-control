import html as html_lib
from datetime import date

from app.models import FlagClassificacao, Poc, StatusItem
from app.relatorio_i18n import fmt_data, html_lang, t

def _status_label(lang, status) -> str:
    return t(lang, f"status.{status.value}")


def _flag_label(lang, flag) -> str:
    return t(lang, f"flag.{flag.value}")


_FLAG_COLOR = {
    FlagClassificacao.verde: "#1f9a5e",
    FlagClassificacao.amarelo: "#92660a",
    FlagClassificacao.vermelho: "#c2412f",
}


def _esc(valor: str | None) -> str:
    return html_lib.escape(valor or "")


def montar_export_html(poc: Poc, lang: str = "en") -> str:
    total = len(poc.itens)
    concluidos = sum(1 for i in poc.itens if i.status == StatusItem.concluido)
    pct = round(concluidos / total * 100) if total else 0

    fase_titulo = {f["numero"]: f["titulo"] for f in (poc.fases or [])}
    por_fase: dict[int, list] = {}
    for item in poc.itens:
        por_fase.setdefault(item.fase, []).append(item)

    linhas_itens = []
    for numero in sorted(por_fase):
        titulo = fase_titulo.get(numero, t(lang, "comum.fase", n=numero))
        linhas_itens.append(f'<tr class="fase-row"><td colspan="4"><strong>{_esc(titulo)}</strong></td></tr>')
        for item in sorted(por_fase[numero], key=lambda i: i.ordem):
            classificacao = item.classificacao
            if classificacao:
                cor = _FLAG_COLOR[classificacao.flag]
                flag_html = f'<span style="color:{cor};font-weight:600">{_flag_label(lang, classificacao.flag)}</span>'
                if classificacao.procedimento:
                    flag_html += f"<br><small>{_esc(classificacao.procedimento.titulo)}</small>"
            else:
                flag_html = '<span style="color:#888">—</span>'
            linhas_itens.append(
                f"<tr><td>{_esc(item.codigo)}</td><td>{_esc(item.titulo)}</td>"
                f"<td>{_status_label(lang, item.status)}</td><td>{flag_html}</td></tr>"
            )

    prereq_linhas = "".join(
        f"<li>{'☑' if p.atendido else '☐'} {_esc(p.titulo)}"
        f"{f' — {_esc(p.descricao)}' if p.descricao else ''}</li>"
        for p in poc.prerequisitos
    )

    sessao_blocos = []
    for s in sorted(poc.sessoes, key=lambda s: s.data):
        bloco = f"<h3>{fmt_data(lang, s.data)}</h3>"
        if s.participantes:
            bloco += f"<p><em>{t(lang, 'comum.participantes')}: {_esc(', '.join(s.participantes))}</em></p>"
        if s.agenda:
            bloco += f"<p>{_esc(s.agenda)}</p>"
        for rotulo, campo in (
            (t(lang, "comum.resolvido"), s.pontos_resolvidos),
            (t(lang, "comum.pendencias"), s.pontos_falha),
            (t(lang, "comum.proximos_passos"), s.proximos_passos),
        ):
            if campo:
                itens_html = "".join(f"<li>{_esc(p)}</li>" for p in campo)
                bloco += f"<p><strong>{rotulo}:</strong></p><ul>{itens_html}</ul>"
        sessao_blocos.append(bloco)

    return f"""<!doctype html>
<html lang="{html_lang(lang)}">
<head>
<meta charset="utf-8">
<title>{_esc(poc.titulo)} — {t(lang, 'export.titulo')}</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; max-width: 900px; margin: 40px auto; padding: 0 20px; }}
  h1 {{ margin-bottom: 4px; }}
  h2 {{ margin-top: 32px; border-bottom: 1px solid #ccc; padding-bottom: 6px; }}
  .sub {{ color: #555; margin-bottom: 20px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 8px; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; font-size: 13px; vertical-align: top; }}
  th {{ background: #f0f0f0; }}
  .fase-row td {{ background: #fafafa; }}
  .pct {{ font-size: 28px; font-weight: 700; margin: 0 0 20px; }}
  ul {{ margin: 4px 0 12px; padding-left: 20px; font-size: 13px; }}
  @media print {{ body {{ margin: 0; }} }}
</style>
</head>
<body>
  <h1>{_esc(poc.titulo)}</h1>
  <div class="sub">{_esc(poc.cliente)} · {t(lang, 'comum.gerado_em')} {fmt_data(lang, date.today())}</div>
  <p class="pct">{t(lang, 'export.pct', pct=pct, c=concluidos, t=total)}</p>

  <h2>{t(lang, 'export.plano')}</h2>
  <table>
    <thead><tr><th>{t(lang, 'export.col_codigo')}</th><th>{t(lang, 'comum.item')}</th><th>{t(lang, 'comum.status')}</th><th>{t(lang, 'export.col_class')}</th></tr></thead>
    <tbody>{"".join(linhas_itens)}</tbody>
  </table>

  <h2>{t(lang, 'export.prereq')}</h2>
  <ul>{prereq_linhas or f"<li>{t(lang, 'comum.nenhum')}</li>"}</ul>

  <h2>{t(lang, 'export.sessoes')}</h2>
  {"".join(sessao_blocos) or "<p>{t(lang, 'comum.sessoes_vazio')}</p>"}
</body>
</html>"""
