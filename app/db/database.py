from urllib.parse import parse_qs, urlparse

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings


def _normalizar_url(url: str) -> str:
    """Deixa a DATABASE_URL pronta para o SQLAlchemy 2.x e para o Neon.

    - O Neon (e outros provedores) fornecem URLs com o esquema legado
      ``postgres://``, que o SQLAlchemy 2.x não aceita — trocamos por
      ``postgresql://``.
    - O Neon só aceita conexões TLS; se a URL não trouxer ``sslmode``,
      acrescentamos ``sslmode=require`` (hosts locais ficam de fora para
      não quebrar um PostgreSQL de desenvolvimento sem TLS).
    """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    if url.startswith("postgresql"):
        parsed = urlparse(url)
        host = parsed.hostname or ""
        sem_sslmode = "sslmode" not in parse_qs(parsed.query)
        if sem_sslmode and host not in ("localhost", "127.0.0.1", "db"):
            url += ("&" if parsed.query else "?") + "sslmode=require"

    return url


_url = _normalizar_url(settings.DATABASE_URL)
_is_sqlite = _url.startswith("sqlite")

if _is_sqlite:
    # `timeout` faz o driver aguardar o bloqueio ser liberado em vez de já falhar
    # com "database is locked" quando há escrita e leitura simultâneas (sincronização).
    engine = create_engine(_url, connect_args={"check_same_thread": False, "timeout": 30})
else:
    # PostgreSQL (Neon): o compute serverless suspende após inatividade e
    # derruba as conexões abertas. `pool_pre_ping` testa a conexão antes de
    # usá-la (reconecta em vez de estourar erro) e `pool_recycle` descarta
    # conexões paradas antes de o Neon encerrá-las por timeout.
    engine = create_engine(
        _url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=5,
    )


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
