def test_previsao_sem_dados(client, auth_headers):
    r = client.get("/predict/", headers=auth_headers)
    assert r.status_code == 400
    assert "insuficientes" in r.json()["detail"].lower()


def test_previsao_dados_insuficientes(client, auth_headers):
    for i in range(1, 4):
        client.post("/vendas/", json={"data_venda": f"2024-01-{i:02d}", "valor": 100.0}, headers=auth_headers)
    r = client.get("/predict/", headers=auth_headers)
    assert r.status_code == 400


def test_previsao_com_dados_suficientes(client, auth_headers):
    for i in range(1, 16):
        client.post("/vendas/", json={"data_venda": f"2024-01-{i:02d}", "valor": float(100 + i * 10)}, headers=auth_headers)
    r = client.get("/predict/?dias=7", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "forecast" in data
    assert "historico" in data
    assert "componentes" in data
    assert "resumo" in data
    assert len(data["forecast"]) == 7


def test_previsao_sem_token(client):
    r = client.get("/predict/")
    assert r.status_code == 403


def test_previsao_estrutura_forecast(client, auth_headers):
    for i in range(1, 16):
        client.post("/vendas/", json={"data_venda": f"2024-02-{i:02d}", "valor": float(50 + i * 5)}, headers=auth_headers)
    r = client.get("/predict/?dias=5", headers=auth_headers)
    assert r.status_code == 200
    primeiro = r.json()["forecast"][0]
    assert "ds" in primeiro
    assert "yhat" in primeiro
    assert "yhat_lower" in primeiro
    assert "yhat_upper" in primeiro
    assert "dia_semana" in primeiro
    assert "is_holiday" in primeiro
