import pytest


def _prophet_treina() -> bool:
    """O Prophet precisa de um backend Stan compilado para treinar; em alguns
    ambientes ele vem quebrado. Detecta isso uma vez para pular apenas os
    testes que realmente treinam o modelo (os demais seguem rodando)."""
    try:
        import pandas as pd
        from prophet import Prophet

        modelo = Prophet()
        modelo.fit(pd.DataFrame({
            "ds": pd.date_range("2024-01-01", periods=10),
            "y": list(range(10)),
        }))
        return True
    except Exception:
        return False


prophet_necessario = pytest.mark.skipif(
    not _prophet_treina(),
    reason="Backend Stan do Prophet indisponível neste ambiente.",
)


def test_previsao_sem_dados(client, auth_headers):
    r = client.get("/predict/", headers=auth_headers)
    assert r.status_code == 400
    assert "insuficientes" in r.json()["detail"].lower()


def test_previsao_dados_insuficientes(client, auth_headers):
    for i in range(1, 4):
        client.post("/vendas/", json={"data_venda": f"2024-01-{i:02d}", "valor": 100.0}, headers=auth_headers)
    r = client.get("/predict/", headers=auth_headers)
    assert r.status_code == 400


@prophet_necessario
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


@prophet_necessario
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
