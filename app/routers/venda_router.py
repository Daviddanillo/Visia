import io
import logging
from datetime import datetime
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.database import get_db
from app.models.usuario import Usuario
from app.models.venda import UploadArquivo, Venda
from app.schemas.venda import (
    ArquivoResposta,
    ImportacaoResposta,
    StatsResposta,
    VendaAtualizar,
    VendaCriar,
    VendaResposta,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/vendas", tags=["Vendas"])

_SINONIMOS_DATA = {
    "shipping_limit_date", "order_purchase_timestamp", "order_approved_at",
    "data_venda", "data", "date", "ds", "dia",
}
_SINONIMOS_VALOR = {
    "price", "payment_value", "valor", "venda", "vendas", "y", "total", "preco",
}


def _detectar_coluna(colunas: list, sinonimos: set) -> Optional[str]:
    return next((c for c in colunas if any(s in c for s in sinonimos)), None)


def _limpar_valor(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(
        serie.astype(str)
            .str.replace("R$", "", regex=False)
            .str.replace(" ", "", regex=False)
            .str.replace(r"\.(?=\d{3})", "", regex=True)
            .str.replace(",", ".", regex=False),
        errors="coerce",
    )


# ── Arquivos (definidos antes de /{venda_id} para evitar conflito de rota) ────

@router.get("/arquivos", response_model=List[ArquivoResposta])
def listar_arquivos(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    return (
        db.query(UploadArquivo)
        .filter(UploadArquivo.usuario_id == usuario.id)
        .order_by(UploadArquivo.id.desc())
        .all()
    )


@router.delete("/arquivos/{arquivo_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_arquivo(
    arquivo_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    arquivo = (
        db.query(UploadArquivo)
        .filter(UploadArquivo.id == arquivo_id, UploadArquivo.usuario_id == usuario.id)
        .first()
    )
    if not arquivo:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    db.delete(arquivo)
    db.commit()


# ── Stats (definido antes de /{venda_id}) ────────────────────────────────────

@router.get("/stats", response_model=StatsResposta)
def obter_stats(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    vendas   = db.query(Venda).filter(Venda.usuario_id == usuario.id).all()
    arquivos = (
        db.query(UploadArquivo)
        .filter(UploadArquivo.usuario_id == usuario.id)
        .order_by(UploadArquivo.id.desc())
        .all()
    )
    if not vendas:
        return StatsResposta(
            total_registros=0,
            total_valor=0.0,
            maior_venda=0.0,
            media_diaria=0.0,
            total_arquivos=len(arquivos),
            ultimo_upload=None,
        )
    valores      = [v.valor for v in vendas]
    datas_unicas = len({str(v.data_venda) for v in vendas})
    return StatsResposta(
        total_registros=len(vendas),
        total_valor=round(sum(valores), 2),
        maior_venda=round(max(valores), 2),
        media_diaria=round(sum(valores) / datas_unicas, 2) if datas_unicas else 0.0,
        total_arquivos=len(arquivos),
        ultimo_upload=arquivos[0].data_upload.strftime("%d/%m/%Y") if arquivos else None,
    )


# ── Importação CSV (definido antes de /{venda_id}) ────────────────────────────

@router.post("/importar-csv", response_model=ImportacaoResposta, status_code=status.HTTP_201_CREATED)
async def importar_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    conteudo = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(conteudo), sep=None, engine="python")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Arquivo CSV inválido: {exc}")

    if df.empty:
        raise HTTPException(status_code=400, detail="O arquivo está vazio.")

    df.columns = [str(c).strip().lower().replace('"', "").replace("'", "") for c in df.columns]
    col_data  = _detectar_coluna(df.columns.tolist(), _SINONIMOS_DATA)
    col_valor = _detectar_coluna(df.columns.tolist(), _SINONIMOS_VALOR)

    trabalho = pd.DataFrame()
    trabalho["data_venda"] = (
        pd.to_datetime(df[col_data], errors="coerce").dt.date
        if col_data else datetime.now().date()
    )
    if col_valor:
        trabalho["valor"] = (
            _limpar_valor(df[col_valor])
            if df[col_valor].dtype == object
            else pd.to_numeric(df[col_valor], errors="coerce")
        )
    else:
        logger.warning("Coluna de valor não detectada. Usando peso unitário 1.0 por linha.")
        trabalho["valor"] = 1.0

    trabalho["data_venda"] = trabalho["data_venda"].fillna(datetime.now().date())
    trabalho["valor"]      = trabalho["valor"].fillna(0.0)

    consolidado = trabalho.groupby("data_venda")["valor"].sum().reset_index()

    arquivo = UploadArquivo(
        nome_arquivo=file.filename,
        data_upload=datetime.now().date(),
        usuario_id=usuario.id,
    )
    db.add(arquivo)
    db.flush()

    db.bulk_insert_mappings(
        Venda,
        [
            {
                "data_venda": row.data_venda,
                "valor":      float(row.valor),
                "usuario_id": usuario.id,
                "arquivo_id": arquivo.id,
            }
            for row in consolidado.itertuples(index=False)
        ],
    )
    db.commit()

    return ImportacaoResposta(
        status="sucesso",
        mensagem=f"'{file.filename}' importado com sucesso.",
        registros_afetados=len(consolidado),
        arquivo_id=arquivo.id,
    )


# ── Vendas manuais (arquivo_id IS NULL) ──────────────────────────────────────

@router.get("/manuais", response_model=List[VendaResposta])
def listar_vendas_manuais(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    return (
        db.query(Venda)
        .filter(Venda.usuario_id == usuario.id, Venda.arquivo_id.is_(None))
        .order_by(Venda.data_venda.desc())
        .all()
    )


@router.delete("/manuais", status_code=status.HTTP_204_NO_CONTENT)
def deletar_todas_manuais(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    db.query(Venda).filter(
        Venda.usuario_id == usuario.id,
        Venda.arquivo_id.is_(None),
    ).delete(synchronize_session=False)
    db.commit()


# ── CRUD de Vendas ────────────────────────────────────────────────────────────

@router.get("/", response_model=List[VendaResposta])
def listar_vendas(
    arquivo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    query = db.query(Venda).filter(Venda.usuario_id == usuario.id)
    if arquivo_id is not None:
        query = query.filter(Venda.arquivo_id == arquivo_id)
    return query.order_by(Venda.data_venda.desc()).all()


@router.post("/", response_model=VendaResposta, status_code=status.HTTP_201_CREATED)
def criar_venda(
    dados: VendaCriar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    venda = Venda(data_venda=dados.data_venda, valor=dados.valor, usuario_id=usuario.id)
    db.add(venda)
    db.commit()
    db.refresh(venda)
    return venda


@router.get("/{venda_id}", response_model=VendaResposta)
def obter_venda(
    venda_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    venda = (
        db.query(Venda)
        .filter(Venda.id == venda_id, Venda.usuario_id == usuario.id)
        .first()
    )
    if not venda:
        raise HTTPException(status_code=404, detail="Venda não encontrada.")
    return venda


@router.put("/{venda_id}", response_model=VendaResposta)
def atualizar_venda(
    venda_id: int,
    dados: VendaAtualizar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    venda = (
        db.query(Venda)
        .filter(Venda.id == venda_id, Venda.usuario_id == usuario.id)
        .first()
    )
    if not venda:
        raise HTTPException(status_code=404, detail="Venda não encontrada.")
    if dados.data_venda is not None:
        venda.data_venda = dados.data_venda
    if dados.valor is not None:
        venda.valor = dados.valor
    db.commit()
    db.refresh(venda)
    return venda


@router.delete("/{venda_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_venda(
    venda_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    venda = (
        db.query(Venda)
        .filter(Venda.id == venda_id, Venda.usuario_id == usuario.id)
        .first()
    )
    if not venda:
        raise HTTPException(status_code=404, detail="Venda não encontrada.")
    db.delete(venda)
    db.commit()
