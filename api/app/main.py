import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.auth import router as auth_router
from app.config import settings
from app.db import SessionLocal
from app.planner.router import router as planner_router
from app.pocs.router import router as pocs_router
from app.recuperacao import recuperar_extracoes_interrompidas
from app.procedimentos.router import router as procedimentos_router
from app.rfi.router import router as rfi_router
from app.sync.router import router as sync_router
from app.users import router as users_router

# Sem isso, logger.warning/info/exception dos nossos módulos (app.gemini, app.pocs.tasks etc.)
# não aparecem em `docker logs` — o root logger do Python não tem handler por padrão, e o
# logging do uvicorn não propaga pros loggers da aplicação sozinho. Foi assim que um 503 real
# do Gemini na extração de uma PoC ficou invisível nos logs (só o traceback.exception ia pro
# "void"); isso garante que INFO pra cima sempre vá pro stdout do container.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # ADR 7: tarefas em segundo plano morrem com o processo; o que ficou `extraindo` vira `erro` pra poder tentar de novo.
    # Uma falha aqui nunca impede a api de subir.
    if settings.extracao_recuperar_no_inicio:
        try:
            with SessionLocal() as db:
                recuperadas = recuperar_extracoes_interrompidas(db)
            if recuperadas["pocs"] or recuperadas["rfis"]:
                logger.warning("Extrações interrompidas por um reinício marcadas como erro: %s", recuperadas)
        except Exception:  # noqa: BLE001
            logger.exception("Não consegui recuperar as extrações interrompidas")
    yield


app = FastAPI(title="POC Control", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(procedimentos_router)
app.include_router(pocs_router)
app.include_router(planner_router)
app.include_router(rfi_router)
app.include_router(sync_router)
app.include_router(users_router)


@app.get("/api/health")
def health():
    db_status = "ok"
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    finally:
        db.close()

    return {"status": "ok", "db": db_status}
