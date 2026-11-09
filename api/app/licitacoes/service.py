"""Verificação de licitações novas: varre o PNCP (pncp_client.py) por todas as modalidades, casa
contra os termos de busca ativos (matching.py) e grava/atualiza o que bater. Chamado tanto pelo
laço periódico em app/main.py quanto pelo botão "Atualizar agora" (app/licitacoes/router.py)."""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.licitacoes.matching import termos_que_batem
from app.licitacoes.pncp_client import MODALIDADES, buscar_publicacoes
from app.models import Licitacao, TermoBuscaLicitacao

logger = logging.getLogger(__name__)

# Últimos N dias até hoje, a cada rodada -- absorve rodadas perdidas (reinício, downtime) sem
# precisar guardar "última vez que rodou em quê". O UNIQUE em numero_controle_pncp faz buscar o
# mesmo período de novo não duplicar nada (vira update, não insert).
JANELA_DIAS = 3

# Trava simples em memória -- não deixa o laço periódico e o botão manual (ou dois cliques
# seguidos) rodarem ao mesmo tempo e brigarem pelo mesmo upsert. Também exposta (ver
# verificacao_em_andamento) pro front saber se ainda está rodando, já que uma rodada completa pode
# levar vários minutos (13 modalidades, cada uma pausada pra não levar 429 do PNCP).
_em_andamento = False


def verificacao_em_andamento() -> bool:
    return _em_andamento


def _data(valor: str | None) -> date | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor).date()
    except ValueError:
        return None


def _datahora(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


def _link_pncp(cnpj: str, ano: int, sequencial: int) -> str:
    return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{sequencial}"


def _upsert(db: Session, item: dict, codigo_modalidade: int, termos_encontrados: list[str]) -> bool:
    """Grava ou atualiza uma licitação a partir do item cru da API. Devolve True quando é nova.
    `codigo_modalidade` vem de quem chamou (o parâmetro já usado na busca), não do item -- mais
    confiável do que depender de um campo de modalidade na resposta."""
    numero_controle = item.get("numeroControlePNCP")
    if not numero_controle:
        return False

    orgao = item.get("orgaoEntidade") or {}
    unidade = item.get("unidadeOrgao") or {}

    existente = db.query(Licitacao).filter(Licitacao.numero_controle_pncp == numero_controle).one_or_none()
    nova = existente is None
    licitacao = existente or Licitacao(numero_controle_pncp=numero_controle)

    licitacao.orgao_nome = orgao.get("razaoSocial") or ""
    licitacao.orgao_cnpj = orgao.get("cnpj") or ""
    licitacao.unidade_nome = unidade.get("nomeUnidade")
    licitacao.uf = unidade.get("ufSigla")
    licitacao.municipio = unidade.get("municipioNome")
    licitacao.objeto = item.get("objetoCompra") or ""
    licitacao.modalidade_codigo = codigo_modalidade
    licitacao.modalidade_nome = MODALIDADES.get(codigo_modalidade)
    licitacao.valor_estimado = item.get("valorTotalEstimado")
    licitacao.data_publicacao = _data(item.get("dataPublicacaoPncp")) or date.today()
    licitacao.data_abertura_proposta = _datahora(item.get("dataAberturaProposta"))
    licitacao.data_encerramento_proposta = _datahora(item.get("dataEncerramentoProposta"))
    licitacao.ano_compra = item.get("anoCompra") or 0
    licitacao.sequencial_compra = item.get("sequencialCompra") or 0
    licitacao.termos_encontrados = termos_encontrados
    licitacao.link_pncp = _link_pncp(licitacao.orgao_cnpj, licitacao.ano_compra, licitacao.sequencial_compra)

    if nova:
        db.add(licitacao)
    return nova


def verificar_licitacoes(db: Session) -> int:
    """Varre as 13 modalidades do PNCP nos últimos JANELA_DIAS dias, casa o objeto de cada
    licitação contra os termos de busca ativos, e grava/atualiza as que baterem. Devolve quantas
    são novas. Uma falha numa modalidade (rede, API fora do ar) não derruba as outras -- loga e
    segue pras próximas."""
    global _em_andamento
    if _em_andamento:
        logger.info("Verificação de licitações já em andamento -- pulando esta chamada")
        return 0
    _em_andamento = True
    try:
        termos = [
            t.termo for t in db.query(TermoBuscaLicitacao).filter(TermoBuscaLicitacao.ativo.is_(True)).all()
        ]
        if not termos:
            return 0

        hoje = date.today()
        data_inicial = (hoje - timedelta(days=JANELA_DIAS)).strftime("%Y%m%d")
        data_final = hoje.strftime("%Y%m%d")

        novas = 0
        for codigo_modalidade in MODALIDADES:
            try:
                itens = buscar_publicacoes(data_inicial, data_final, codigo_modalidade)
            except Exception:  # noqa: BLE001 - uma modalidade fora do ar não pode travar as outras
                logger.exception("Falha ao buscar modalidade %s no PNCP", codigo_modalidade)
                continue

            for item in itens:
                encontrados = termos_que_batem(item.get("objetoCompra") or "", termos)
                if not encontrados:
                    continue
                if _upsert(db, item, codigo_modalidade, encontrados):
                    novas += 1
            db.commit()

        return novas
    finally:
        _em_andamento = False
