import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func

from app.categorias import normalizar as normalizar_categoria
from app.db import SessionLocal
from app.gemini import extrair_itens_rfi, interpretar_erro_gemini, modelo_efetivo
from app.models import OrigemClassificacao, Rfi, RfiDocumento, RfiItem, StatusExtracao, VeredictoRfi
from app.rfi.documentos import carregar_documento
from app.rfi.service import avaliar_item_rfi

logger = logging.getLogger(__name__)

JUSTIFICATIVA_INTERROMPIDO = (
    'Avaliação interrompida antes de chegar a este item — use "Reavaliar" (no item ou no RFI) para avaliá-lo.'
)


def iniciar_processamento(rfi: Rfi) -> None:
    """Marca o RFI como em processamento (também é o que bloqueia execuções concorrentes: os
    endpoints devolvem 409 enquanto estiver `extraindo`). Quem chama faz o commit."""
    rfi.status_extracao = StatusExtracao.extraindo
    rfi.erro_extracao = None
    rfi.processamento_iniciado_em = datetime.now(timezone.utc)
    rfi.progresso = None
    rfi.cancelamento_solicitado = False


def _cancelado(db, rfi_id: uuid.UUID) -> bool:
    db.expire_all()  # lê o valor atual do banco, não o da sessão
    return bool(db.query(Rfi.cancelamento_solicitado).filter(Rfi.id == rfi_id).scalar())


def _progresso(db, rfi: Rfi, fase: str, atual: int, total: int, nome: str) -> None:
    rfi.progresso = {"fase": fase, "atual": atual, "total": total, "nome": nome}
    db.commit()


def _finalizar(db, rfi_id: uuid.UUID, erro: bool = False) -> None:
    rfi = db.get(Rfi, rfi_id)
    if rfi is not None:
        rfi.status_extracao = StatusExtracao.erro if erro else StatusExtracao.pronto
        rfi.progresso = None
        rfi.cancelamento_solicitado = False
        db.commit()


def _avaliar(db, item_id: uuid.UUID, rfi_id: uuid.UUID, api_key: str | None, model: str | None) -> None:
    try:
        item = db.get(RfiItem, item_id)
        if item is None:  # removido (documento excluído) no meio da avaliação
            return
        avaliar_item_rfi(db, item, api_key=api_key, model=model)
    except Exception:  # noqa: BLE001 - não pode travar o lote por um item com erro
        db.rollback()
        logger.exception("Falha ao avaliar item %s do RFI %s", item_id, rfi_id)


def _marcar_interrompidos(db, ids: list[uuid.UUID]) -> None:
    """Itens novos que não chegaram a ser avaliados: sem isso ficariam `veredito=null` ("processando")
    para sempre. Viram "sem evidência" com uma justificativa que explica e manda reavaliar."""
    if not ids:
        return
    db.query(RfiItem).filter(RfiItem.id.in_(ids), RfiItem.veredito.is_(None)).update(
        {
            RfiItem.veredito: VeredictoRfi.sem_evidencia,
            RfiItem.justificativa: JUSTIFICATIVA_INTERROMPIDO,
            RfiItem.origem: None,
        },
        synchronize_session=False,
    )
    db.commit()


def processar_rfi(
    rfi_id: uuid.UUID,
    documento_ids: list[uuid.UUID],
    api_key: str | None = None,
    model: str | None = None,
) -> None:
    """Extrai os itens dos documentos indicados (um por vez, cada um numa chamada ao Gemini -- mais \
    robusto que um prompt gigante e permite remover um documento depois sem refazer os outros) e, \
    em seguida, avalia cada item NOVO nesse mesmo background task (diferente do fluxo de PoC, onde \
    extração e classificação são dois botões separados) -- é o que o Gabriel pediu: uma primeira \
    triagem inteira automática, sem clique a mais. O RFI fica `extraindo` até o fim da avaliação (o \
    que também bloqueia mudanças concorrentes). Chamado na criação do RFI (todos os documentos) e \
    quando documentos são adicionados depois (só os novos); itens já existentes não são tocados. \
    Pode ser interrompido (Rfi.cancelamento_solicitado) entre documentos e entre itens."""
    db = SessionLocal()
    try:
        rfi = db.get(Rfi, rfi_id)
        if rfi is None:
            return

        rfi.modelo_extracao = modelo_efetivo(model)
        # `or -1` quebraria quando o maior ordem existente for 0 (0 é falsy em Python, cairia no
        # -1 do fallback e repetiria ordem=0 no 2º documento) -- comparação explícita com None.
        maior_ordem = db.query(func.max(RfiItem.ordem)).filter(RfiItem.rfi_id == rfi.id).scalar()
        proxima_ordem = 0 if maior_ordem is None else maior_ordem + 1

        itens_novos: list[RfiItem] = []
        erros: list[str] = []
        tentados = 0
        cancelado = False
        for n, doc_id in enumerate(documento_ids, start=1):
            if _cancelado(db, rfi_id):
                cancelado = True
                break
            rfi = db.get(Rfi, rfi_id)
            doc = db.get(RfiDocumento, doc_id)
            if rfi is None:
                return
            if doc is None:  # removido enquanto esperava na fila
                continue
            _progresso(db, rfi, "lendo", n, len(documento_ids), doc.nome_arquivo)
            tentados += 1
            try:
                pdf_bytes, texto = carregar_documento(doc)
                extraido = extrair_itens_rfi(pdf_bytes=pdf_bytes, texto=texto, api_key=api_key, model=model)
            except Exception as exc:  # noqa: BLE001 - precisa capturar qualquer erro da chamada ao Gemini
                logger.exception("Falha ao extrair itens do documento %s do RFI %s (modelo=%s)", doc_id, rfi_id, model)
                erros.append(f"{doc.nome_arquivo}: {interpretar_erro_gemini(exc)}")
                continue

            if not rfi.titulo:
                rfi.titulo = extraido.titulo_sugerido or ""
            if not rfi.orgao:
                rfi.orgao = extraido.orgao_sugerido or ""
            if not rfi.numero_processo:
                rfi.numero_processo = extraido.numero_processo_sugerido or None

            for item in extraido.itens:
                novo = RfiItem(
                    rfi_id=rfi.id,
                    documento_id=doc.id,
                    codigo=item.codigo,
                    categoria=item.categoria or None,
                    categoria_codigo=normalizar_categoria(item.categoria_codigo),
                    descricao=item.descricao,
                    ordem=proxima_ordem,
                )
                proxima_ordem += 1
                db.add(novo)
                itens_novos.append(novo)
            # Commit por documento: os itens dele já aparecem na tela (que faz polling) enquanto os
            # próximos documentos ainda estão sendo lidos, em vez de tudo de uma vez no fim.
            db.commit()

        rfi = db.get(Rfi, rfi_id)
        if rfi is None:
            return
        if not rfi.titulo:
            rfi.titulo = "RFI sem título"
        # Só vira `erro` se NENHUM documento deu certo; se algum falhou e outro não, o RFI fica
        # `pronto` com a mensagem em erro_extracao (o front mostra como aviso).
        rfi.erro_extracao = "\n".join(erros) or None
        db.commit()
        if erros and len(erros) == tentados:
            _finalizar(db, rfi_id, erro=True)
            return

        ids = [i.id for i in itens_novos]
        try:
            for k, item_id in enumerate(ids, start=1):
                if cancelado or _cancelado(db, rfi_id):
                    cancelado = True
                    break
                rfi = db.get(Rfi, rfi_id)
                item = db.get(RfiItem, item_id)
                if rfi is None:
                    return
                _progresso(db, rfi, "avaliando", k, len(ids), item.codigo if item else "")
                _avaliar(db, item_id, rfi_id, api_key, model)
        finally:
            if cancelado:
                _marcar_interrompidos(db, ids)
            _finalizar(db, rfi_id)
    finally:
        db.close()


def reavaliar_rfi(
    rfi_id: uuid.UUID,
    incluir_manuais: bool,
    api_key: str | None = None,
    model: str | None = None,
    somente_pendentes: bool = False,
) -> None:
    """Reavalia todos os itens do RFI. Por padrão pula os que o usuário sobrescreveu à mão
    (origem=manual) pra não perder o trabalho dele. Se interrompido, os itens que ainda não foram
    reavaliados simplesmente mantêm o veredito que já tinham."""
    db = SessionLocal()
    try:
        rfi = db.get(Rfi, rfi_id)
        if rfi is None:
            return
        query = db.query(RfiItem.id).filter(RfiItem.rfi_id == rfi_id)
        if somente_pendentes:  # retoma uma avaliação que morreu no meio (reinício do servidor, por exemplo)
            query = query.filter(RfiItem.veredito.is_(None))
        elif not incluir_manuais:
            query = query.filter(
                (RfiItem.origem.is_(None)) | (RfiItem.origem != OrigemClassificacao.manual)
            )
        ids = [i for (i,) in query.order_by(RfiItem.ordem).all()]
        try:
            for k, item_id in enumerate(ids, start=1):
                if _cancelado(db, rfi_id):
                    break
                rfi = db.get(Rfi, rfi_id)
                item = db.get(RfiItem, item_id)
                if rfi is None:
                    return
                _progresso(db, rfi, "reavaliando", k, len(ids), item.codigo if item else "")
                _avaliar(db, item_id, rfi_id, api_key, model)
        finally:
            _finalizar(db, rfi_id)
    finally:
        db.close()
