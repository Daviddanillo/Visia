from sqlalchemy import Column, Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.database import Base


class Pasta(Base):
    """Pasta de organização. Suporta aninhamento via ``parent_id`` (auto-FK)."""

    __tablename__ = "pastas"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    # Pasta-mãe. NULL → pasta na raiz.
    parent_id = Column(Integer, ForeignKey("pastas.id"), nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)

    usuario = relationship("Usuario", back_populates="pastas")
    parent = relationship("Pasta", remote_side=[id], back_populates="subpastas")
    subpastas = relationship(
        "Pasta", back_populates="parent", cascade="all, delete-orphan"
    )
    arquivos = relationship("UploadArquivo", back_populates="pasta")


class UploadArquivo(Base):
    __tablename__ = "uploads_arquivos"

    id = Column(Integer, primary_key=True, index=True)
    nome_arquivo = Column(String, nullable=False)
    data_upload = Column(Date, nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    # Pasta onde o arquivo está organizado. NULL → raiz (não organizado).
    pasta_id = Column(Integer, ForeignKey("pastas.id"), nullable=True)

    usuario = relationship("Usuario", back_populates="arquivos")
    pasta = relationship("Pasta", back_populates="arquivos")
    vendas = relationship("Venda", back_populates="arquivo", cascade="all, delete-orphan")


class Venda(Base):
    __tablename__ = "vendas"

    id = Column(Integer, primary_key=True, index=True)
    data_venda = Column(Date, nullable=False)
    valor = Column(Float, nullable=False)
    # Categoria/produto da venda (ex.: "Chocolate", "Flores").
    # Nullable → arquivos que só têm números continuam funcionando normalmente.
    categoria = Column(String, nullable=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    arquivo_id = Column(Integer, ForeignKey("uploads_arquivos.id"), nullable=True)

    usuario = relationship("Usuario", back_populates="vendas")
    arquivo = relationship("UploadArquivo", back_populates="vendas")
