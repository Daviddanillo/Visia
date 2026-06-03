import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from sqlalchemy import inspect, text

import app.models  # noqa: F401 — registra modelos no metadata do SQLAlchemy
from app.core.config import settings
from app.core.ratelimit import limiter
from app.db.database import Base, engine
from app.routers import auth_router, predict_router, venda_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(name)s — %(message)s")

Base.metadata.create_all(bind=engine)


def _migrar_coluna_categoria() -> None:
    """Adiciona a coluna `categoria` à tabela `vendas` em bancos já existentes.

    `create_all` não altera tabelas existentes, então fazemos um ALTER TABLE
    idempotente para manter compatibilidade com bancos antigos (dados.db).
    """
    try:
        inspetor = inspect(engine)
        colunas = {c["name"] for c in inspetor.get_columns("vendas")}
        if "categoria" not in colunas:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE vendas ADD COLUMN categoria VARCHAR"))
            logging.info("Migração: coluna 'categoria' adicionada à tabela 'vendas'.")
    except Exception as exc:  # pragma: no cover — best-effort
        logging.warning("Não foi possível migrar a coluna 'categoria': %s", exc)


def _migrar_coluna_pasta_id() -> None:
    """Adiciona a coluna `pasta_id` à tabela `uploads_arquivos` (bancos antigos).

    A tabela `pastas` é criada por `create_all`; aqui garantimos que arquivos
    importados antes da feature de organização ganhem a coluna de pasta.
    """
    try:
        inspetor = inspect(engine)
        colunas = {c["name"] for c in inspetor.get_columns("uploads_arquivos")}
        if "pasta_id" not in colunas:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE uploads_arquivos ADD COLUMN pasta_id INTEGER"))
            logging.info("Migração: coluna 'pasta_id' adicionada à tabela 'uploads_arquivos'.")
    except Exception as exc:  # pragma: no cover — best-effort
        logging.warning("Não foi possível migrar a coluna 'pasta_id': %s", exc)


def _migrar_colunas_sincronizacao() -> None:
    """Adiciona as colunas de sincronização de pastas do disco em bancos antigos.

    `create_all` cria a tabela `raizes_sincronizadas`, mas não altera as tabelas
    `pastas`/`uploads_arquivos` já existentes; aqui garantimos as novas colunas.
    """
    alteracoes = [
        ("pastas", "caminho_origem", "VARCHAR"),
        ("uploads_arquivos", "caminho_origem", "VARCHAR"),
        ("uploads_arquivos", "mtime_origem", "FLOAT"),
    ]
    try:
        inspetor = inspect(engine)
        for tabela, coluna, tipo in alteracoes:
            colunas = {c["name"] for c in inspetor.get_columns(tabela)}
            if coluna not in colunas:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}"))
                logging.info("Migração: coluna '%s' adicionada à tabela '%s'.", coluna, tabela)
    except Exception as exc:  # pragma: no cover — best-effort
        logging.warning("Não foi possível migrar colunas de sincronização: %s", exc)


_migrar_coluna_categoria()
_migrar_coluna_pasta_id()
_migrar_colunas_sincronizacao()

app = FastAPI(
    title="Visia Intelligence API",
    description="Previsão inteligente de vendas com sazonalidade e feriados brasileiros.",
    version="2.0.0",
)

# Rate limiting (proteção contra força bruta — ver app/core/ratelimit.py)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# A UI é servida pelo próprio app (mesma origem), mas para clientes externos da
# API liberamos as origens configuradas + a URL pública do Render, se houver.
_origens = list(settings.origens_permitidas)
_render_url = os.environ.get("RENDER_EXTERNAL_URL")
if _render_url and _render_url not in _origens:
    _origens.append(_render_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origens,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(venda_router.router)
app.include_router(predict_router.router)


@app.get("/health", tags=["Monitoramento"])
def health_check():
    return {"status": "healthy", "version": app.version}


_frontend = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
if os.path.exists(_frontend):
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
