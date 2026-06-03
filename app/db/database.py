from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

# Render/Heroku expõem a URL como "postgres://"; o SQLAlchemy 2.0 exige
# "postgresql://". Normaliza para não quebrar o deploy.
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)

_is_sqlite = _db_url.startswith("sqlite")
# `timeout` faz o driver aguardar o bloqueio ser liberado em vez de já falhar
# com "database is locked" quando há escrita e leitura simultâneas (sincronização).
_connect_args = {"check_same_thread": False, "timeout": 30} if _is_sqlite else {}

# pool_pre_ping evita erros com conexões ociosas derrubadas pelo Postgres gerenciado.
engine = create_engine(_db_url, connect_args=_connect_args, pool_pre_ping=True)


if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _configurar_sqlite(dbapi_conn, _record):
        """WAL permite leituras concorrentes com uma escrita (ex.: dashboard
        carregando enquanto a sincronização grava), reduzindo 'database is locked'."""
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
