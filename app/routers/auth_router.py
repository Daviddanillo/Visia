from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import criar_token, get_current_user, hash_senha, verificar_senha
from app.db.database import get_db
from app.models.usuario import Usuario
from app.schemas.auth import (
    LoginRequest,
    TokenResposta,
    UsuarioAtualizar,
    UsuarioCriar,
    UsuarioResposta,
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/cadastro", response_model=UsuarioResposta, status_code=status.HTTP_201_CREATED)
def cadastrar(dados: UsuarioCriar, db: Session = Depends(get_db)):
    if db.query(Usuario).filter(Usuario.email == dados.email).first():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado.")
    usuario = Usuario(
        nome=dados.nome,
        email=dados.email,
        senha_hash=hash_senha(dados.senha),
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


@router.post("/login", response_model=TokenResposta)
def login(dados: LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.email == dados.email).first()
    if not usuario or not verificar_senha(dados.senha, usuario.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
        )
    return {
        "access_token": criar_token({"sub": usuario.email}),
        "token_type": "bearer",
        "usuario": usuario,
    }


@router.get("/me", response_model=UsuarioResposta)
def obter_perfil(usuario: Usuario = Depends(get_current_user)):
    return usuario


@router.put("/me", response_model=UsuarioResposta)
def atualizar_perfil(
    dados: UsuarioAtualizar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    if dados.email and dados.email != usuario.email:
        if db.query(Usuario).filter(Usuario.email == dados.email).first():
            raise HTTPException(status_code=400, detail="E-mail já está em uso.")
        usuario.email = dados.email
    if dados.nome:
        usuario.nome = dados.nome
    if dados.senha:
        usuario.senha_hash = hash_senha(dados.senha)
    db.commit()
    db.refresh(usuario)
    return usuario


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def deletar_conta(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    db.delete(usuario)
    db.commit()
