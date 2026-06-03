import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.ratelimit import limiter
from app.db.database import Base, get_db
from app.main import app

# Desliga o rate limiting na suíte de testes: a fixture auth_headers faz
# cadastro+login a cada teste, o que estouraria os limites (5/min, 10/min) e
# retornaria 429 em vez do token. O slowapi consulta esta flag a cada
# requisição, então desativá-la aqui basta (não testamos o limitador em si).
limiter.enabled = False

_engine = create_engine(
    "sqlite:///./test.db",
    connect_args={"check_same_thread": False},
)
_TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    client.post("/auth/cadastro", json={"nome": "Teste", "email": "teste@visia.com", "senha": "senha123"})
    r = client.post("/auth/login", json={"email": "teste@visia.com", "senha": "senha123"})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
