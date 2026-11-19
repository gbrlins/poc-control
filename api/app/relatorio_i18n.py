"""Textos fixos dos relatórios exportados (HTML/XLSX) nos 3 idiomas da casca (pt/en/es).

O que vem do banco ou da IA (títulos, justificativas, resumos) NÃO passa por aqui: continua no idioma em que foi gerado (pt-BR, ver
CLAUDE.md). Só os rótulos, títulos de seção e status que o próprio relatório escreve. Idioma desconhecido cai em pt, que é o padrão.
Adicionar um idioma = acrescentar uma posição em cada tupla (e em LANGS)."""
from datetime import date

from app.idioma import norm_idioma

LANGS = ("pt", "en", "es")

# chave: (pt, en, es). Valores podem ter {campos} preenchidos por t(..., campo=...).
_TEXTOS: dict[str, tuple[str, str, str]] = {
    # status de item (PoC)
    "status.pendente": ("Pendente", "Pending", "Pendiente"),
    "status.em_andamento": ("Em andamento", "In progress", "En curso"),
    "status.concluido": ("Concluído", "Completed", "Completado"),
    "status.bloqueado": ("Bloqueado", "Blocked", "Bloqueado"),
    "status.nao_aplicavel": ("N/A", "N/A", "N/A"),
    # semáforo: no relatório interno (cores) e na apresentação (linguagem de cliente)
    "flag.verde": ("Verde", "Green", "Verde"),
    "flag.amarelo": ("Amarelo", "Yellow", "Amarillo"),
    "flag.vermelho": ("Vermelho", "Red", "Rojo"),
    "flagcliente.verde": ("Validado", "Validated", "Validado"),
    "flagcliente.amarelo": ("Em avaliação", "Under evaluation", "En evaluación"),
    "flagcliente.vermelho": ("Não suportado", "Not supported", "No soportado"),
    # veredito de RFI
    "veredito.atende": ("Atende", "Meets", "Cumple"),
    "veredito.atende_parcial": ("Atende parcial", "Partially meets", "Cumple parcialmente"),
    "veredito.nao_atende": ("Não atende", "Does not meet", "No cumple"),
    "veredito.sem_evidencia": ("Sem evidência", "No evidence", "Sin evidencia"),
    # comuns
    "comum.fase": ("Fase {n}", "Phase {n}", "Fase {n}"),
    "comum.participantes": ("Participantes", "Participants", "Participantes"),
    "comum.resolvido": ("Resolvido", "Resolved", "Resuelto"),
    "comum.pendencias": ("Pendências", "Open points", "Pendientes"),
    "comum.proximos_passos": ("Próximos passos", "Next steps", "Próximos pasos"),
    "comum.nenhum": ("Nenhum", "None", "Ninguno"),
    "comum.sessoes_vazio": ("Nenhuma sessão registrada.", "No sessions recorded.", "Ninguna sesión registrada."),
    "comum.gerado_em": ("gerado em", "generated on", "generado el"),
    "comum.item": ("Item", "Item", "Ítem"),
    "comum.status": ("Status", "Status", "Estado"),
    # relatório de status da PoC
    "export.titulo": ("Status", "Status", "Estado"),
    "export.pct": ("{pct}% dos itens concluídos ({c}/{t})", "{pct}% of items completed ({c}/{t})", "{pct}% de los ítems completados ({c}/{t})"),
    "export.plano": ("Plano de testes", "Test plan", "Plan de pruebas"),
    "export.col_codigo": ("Código", "Code", "Código"),
    "export.col_class": ("Classificação", "Classification", "Clasificación"),
    "export.prereq": ("Pré-requisitos", "Prerequisites", "Requisitos previos"),
    "export.sessoes": ("Sessões", "Sessions", "Sesiones"),
    # apresentação ao cliente
    "apres.titulo": ("Apresentação ao cliente", "Customer presentation", "Presentación al cliente"),
    "apres.sub": ("Apresentação de resultados", "Results presentation", "Presentación de resultados"),
    "apres.sumario": ("Sumário executivo", "Executive summary", "Resumen ejecutivo"),
    "apres.sumario_vazio": ("Sumário executivo ainda não foi gerado.", "The executive summary has not been generated yet.", "El resumen ejecutivo aún no se ha generado."),
    "apres.numeros": ("Resultados em números", "Results in numbers", "Resultados en cifras"),
    "apres.concluido": ("concluído", "completed", "completado"),
    "apres.itens_concluidos": ("itens concluídos", "items completed", "ítems completados"),
    "apres.itens_pendentes": ("itens pendentes/bloqueados", "pending/blocked items", "ítems pendientes/bloqueados"),
    "apres.sessoes_realizadas": ("sessões realizadas", "sessions held", "sesiones realizadas"),
    "apres.por_fase": ("Resultados por fase", "Results by phase", "Resultados por fase"),
    "apres.col_desc": ("Descrição", "Description", "Descripción"),
    "apres.col_viab": ("Viabilidade", "Feasibility", "Viabilidad"),
    "apres.linha_tempo": ("Linha do tempo das sessões", "Session timeline", "Línea de tiempo de las sesiones"),
    "apres.proximos": ("Próximos passos", "Next steps", "Próximos pasos"),
    "apres.sem_passos": ("Nenhum próximo passo registrado.", "No next steps recorded.", "Ningún próximo paso registrado."),
    "apres.sem_itens": ("Nenhum item cadastrado.", "No items registered.", "Ningún ítem registrado."),
    # roteiro do dia / ambiente
    "roteiro.titulo": ("Roteiro do dia", "Day script", "Guion del día"),
    "roteiro.itens_hoje": ("Itens selecionados para hoje", "Items selected for today", "Ítems seleccionados para hoy"),
    "roteiro.vazio": ("Nenhum item selecionado.", "No item selected.", "Ningún ítem seleccionado."),
    "roteiro.criterio": ("Critério de aceite", "Acceptance criterion", "Criterio de aceptación"),
    "roteiro.procedimento": ("Procedimento", "Procedure", "Procedimiento"),
    "roteiro.sem_proc": ("Sem procedimento vinculado", "No linked procedure", "Sin procedimiento vinculado"),
    "roteiro.semaforo": ("semáforo: {flag}", "flag: {flag}", "semáforo: {flag}"),
    "roteiro.nao_class": ("Item ainda não classificado.", "Item not classified yet.", "Ítem aún sin clasificar."),
    "ambiente.titulo": ("Ambiente desta PoC", "This PoC's environment", "Entorno de esta PoC"),
    "ambiente.produtos": ("Produtos selecionados", "Selected products", "Productos seleccionados"),
    "ambiente.cidr": ("CIDR de gerência", "Management CIDR", "CIDR de gestión"),
    "ambiente.gateway": ("Gateway", "Gateway", "Gateway"),
    "ambiente.vip": ("VIP do cluster", "Cluster VIP", "VIP del clúster"),
    "ambiente.pool_ini": ("Pool de IP (início)", "IP pool (start)", "Pool de IP (inicio)"),
    "ambiente.pool_fim": ("Pool de IP (fim)", "IP pool (end)", "Pool de IP (fin)"),
    # RFI
    "rfi.titulo": ("Análise de RFI", "RFI analysis", "Análisis de RFI"),
    "rfi.sem_categoria": ("Sem categoria", "No category", "Sin categoría"),
    "rfi.processo": ("processo", "process", "proceso"),
    "rfi.processando": ("Em processamento…", "Processing…", "Procesando…"),
    "rfi.atendimento": ("Atendimento", "Compliance", "Cumplimiento"),
    "rfi.avaliados": ("{a}/{t} itens avaliados", "{a}/{t} items evaluated", "{a}/{t} ítems evaluados"),
    "rfi.col_desc": ("Descrição", "Description", "Descripción"),
    "rfi.col_veredito": ("Veredito", "Verdict", "Veredicto"),
    "rfi.col_just": ("Justificativa", "Justification", "Justificación"),
    "rfi.col_fontes": ("Fonte(s)", "Source(s)", "Fuente(s)"),
    "rfi.col_categoria": ("Categoria", "Category", "Categoría"),
    "rfi.processando_xlsx": ("Em processamento", "Processing", "Procesando"),
}


def norm_lang(lang: str | None) -> str:
    return norm_idioma(lang)


def t(lang: str | None, chave: str, **campos) -> str:
    texto = _TEXTOS[chave][LANGS.index(norm_lang(lang))]
    return texto.format(**campos) if campos else texto


def fmt_data(lang: str | None, d: date) -> str:
    """pt/es: dd/mm/aaaa; en: aaaa-mm-dd (ISO, sem ambiguidade entre mm/dd e dd/mm)."""
    return d.strftime("%Y-%m-%d") if norm_lang(lang) == "en" else d.strftime("%d/%m/%Y")


def html_lang(lang: str | None) -> str:
    return {"pt": "pt-BR", "en": "en", "es": "es"}[norm_lang(lang)]
