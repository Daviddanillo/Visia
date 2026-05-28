from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.database import get_db
from app.models.usuario import Usuario
from app.services.predictor import gerar_previsao

router = APIRouter(prefix="/predict", tags=["Previsão IA"])


@router.get("/")
def prever_vendas(
    dias: int = 30,
    arquivo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        return gerar_previsao(
            usuario_id=usuario.id,
            db=db,
            dias=dias,
            arquivo_id=arquivo_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
