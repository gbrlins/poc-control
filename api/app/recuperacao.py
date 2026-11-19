"""Recuperação de extrações interrompidas (ADR 7, poc-planner/docs/adr/ADR-0007-background-jobs.md).

A extração de itens (PoC) e de requisitos (RFI) roda no próprio processo da api (`BackgroundTasks`). Se o contêiner reinicia
no meio, a linha ficava `extraindo` para sempre e o "tentar de novo" (`reextrair`, que só aceita `erro`) não a alcançava.

Na inicialização, TODA linha ainda `extraindo` pertence a uma tarefa que morreu com o processo anterior (a api sobe com um
único worker), então vira `erro` com uma mensagem clara e o botão de nova tentativa volta a funcionar. Com mais de um worker
isso derrubaria tarefas vivas do outro: desligue com `EXTRACAO_RECUPERAR_NO_INICIO=false`."""

import logging

from sqlalchemy.orm import Session

from app.models import Poc, Rfi, StatusExtracao

logger = logging.getLogger(__name__)

MENSAGEM_REINICIO = (
    "The extraction was interrupted by a server restart before it finished. "
    "Use \"Try again\" to redo it."
)


def recuperar_extracoes_interrompidas(db: Session) -> dict[str, int]:
    """Marca como `erro` toda PoC e RFI ainda em `extraindo` e devolve quantas foram. Idempotente; faz o commit."""
    contagem = {}
    for chave, modelo in (("pocs", Poc), ("rfis", Rfi)):
        linhas = db.query(modelo).filter(modelo.status_extracao == StatusExtracao.extraindo).all()
        for linha in linhas:
            linha.status_extracao = StatusExtracao.erro
            linha.erro_extracao = MENSAGEM_REINICIO
        contagem[chave] = len(linhas)
    db.commit()
    return contagem
