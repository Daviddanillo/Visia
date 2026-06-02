from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.db.database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    senha_hash = Column(String, nullable=False)

    vendas = relationship("Venda", back_populates="usuario", cascade="all, delete-orphan")
    arquivos = relationship("UploadArquivo", back_populates="usuario", cascade="all, delete-orphan")
    pastas = relationship("Pasta", back_populates="usuario", cascade="all, delete-orphan")
    raizes_sincronizadas = relationship(
        "RaizSincronizada", back_populates="usuario", cascade="all, delete-orphan"
    )
