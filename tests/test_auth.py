def test_cadastro_sucesso(client):
    r = client.post("/auth/cadastro", json={"nome": "Alice", "email": "alice@test.com", "senha": "senha123"})
    assert r.status_code == 201
    assert r.json()["email"] == "alice@test.com"


def test_cadastro_email_duplicado(client):
    dados = {"nome": "Bob", "email": "bob@test.com", "senha": "senha123"}
    client.post("/auth/cadastro", json=dados)
    r = client.post("/auth/cadastro", json=dados)
    assert r.status_code == 400


def test_cadastro_senha_curta(client):
    r = client.post("/auth/cadastro", json={"nome": "Carol", "email": "carol@test.com", "senha": "123"})
    assert r.status_code == 422


def test_login_valido(client):
    client.post("/auth/cadastro", json={"nome": "Dave", "email": "dave@test.com", "senha": "senha123"})
    r = client.post("/auth/login", json={"email": "dave@test.com", "senha": "senha123"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["usuario"]["email"] == "dave@test.com"


def test_login_senha_errada(client):
    client.post("/auth/cadastro", json={"nome": "Eve", "email": "eve@test.com", "senha": "correta123"})
    r = client.post("/auth/login", json={"email": "eve@test.com", "senha": "errada"})
    assert r.status_code == 401


def test_login_usuario_inexistente(client):
    r = client.post("/auth/login", json={"email": "nao@existe.com", "senha": "qualquer"})
    assert r.status_code == 401


def test_obter_perfil(client, auth_headers):
    r = client.get("/auth/me", headers=auth_headers)
    assert r.status_code == 200
    assert "id" in r.json()


def test_obter_perfil_sem_token(client):
    r = client.get("/auth/me")
    assert r.status_code == 403


def test_atualizar_nome(client, auth_headers):
    r = client.put("/auth/me", json={"nome": "Novo Nome"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["nome"] == "Novo Nome"


def test_deletar_conta(client, auth_headers):
    r = client.delete("/auth/me", headers=auth_headers)
    assert r.status_code == 204
    r2 = client.get("/auth/me", headers=auth_headers)
    assert r2.status_code == 401
