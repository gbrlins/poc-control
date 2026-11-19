import html as html_lib
from datetime import date

from app.models import FlagClassificacao, Poc, StatusItem
from app.pocs.roteiro import montar_ambiente_html
from app.relatorio_i18n import fmt_data, html_lang, t

def _status_label(lang, status) -> str:
    return t(lang, f"status.{status.value}")


def _flag_label(lang, flag) -> str:
    # Linguagem de cliente (Validado / Em avaliação / Não suportado), não as cores internas do semáforo.
    return t(lang, f"flagcliente.{flag.value}")


_FLAG_COLOR = {
    FlagClassificacao.verde: "#1f9a5e",
    FlagClassificacao.amarelo: "#92660a",
    FlagClassificacao.vermelho: "#c2412f",
}

_PINE = "#0c322c"


def _esc(valor: str | None) -> str:
    return html_lib.escape(valor or "")


def montar_apresentacao_html(poc: Poc, lang: str = "en") -> str:
    total = len(poc.itens)
    concluidos = sum(1 for i in poc.itens if i.status == StatusItem.concluido)
    pendentes = sum(1 for i in poc.itens if i.status in (StatusItem.bloqueado, StatusItem.pendente))
    pct = round(concluidos / total * 100) if total else 0

    fase_titulo = {f["numero"]: f["titulo"] for f in (poc.fases or [])}
    por_fase: dict[int, list] = {}
    for item in poc.itens:
        por_fase.setdefault(item.fase, []).append(item)

    blocos_fase = []
    for numero in sorted(por_fase):
        titulo = fase_titulo.get(numero, t(lang, "comum.fase", n=numero))
        linhas = []
        for item in sorted(por_fase[numero], key=lambda i: i.ordem):
            classificacao = item.classificacao
            if classificacao:
                cor = _FLAG_COLOR[classificacao.flag]
                flag_html = f'<span style="color:{cor};font-weight:600">{_flag_label(lang, classificacao.flag)}</span>'
            else:
                flag_html = '<span style="color:#888">—</span>'
            linhas.append(
                f"<tr><td>{_esc(item.codigo)}</td><td>{_esc(item.titulo)}</td>"
                f"<td>{_status_label(lang, item.status)}</td><td>{flag_html}</td></tr>"
            )
        blocos_fase.append(
            f"<h3>{_esc(titulo)}</h3>"
            f'<table><thead><tr><th>{t(lang, 'comum.item')}</th><th>{t(lang, 'apres.col_desc')}</th><th>{t(lang, 'comum.status')}</th><th>{t(lang, 'apres.col_viab')}</th></tr></thead>'
            f"<tbody>{''.join(linhas)}</tbody></table>"
        )

    sessoes_ordenadas = sorted(poc.sessoes, key=lambda s: s.data)
    timeline_blocos = []
    proximos_passos_geral: list[str] = []
    for s in sessoes_ordenadas:
        bloco = f"<div class=\"sessao\"><h4>{fmt_data(lang, s.data)}</h4>"
        if s.participantes:
            bloco += f"<p class=\"muted\">{t(lang, 'comum.participantes')}: {_esc(', '.join(s.participantes))}</p>"
        if s.agenda:
            bloco += f"<p>{_esc(s.agenda)}</p>"
        for rotulo, campo, cor in (
            (t(lang, "comum.resolvido"), s.pontos_resolvidos, "#1f9a5e"),
            (t(lang, "comum.pendencias"), s.pontos_falha, "#92660a"),
            (t(lang, "comum.proximos_passos"), s.proximos_passos, "#2b6cb0"),
        ):
            if campo:
                itens_html = "".join(f"<li>{_esc(p)}</li>" for p in campo)
                bloco += f'<p class="tag" style="color:{cor}">{rotulo}</p><ul>{itens_html}</ul>'
        bloco += "</div>"
        timeline_blocos.append(bloco)
        proximos_passos_geral.extend(s.proximos_passos)

    passos_unicos = list(dict.fromkeys(proximos_passos_geral))
    passos_html = "".join(f"<li>{_esc(p)}</li>" for p in passos_unicos) or f"<li>{t(lang, 'apres.sem_passos')}</li>"

    resumo_paragrafos = "".join(
        f"<p>{_esc(p)}</p>" for p in (poc.resumo_executivo or "").split("\n") if p.strip()
    ) or f'<p class="muted">{t(lang, "apres.sumario_vazio")}</p>'

    blocos_fase_html = "".join(blocos_fase) or f'<p class="muted">{t(lang, "apres.sem_itens")}</p>'
    timeline_html = "".join(timeline_blocos) or f'<p class="muted">{t(lang, "comum.sessoes_vazio")}</p>'

    return f"""<!doctype html>
<html lang="{html_lang(lang)}">
<head>
<meta charset="utf-8">
<title>{_esc(poc.titulo)} — {t(lang, 'apres.titulo')}</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; max-width: 900px; margin: 0 auto; padding: 0 20px 60px; }}
  header {{ background: {_PINE}; color: #fff; margin: 0 -20px 32px; padding: 40px 20px; }}
  header h1 {{ margin: 0 0 6px; font-size: 26px; }}
  header .sub {{ opacity: .85; font-size: 14px; }}
  h2 {{ margin-top: 36px; border-bottom: 2px solid {_PINE}; padding-bottom: 6px; color: {_PINE}; }}
  h3 {{ margin-top: 24px; }}
  .stat-grid {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 8px; }}
  .stat {{ flex: 1; min-width: 140px; background: #f5f6f5; border-radius: 8px; padding: 14px 16px; }}
  .stat b {{ display: block; font-size: 28px; color: {_PINE}; }}
  .stat span {{ font-size: 12px; text-transform: uppercase; letter-spacing: .03em; color: #666; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 8px; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; font-size: 13px; vertical-align: top; }}
  th {{ background: #f0f0f0; }}
  .sessao {{ border-left: 3px solid {_PINE}; padding: 4px 16px; margin-bottom: 16px; }}
  .tag {{ font-size: 12px; text-transform: uppercase; letter-spacing: .03em; font-weight: 700; margin: 10px 0 2px; }}
  .muted {{ color: #666; }}
  ul {{ margin: 4px 0 12px; padding-left: 20px; font-size: 13px; }}
  @media print {{ header {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}
</style>
</head>
<body>
  <header>
    <h1>{_esc(poc.titulo)}</h1>
    <div class="sub">{_esc(poc.cliente)} · {t(lang, 'apres.sub')} · {fmt_data(lang, date.today())}</div>
  </header>

  <h2>{t(lang, 'apres.sumario')}</h2>
  {resumo_paragrafos}

  {montar_ambiente_html(poc, lang)}

  <h2>{t(lang, 'apres.numeros')}</h2>
  <div class="stat-grid">
    <div class="stat"><b>{pct}%</b><span>{t(lang, 'apres.concluido')}</span></div>
    <div class="stat"><b>{concluidos}/{total}</b><span>{t(lang, 'apres.itens_concluidos')}</span></div>
    <div class="stat"><b>{pendentes}</b><span>{t(lang, 'apres.itens_pendentes')}</span></div>
    <div class="stat"><b>{len(poc.sessoes)}</b><span>{t(lang, 'apres.sessoes_realizadas')}</span></div>
  </div>

  <h2>{t(lang, 'apres.por_fase')}</h2>
  {blocos_fase_html}

  <h2>{t(lang, 'apres.linha_tempo')}</h2>
  {timeline_html}

  <h2>{t(lang, 'apres.proximos')}</h2>
  <ul>{passos_html}</ul>
</body>
</html>"""
