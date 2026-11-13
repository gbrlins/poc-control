import logging
import uuid

from app.classificacao.service import classificar_item
from app.db import SessionLocal
from app.models import Classificacao, Item

logger = logging.getLogger(__name__)


def classificar_pendentes(
    poc_id: uuid.UUID, api_key: str | None = None, model: str | None = None, lang: str | None = None
) -> None:
    db = SessionLocal()
    try:
        itens = (
            db.query(Item)
            .outerjoin(Classificacao)
            .filter(Item.poc_id == poc_id, Classificacao.id.is_(None))
            .all()
        )
        for item in itens:
            try:
                classificar_item(db, item, api_key=api_key, model=model, lang=lang)
            except Exception:  # noqa: BLE001 - não pode travar o lote por um item com erro
                logger.exception("Falha ao classificar item %s", item.id)
    finally:
        db.close()
