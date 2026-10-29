"""Propriedade e exclusão permanente de PoCs e RFIs (ADR 4, poc-planner/docs/adr/ADR-0004-ownership-deletion.md).

- O dono é `responsavel_id`. Só o dono exclui; nem o administrador exclui a PoC de outra pessoa.
- Só o dono transfere. Linha SEM dono pode ser assumida por qualquer engenheiro. O administrador pode reatribuir o dono
  de qualquer linha (por exemplo quando o dono saiu), mas continua sem poder excluir.
- A exclusão exige o título digitado, grava uma linha de auditoria (sem cliente nem conteúdo) e remove as linhas do banco
  (cascata) e depois os arquivos. O histórico anônimo `resultados_catalogo` e os procedimentos promovidos sobrevivem."""

import logging
import pathlib
import shutil
import uuid
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Anexo, Exclusao, Item, Nota, Poc, Procedimento, Rfi, RfiItem, User

logger = logging.getLogger(__name__)


@dataclass
class ExclusaoErro(Exception):
    status: int
    mensagem: str


def eh_dono(user: User, recurso) -> bool:
    return recurso.responsavel_id is not None and recurso.responsavel_id == user.id


def pode_atribuir(user: User, recurso, novo_id: uuid.UUID) -> bool:
    if user.is_admin or eh_dono(user, recurso):
        return True
    return recurso.responsavel_id is None and novo_id == user.id  # assumir uma linha sem dono


def pasta_do(tipo: str, recurso_id: uuid.UUID) -> pathlib.Path:
    """Sempre montada a partir do id (nunca de um caminho guardado no banco), então nada fora de uploads/ é tocado."""
    return pathlib.Path(settings.uploads_dir) / ("pocs" if tipo == "poc" else "rfis") / str(recurso_id)


def _arquivos(pasta: pathlib.Path) -> int:
    return sum(1 for p in pasta.rglob("*") if p.is_file()) if pasta.is_dir() else 0


def _titulo_de_confirmacao(recurso) -> str:
    return (recurso.titulo or "").strip() or str(recurso.id)


def procedimentos_que_permanecem(db: Session, poc: Poc) -> list[dict]:
    linhas = (
        db.query(Procedimento.id, Procedimento.titulo)
        .join(Anexo, Anexo.procedimento_id == Procedimento.id)
        .join(Item, Item.id == Anexo.item_id)
        .filter(Item.poc_id == poc.id)
        .distinct()
        .all()
    )
    return [{"id": str(i), "titulo": t} for i, t in linhas]


def contagens(db: Session, tipo: str, recurso) -> dict:
    if tipo == "poc":
        itens = db.query(func.count(Item.id)).filter(Item.poc_id == recurso.id).scalar() or 0
        notas = db.query(func.count(Nota.id)).join(Item, Item.id == Nota.item_id).filter(Item.poc_id == recurso.id).scalar() or 0
        anexos = db.query(func.count(Anexo.id)).join(Item, Item.id == Anexo.item_id).filter(Item.poc_id == recurso.id).scalar() or 0
        return {"itens": itens, "notas": notas, "anexos": anexos, "sessoes": len(recurso.sessoes), "arquivos": _arquivos(pasta_do("poc", recurso.id))}
    itens = db.query(func.count(RfiItem.id)).filter(RfiItem.rfi_id == recurso.id).scalar() or 0
    return {"itens": itens, "arquivos": _arquivos(pasta_do("rfi", recurso.id))}


def previa(db: Session, user: User, tipo: str, recurso) -> dict:
    return {
        "titulo": _titulo_de_confirmacao(recurso),
        "podeExcluir": eh_dono(user, recurso),
        "semDono": recurso.responsavel_id is None,
        "contagens": contagens(db, tipo, recurso),
        "procedimentosQuePermanecem": procedimentos_que_permanecem(db, recurso) if tipo == "poc" else [],
    }


def excluir(db: Session, user: User, tipo: str, recurso, confirmar: str) -> None:
    if not eh_dono(user, recurso):
        raise ExclusaoErro(
            403,
            "Esta linha não tem dono: assuma-a antes de excluir." if recurso.responsavel_id is None else "Só o dono pode excluir.",
        )
    if (confirmar or "").strip() != _titulo_de_confirmacao(recurso):
        raise ExclusaoErro(400, "O título digitado não confere.")

    titulo = _titulo_de_confirmacao(recurso)
    recurso_id = recurso.id
    db.add(Exclusao(tipo=tipo, excluido_por_id=user.id, titulo=titulo[:255], contagens=contagens(db, tipo, recurso)))
    db.delete(recurso)
    db.commit()

    # Depois do commit: um arquivo que não apagar não desfaz a exclusão (as linhas já foram). Vai pro log e pro script de
    # varredura de órfãos (scripts/limpar_orfaos.py).
    pasta = pasta_do(tipo, recurso_id)
    try:
        shutil.rmtree(pasta)
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Não consegui apagar %s depois de excluir %s %s", pasta, tipo, recurso_id)
