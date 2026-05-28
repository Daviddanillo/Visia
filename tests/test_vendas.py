def test_criar_venda(client, auth_headers):
    r = client.post("/vendas/", json={"data_venda": "2024-01-15", "valor": 150.0}, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["valor"] == 150.0


def test_criar_venda_valor_invalido(client, auth_headers):
    r = client.post("/vendas/", json={"data_venda": "2024-01-15", "valor": -10.0}, headers=auth_headers)
    assert r.status_code == 422


def test_listar_vendas(client, auth_headers):
    client.post("/vendas/", json={"data_venda": "2024-01-10", "valor": 100.0}, headers=auth_headers)
    client.post("/vendas/", json={"data_venda": "2024-01-11", "valor": 200.0}, headers=auth_headers)
    r = client.get("/vendas/", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_listar_vendas_sem_token(client):
    r = client.get("/vendas/")
    assert r.status_code == 403


def test_obter_venda(client, auth_headers):
    criado = client.post("/vendas/", json={"data_venda": "2024-02-01", "valor": 300.0}, headers=auth_headers).json()
    r = client.get(f"/vendas/{criado['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == criado["id"]


def test_obter_venda_inexistente(client, auth_headers):
    r = client.get("/vendas/99999", headers=auth_headers)
    assert r.status_code == 404


def test_atualizar_venda(client, auth_headers):
    criado = client.post("/vendas/", json={"data_venda": "2024-03-01", "valor": 100.0}, headers=auth_headers).json()
    r = client.put(f"/vendas/{criado['id']}", json={"valor": 500.0}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["valor"] == 500.0


def test_deletar_venda(client, auth_headers):
    criado = client.post("/vendas/", json={"data_venda": "2024-04-01", "valor": 100.0}, headers=auth_headers).json()
    r = client.delete(f"/vendas/{criado['id']}", headers=auth_headers)
    assert r.status_code == 204
    r2 = client.get(f"/vendas/{criado['id']}", headers=auth_headers)
    assert r2.status_code == 404


def test_isolamento_entre_usuarios(client):
    client.post("/auth/cadastro", json={"nome": "U1", "email": "u1@test.com", "senha": "senha123"})
    client.post("/auth/cadastro", json={"nome": "U2", "email": "u2@test.com", "senha": "senha123"})
    t1 = client.post("/auth/login", json={"email": "u1@test.com", "senha": "senha123"}).json()["access_token"]
    t2 = client.post("/auth/login", json={"email": "u2@test.com", "senha": "senha123"}).json()["access_token"]
    h1 = {"Authorization": f"Bearer {t1}"}
    h2 = {"Authorization": f"Bearer {t2}"}
    venda = client.post("/vendas/", json={"data_venda": "2024-05-01", "valor": 999.0}, headers=h1).json()
    r = client.get(f"/vendas/{venda['id']}", headers=h2)
    assert r.status_code == 404


def test_stats(client, auth_headers):
    client.post("/vendas/", json={"data_venda": "2024-06-01", "valor": 200.0}, headers=auth_headers)
    r = client.get("/vendas/stats", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total_registros"] == 1
    assert data["total_valor"] == 200.0


def test_stats_sem_dados(client, auth_headers):
    r = client.get("/vendas/stats", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["total_registros"] == 0


def test_listar_arquivos_vazio(client, auth_headers):
    r = client.get("/vendas/arquivos", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_deletar_arquivo_inexistente(client, auth_headers):
    r = client.delete("/vendas/arquivos/99999", headers=auth_headers)
    assert r.status_code == 404
