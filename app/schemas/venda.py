from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class VendaCriar(BaseModel):
    data_venda: date
    valor: float = Field(..., gt=0, description="Valor da venda em R$")
    categoria: Optional[str] = Field(None, description="Categoria/produto da venda")


class VendaAtualizar(BaseModel):
    data_venda: Optional[date] = None
    valor: Optional[float] = Field(None, gt=0)
    categoria: Optional[str] = None


class VendaResposta(BaseModel):
    id: int
    usuario_id: int
    data_venda: date
    valor: float
    categoria: Optional[str] = None
    arquivo_id: Optional[int] = None

    model_config = {"from_attributes": True}


class CategoriaResposta(BaseModel):
    categoria: str
    total_registros: int
    total_valor: float


class ArquivoResposta(BaseModel):
    id: int
    nome_arquivo: str
    data_upload: date
    pasta_id: Optional[int] = None

    model_config = {"from_attributes": True}


class ArquivoAtualizar(BaseModel):
    """Renomeia (`nome_arquivo`) e/ou move (`pasta_id`) um arquivo.

    `pasta_id=None` movido explicitamente para a raiz; usar
    ``model_fields_set`` para distinguir 'não informado' de 'mover p/ raiz'.
    """

    nome_arquivo: Optional[str] = None
    pasta_id: Optional[int] = None


class PastaCriar(BaseModel):
    nome: str = Field(..., min_length=1, max_length=120)
    parent_id: Optional[int] = None


class PastaAtualizar(BaseModel):
    nome: Optional[str] = Field(None, min_length=1, max_length=120)
    parent_id: Optional[int] = None


class PastaResposta(BaseModel):
    id: int
    nome: str
    parent_id: Optional[int] = None

    model_config = {"from_attributes": True}


class ImportacaoResposta(BaseModel):
    status: str
    mensagem: str
    registros_afetados: int
    arquivo_id: int
    tem_categorias: bool = False
    categorias_detectadas: list[str] = []
    coluna_valor_detectada: Optional[str] = None
    coluna_categoria_detectada: Optional[str] = None


class StatsResposta(BaseModel):
    total_registros: int
    total_valor: float
    maior_venda: float
    media_diaria: float
    total_arquivos: int
    ultimo_upload: Optional[str]
