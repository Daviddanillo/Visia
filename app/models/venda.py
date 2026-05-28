from sqlalchemy import Column, Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.database import Base


class UploadArquivo(Base):
    __tablename__ = "uploads_arquivos"

    id = Column(Integer, primary_key=True, index=True)
    nome_arquivo = Column(String, nullable=False)
    data_upload = Column(Date, nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)

    usuario = relationship("Usuario", back_populates="arquivos")
    vendas = relationship("Venda", back_populates="arquivo", cascade="all, delete-orphan")


class Venda(Base):
    __tablename__ = "vendas"

    id = Column(Integer, primary_key=True, index=True)
    data_venda = Column(Date, nullable=False)
    valor = Column(Float, nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    arquivo_id = Column(Integer, ForeignKey("uploads_arquivos.id"), nullable=True)

    usuario = relationship("Usuario", back_populates="vendas")
    arquivo = relationship("UploadArquivo", back_populates="vendas")
