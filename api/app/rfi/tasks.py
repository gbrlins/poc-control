import logging
import uuid

from app.categorias import normalizar as normalizar_categoria
from app.db import SessionLocal
from app.gemini import extrair_itens_rfi, interpretar_erro_gemini, modelo_efetivo
from app.models import Rfi, RfiItem, StatusExtracao
from app.rfi.service import avaliar_item_rfi

logger = logging.getLogger(__name__)


def processar_rfi(
    rfi_id: uuid.UUID,
    pdf_bytes: bytes | None,
    texto: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> None:
    """Extrai os itens do documento e, assim que estiver pronto, já dispara a busca web pra \
    cada item nesse mesmo background task (diferente do fluxo de PoC, onde extração e \
    classificação são dois botões/endpoints separados) -- é o que o Gabriel pediu: uma \
    primeira triagem inteira automática, sem clique a mais."""
    db = SessionLocal()
    try:
        rfi = db.get(Rfi, rfi_id)
        if rfi is None:
            return

        rfi.modelo_extracao = modelo_efetivo(model)

        try:
            extraido = extrair_itens_rfi(pdf_bytes=pdf_bytes, texto=texto, api_key=api_key, model=model)
        except Exception as exc:  # noqa: BLE001 - precisa capturar qualquer erro da chamada ao Gemini
            logger.exception("Falha ao extrair itens do RFI %s (modelo=%s)", rfi_id, model)
            rfi.status_extracao = StatusExtracao.erro
            rfi.erro_extracao = interpretar_erro_gemini(exc)
            db.commit()
            return

        if not rfi.titulo:
            rfi.titulo = extraido.titulo_sugerido or "RFI sem título"
        if not rfi.orgao:
            rfi.orgao = extraido.orgao_sugerido or ""
        if not rfi.numero_processo:
            rfi.numero_processo = extraido.numero_processo_sugerido or None

        itens: list[RfiItem] = []
        for i, item in enumerate(extraido.itens):
            novo = RfiItem(
                rfi_id=rfi.id,
                codigo=item.codigo,
                categoria=item.categoria or None,
                categoria_codigo=normalizar_categoria(item.categoria_codigo),
                descricao=item.descricao,
                ordem=i,
            )
            db.add(novo)
            itens.append(novo)

        rfi.status_extracao = StatusExtracao.pronto
        db.commit()

        for item in itens:
            try:
                avaliar_item_rfi(db, item, api_key=api_key, model=model)
            except Exception:  # noqa: BLE001 - não pode travar o lote por um item com erro
                logger.exception("Falha ao avaliar item %s do RFI %s", item.id, rfi_id)
    finally:
        db.close()
