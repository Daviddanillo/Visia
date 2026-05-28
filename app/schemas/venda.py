from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class VendaCriar(BaseModel):
    data_venda: date
    valor: float = Field(..., gt=0, description="Valor da venda em R$")


class VendaAtualizar(BaseModel):
    data_venda: Optional[date] = None
    valor: Optional[float] = Field(None, gt=0)


class VendaResposta(BaseModel):
    id: int
    usuario_id: int
    data_venda: date
    valor: float
    arquivo_id: Optional[int] = None

    model_config = {"from_attributes": True}


class ArquivoResposta(BaseModel):
    id: int
    nome_arquivo: str
    data_upload: date

    model_config = {"from_attributes": True}


class ImportacaoResposta(BaseModel):
    status: str
    mensagem: str
    registros_afetados: int
    arquivo_id: int


class StatsResposta(BaseModel):
    total_registros: int
    total_valor: float
    maior_venda: float
    media_diaria: float
    total_arquivos: int
    ultimo_upload: Optional[str]
