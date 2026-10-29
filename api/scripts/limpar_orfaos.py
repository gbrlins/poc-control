"""Lista (e, com --apagar, remove) pastas de uploads cujo registro não existe mais no banco.

Uma exclusão (ADR 4) remove as linhas e DEPOIS os arquivos; se a remoção de uma pasta falhar, a linha já se foi e a pasta
fica órfã (o motivo vai pro log). Este script acha essas sobras. Por padrão só lista.

Uso, de dentro do container da api:  python scripts/limpar_orfaos.py [--apagar]"""
import argparse
import pathlib
import shutil
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Poc, Rfi  # noqa: E402


def orfaos(db) -> list[pathlib.Path]:
    achados = []
    for subpasta, modelo in (("pocs", Poc), ("rfis", Rfi)):
        raiz = pathlib.Path(settings.uploads_dir) / subpasta
        if not raiz.is_dir():
            continue
        existentes = {str(i) for (i,) in db.query(modelo.id).all()}
        for pasta in sorted(raiz.iterdir()):
            try:
                uuid.UUID(pasta.name)
            except ValueError:
                continue  # não é uma pasta nossa: não mexe
            if pasta.is_dir() and pasta.name not in existentes:
                achados.append(pasta)
    return achados


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apagar", action="store_true", help="remove de verdade (sem isso só lista)")
    args = ap.parse_args()
    with SessionLocal() as db:
        achados = orfaos(db)
    for p in achados:
        print(("apagando " if args.apagar else "órfã: ") + str(p))
        if args.apagar:
            shutil.rmtree(p)
    print(f"{len(achados)} pasta(s) órfã(s)" + ("" if args.apagar or not achados else " (use --apagar para remover)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
