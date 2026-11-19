import html as html_lib
from datetime import date

import markdown as markdown_lib

from app.models import Item, Poc
from app.relatorio_i18n import fmt_data, html_lang, t

_CAMPO_REDE = [
    ("cidr_gerenciamento", "ambiente.cidr"),
    ("gateway", "ambiente.gateway"),
    ("vip_cluster", "ambiente.vip"),
    ("pool_ip_inicio", "ambiente.pool_ini"),
    ("pool_ip_fim", "ambiente.pool_fim"),
]


def _esc(valor) -> str:
    return html_lib.escape(str(valor)) if valor not in (None, "") else ""


def _markdown(texto: str) -> str:
    return markdown_lib.markdown(texto or "", extensions=["tables"])


def montar_ambiente_html(poc: Poc, lang: str = "en") -> str:
    """Bloco "Ambiente desta PoC": parâmetros técnicos capturados na importação do JSON do
    Planejar PoC (ver app/pocs/planner_import.py). Nunca inclui credenciais."""
    params = poc.parametros_tecnicos
    if not params:
        return ""

    blocos = []
    produtos = params.get("produtos_selecionados") or []
    if produtos:
        blocos.append(f"<p><strong>{t(lang, 'ambiente.produtos')}:</strong> {_esc(', '.join(produtos))}</p>")

    rede = params.get("rede") or {}
    linhas_rede = [(t(lang, chave), rede.get(campo)) for campo, chave in _CAMPO_REDE if rede.get(campo)]
    if linhas_rede:
        linhas_html = "".join(f"<tr><td>{_esc(l)}</td><td>{_esc(v)}</td></tr>" for l, v in linhas_rede)
        blocos.append(f"<table class='params'><tbody>{linhas_html}</tbody></table>")

    vms = rede.get("vms") or []
    if vms:
        linhas_vm = "".join(
            f"<tr><td>{_esc(vm.get('name') or vm.get('key') or '—')}</td>"
            f"<td>{_esc(vm.get('ip'))}</td><td>{_esc(vm.get('hostname'))}</td></tr>"
            for vm in vms
            if isinstance(vm, dict)
        )
        if linhas_vm:
            blocos.append(
                "<table class='params'><thead><tr><th>VM</th><th>IP</th><th>Hostname</th></tr></thead>"
                f"<tbody>{linhas_vm}</tbody></table>"
            )

    if not blocos:
        return ""
    return f"<h2>{t(lang, 'ambiente.titulo')}</h2>" + "".join(blocos)


def montar_roteiro_html(poc: Poc, itens: list[Item], lang: str = "en") -> str:
    itens_ordenados = sorted(itens, key=lambda i: (i.fase, i.ordem))
    fase_titulo = {f["numero"]: f["titulo"] for f in (poc.fases or [])}

    blocos = []
    fase_atual: int | None = None
    for item in itens_ordenados:
        if item.fase != fase_atual:
            fase_atual = item.fase
            blocos.append(f"<h2>{_esc(fase_titulo.get(fase_atual, t(lang, 'comum.fase', n=fase_atual)))}</h2>")

        blocos.append(f"<div class='item'><h3>{_esc(item.codigo)} — {_esc(item.titulo)}</h3>")
        if item.descricao:
            blocos.append(f"<p>{_esc(item.descricao)}</p>")
        if item.criterio_aceite:
            blocos.append(
                f"<p class='criterio'><strong>{t(lang, 'roteiro.criterio')}:</strong> {_esc(item.criterio_aceite)}</p>"
            )

        classificacao = item.classificacao
        procedimento = classificacao.procedimento if classificacao else None
        if procedimento is not None:
            blocos.append(f"<p class='proc-link'><strong>{t(lang, 'roteiro.procedimento')}:</strong> {_esc(procedimento.titulo)}</p>")
            for chunk in procedimento.chunks:
                blocos.append(
                    f"<div class='passo'><h4>{_esc(chunk.heading_title)}</h4>{_markdown(chunk.content_text)}</div>"
                )
        elif classificacao is not None:
            blocos.append(
                f"<p class='alert alert-{classificacao.flag.value}'><strong>{t(lang, 'roteiro.sem_proc')}</strong> "
                f"({t(lang, 'roteiro.semaforo', flag=t(lang, 'flag.' + classificacao.flag.value))}). {_esc(classificacao.justificativa or '')}</p>"
            )
        else:
            blocos.append(f"<p class='alert'>{t(lang, 'roteiro.nao_class')}</p>")
        blocos.append("</div>")

    return f"""<!doctype html>
<html lang="{html_lang(lang)}">
<head>
<meta charset="utf-8">
<title>{_esc(poc.titulo)} — {t(lang, 'roteiro.titulo')}</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; max-width: 900px; margin: 40px auto; padding: 0 20px; }}
  h1 {{ margin-bottom: 4px; }}
  h2 {{ margin-top: 32px; border-bottom: 1px solid #ccc; padding-bottom: 6px; color: #0c322c; }}
  .sub {{ color: #555; margin-bottom: 20px; }}
  .item {{ border: 1px solid #ddd; border-radius: 8px; padding: 14px 18px; margin-bottom: 16px; }}
  .item h3 {{ margin: 0 0 8px; }}
  .criterio {{ font-size: 13px; color: #444; }}
  .proc-link {{ font-size: 13px; }}
  .passo {{ margin-top: 10px; padding-left: 14px; border-left: 3px solid #0c322c; font-size: 13.5px; }}
  .passo h4 {{ margin: 0 0 4px; font-size: 14px; }}
  .passo table {{ border-collapse: collapse; margin: 8px 0; width: 100%; }}
  .passo td, .passo th {{ border: 1px solid #ccc; padding: 4px 8px; font-size: 12.5px; text-align: left; }}
  table.params {{ border-collapse: collapse; margin: 8px 0; }}
  table.params td, table.params th {{ border: 1px solid #ccc; padding: 4px 10px; font-size: 13px; text-align: left; }}
  .alert {{ background: #fbefd2; border: 1px solid #e3c878; border-radius: 6px; padding: 8px 12px; font-size: 13px; }}
  .alert-vermelho {{ background: #f8e0da; border-color: #d99b89; }}
  .alert-amarelo {{ background: #fbefd2; border-color: #e3c878; }}
  @media print {{ body {{ margin: 0; }} }}
</style>
</head>
<body>
  <h1>{_esc(poc.titulo)}</h1>
  <div class="sub">{_esc(poc.cliente)} · {t(lang, 'roteiro.titulo')} · {t(lang, 'comum.gerado_em')} {fmt_data(lang, date.today())}</div>
  {montar_ambiente_html(poc, lang)}
  <h2>{t(lang, 'roteiro.itens_hoje')}</h2>
  {''.join(blocos) if blocos else '<p>' + t(lang, 'roteiro.vazio') + '</p>'}
</body>
</html>"""
