"""Disparo em segundo plano de verificar_licitacoes (ver app/licitacoes/router.py::atualizar_licitacoes)
-- uma rodada completa pode levar vários minutos (13 modalidades, cada uma pausada pra não levar
429 do PNCP), tempo demais pra segurar a resposta HTTP do botão "Atualizar agora" (nginx corta a
conexão em 300s -- ver web/nginx.conf). Mesmo padrão de app/rfi/tasks.py e app/pocs/tasks.py: abre
sua própria sessão, não reaproveita a da requisição (que já fechou quando esta função roda)."""

import logging

from app.db import SessionLocal
from app.licitacoes.service import verificar_licitacoes

logger = logging.getLogger(__name__)


def verificar_licitacoes_em_segundo_plano() -> None:
    db = SessionLocal()
    try:
        novas = verificar_licitacoes(db)
        logger.info("Licitações: verificação sob demanda terminou, %s nova(s)", novas)
    finally:
        db.close()
