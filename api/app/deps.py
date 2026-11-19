from fastapi import Cookie, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import read_session_cookie

SESSION_COOKIE_NAME = "poc_control_session"


def get_current_user(
    poc_control_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    if poc_control_session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    user_id = read_session_cookie(poc_control_session)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

    return user


def ui_lang(x_ui_lang: str | None = Header(default=None), lang: str | None = Query(default=None)) -> str:
    """Idioma da tela (pt|en|es): o cabeçalho X-UI-Lang que o front manda em todo pedido (web/src/api.ts) ou, nos links que o navegador abre
    sem cabeçalho (relatórios, downloads), o parâmetro ?lang=. Ausente ou desconhecido vira o idioma padrão (inglês, app/idioma.py)."""
    from app.idioma import SEM_TRADUCAO, norm_idioma

    pedido = lang or x_ui_lang  # o parâmetro é um pedido explícito; o cabeçalho é o idioma automático da tela
    return SEM_TRADUCAO if pedido == SEM_TRADUCAO else norm_idioma(pedido)


def get_current_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only administrators can do this")
    return user
