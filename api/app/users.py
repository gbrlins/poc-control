import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_admin_user
from app.models import User
from app.security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(get_current_admin_user)])


class UsuarioCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    is_admin: bool = False


class AdminUpdate(BaseModel):
    is_admin: bool


class UsuarioOut(BaseModel):
    id: str
    email: str
    is_admin: bool
    created_at: datetime
    ultimo_login: datetime | None
    tem_gemini_key: bool


def _usuario_out(usuario: User) -> UsuarioOut:
    return UsuarioOut(
        id=str(usuario.id),
        email=usuario.email,
        is_admin=usuario.is_admin,
        created_at=usuario.created_at,
        ultimo_login=usuario.ultimo_login,
        tem_gemini_key=bool(usuario.gemini_api_key_encrypted),
    )


@router.get("", response_model=list[UsuarioOut])
def listar_usuarios(db: Session = Depends(get_db)):
    usuarios = db.query(User).order_by(User.created_at).all()
    return [_usuario_out(u) for u in usuarios]


@router.post("", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def criar_usuario(payload: UsuarioCreate, db: Session = Depends(get_db)):
    existente = db.query(User).filter(User.email == payload.email).first()
    if existente is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")

    usuario = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_admin=payload.is_admin,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    return _usuario_out(usuario)


@router.patch("/{usuario_id}/admin", response_model=UsuarioOut)
def atualizar_admin(
    usuario_id: uuid.UUID,
    payload: AdminUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Promove ou remove o acesso de administrador de um usuário, a qualquer momento (não só
    na criação). Bloqueia remover o admin do próprio usuário logado e remover o último
    administrador restante -- as duas formas de ninguém mais conseguir gerenciar usuários."""
    usuario = db.get(User, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    if usuario.is_admin and not payload.is_admin:
        if usuario.id == current_user.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot remove your own administrator access")
        outros_admins = db.query(User).filter(User.is_admin.is_(True), User.id != usuario.id).count()
        if outros_admins == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The last administrator cannot be removed")

    usuario.is_admin = payload.is_admin
    db.commit()
    db.refresh(usuario)
    return _usuario_out(usuario)
