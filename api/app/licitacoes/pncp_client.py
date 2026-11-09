"""Cliente fino pra API pública de consulta do PNCP (Portal Nacional de Contratações Públicas) --
sem autenticação, confirmado no swagger oficial (pncp.gov.br/api/consulta/swagger-ui). Não tem
busca por palavra-chave (ver app/licitacoes/matching.py pro filtro do lado de cá)."""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://pncp.gov.br/api/consulta"
TAMANHO_PAGINA = 50
# Confirmado em produção (2026-11-09): disparar as 13 modalidades (+ páginas) uma atrás da outra
# sem pausa alguma derrubou a API em 429 (Too Many Requests) a partir da ~17ª chamada em poucos
# segundos. Meio segundo entre chamadas (menos de 2/s) resolveu -- folgado o bastante pra não
# provocar o limite de novo, mesmo não documentado publicamente qual é o teto real.
PAUSA_ENTRE_CHAMADAS_SEGUNDOS = 0.5
# Teto de segurança por modalidade/rodada -- a API não documenta limite de taxa nem de volume, e
# isto evita uma rodada rodar pra sempre num dia com volume atípico. Loga aviso se bater o teto
# (pode haver mais resultados daquele dia não lidos nesta rodada; a próxima rodada tenta de novo
# com a janela rolante -- ver app/licitacoes/service.py).
MAX_PAGINAS_POR_MODALIDADE = 20
# Tentativas extras só pra 429 (a pausa normal já evita a maioria, isto é rede de segurança caso o
# limite do dia esteja mais apertado que o de costume), com espera crescente entre elas.
TENTATIVAS_APOS_429 = 3

# Tabela de domínio "Modalidade de Contratação" (Manual de Integração PNCP) -- confirmada por
# terceiros que reproduzem a tabela oficial; a varredura passa por todas, já que o pedido é cobrir
# "todos os itens que a SUSE pode concorrer".
MODALIDADES: dict[int, str] = {
    1: "Leilão - Eletrônico",
    2: "Diálogo Competitivo",
    3: "Concurso",
    4: "Concorrência - Eletrônica",
    5: "Concorrência - Presencial",
    6: "Pregão - Eletrônico",
    7: "Pregão - Presencial",
    8: "Dispensa de Licitação",
    9: "Inexigibilidade",
    10: "Manifestação de Interesse",
    11: "Pré-qualificação",
    12: "Credenciamento",
    13: "Leilão - Presencial",
}


def buscar_publicacoes(data_inicial: str, data_final: str, codigo_modalidade: int) -> list[dict]:
    """Todas as páginas de /v1/contratacoes/publicacao pra uma modalidade e intervalo de datas
    (yyyyMMdd), até acabar ou bater MAX_PAGINAS_POR_MODALIDADE. Levanta httpx.HTTPError se a API
    falhar -- quem chama (service.py) decide se segue pras próximas modalidades ou para a rodada."""
    itens: list[dict] = []
    pagina = 1
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as cliente:
        while pagina <= MAX_PAGINAS_POR_MODALIDADE:
            time.sleep(PAUSA_ENTRE_CHAMADAS_SEGUNDOS)
            params = {
                "dataInicial": data_inicial,
                "dataFinal": data_final,
                "codigoModalidadeContratacao": codigo_modalidade,
                "pagina": pagina,
                "tamanhoPagina": TAMANHO_PAGINA,
            }
            resposta = cliente.get("/v1/contratacoes/publicacao", params=params)
            tentativa = 1
            while resposta.status_code == 429 and tentativa < TENTATIVAS_APOS_429:
                espera = PAUSA_ENTRE_CHAMADAS_SEGUNDOS * (4**tentativa)  # 2s, depois 8s
                logger.warning(
                    "429 do PNCP na modalidade %s página %s -- esperando %.0fs e tentando de novo (%s/%s)",
                    codigo_modalidade, pagina, espera, tentativa, TENTATIVAS_APOS_429 - 1,
                )
                time.sleep(espera)
                resposta = cliente.get("/v1/contratacoes/publicacao", params=params)
                tentativa += 1

            if resposta.status_code == 204:
                break
            resposta.raise_for_status()
            corpo = resposta.json()
            pagina_itens = corpo.get("data") or []
            if not pagina_itens:
                break
            itens.extend(pagina_itens)
            total_paginas = corpo.get("totalPaginas") or pagina
            if pagina >= total_paginas:
                break
            pagina += 1
        else:
            logger.warning(
                "Modalidade %s (%s): parei em %s páginas (teto de segurança) -- "
                "pode haver mais resultados do período não lidos nesta rodada",
                codigo_modalidade,
                MODALIDADES.get(codigo_modalidade, "?"),
                MAX_PAGINAS_POR_MODALIDADE,
            )
    return itens
