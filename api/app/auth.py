from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.crypto import encrypt_secret
from app.db import get_db
from app.deps import SESSION_COOKIE_NAME, get_current_user
from app.gemini import interpretar_erro_gemini, listar_modelos_texto
from app.gemini_key import resolve_api_key
from app.models import User
from app.security import create_session_cookie, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    is_admin: bool
    tem_gemini_key: bool
    gemini_model: str | None


class GeminiKeyUpdate(BaseModel):
    api_key: str = Field(min_length=10)


class GeminiModelUpdate(BaseModel):
    model: str = Field(min_length=1, max_length=100)


class ModeloDisponivelOut(BaseModel):
    nome: str
    nome_exibicao: str


class UsuarioLookupOut(BaseModel):
    id: str
    email: str


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        is_admin=user.is_admin,
        tem_gemini_key=bool(user.gemini_api_key_encrypted),
        gemini_model=user.gemini_model,
    )


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha inválidos")

    user.ultimo_login = datetime.now(timezone.utc)
    db.commit()

    token = create_session_cookie(user.id)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.session_max_age_seconds,
    )
    return _user_out(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


@router.put("/me/gemini-key", response_model=UserOut)
def salvar_chave_gemini(payload: GeminiKeyUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.gemini_api_key_encrypted = encrypt_secret(payload.api_key.strip())
    db.commit()
    return _user_out(user)


@router.delete("/me/gemini-key", response_model=UserOut)
def remover_chave_gemini(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.gemini_api_key_encrypted = None
    db.commit()
    return _user_out(user)


@router.put("/me/gemini-model", response_model=UserOut)
def salvar_modelo_gemini(
    payload: GeminiModelUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    user.gemini_model = payload.model.strip()
    db.commit()
    return _user_out(user)


@router.delete("/me/gemini-model", response_model=UserOut)
def remover_modelo_gemini(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.gemini_model = None
    db.commit()
    return _user_out(user)


@router.get("/usuarios/lookup", response_model=UsuarioLookupOut)
def buscar_usuario_por_email(email: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Resolve um e-mail pro id do usuário -- único jeito de "transferir para alguém" sem expor a
    listagem completa de usuários (/api/users é admin-only) a quem não é admin."""
    usuario = db.query(User).filter(User.email == email.strip()).first()
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado")
    return UsuarioLookupOut(id=str(usuario.id), email=usuario.email)


@router.get("/me/gemini-models", response_model=list[ModeloDisponivelOut])
def listar_modelos_gemini_disponiveis(user: User = Depends(get_current_user)):
    """Consulta a própria API do Gemini pelos modelos que a chave em uso (pessoal ou
    compartilhada) tem acesso de verdade — usado pra popular o seletor em Minha conta."""
    try:
        modelos = listar_modelos_texto(resolve_api_key(user))
    except Exception as exc:  # noqa: BLE001 - qualquer erro da chamada ao Gemini vira 502 com mensagem acionável
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, interpretar_erro_gemini(exc))
    return [ModeloDisponivelOut(nome=m.nome, nome_exibicao=m.nome_exibicao) for m in modelos]
