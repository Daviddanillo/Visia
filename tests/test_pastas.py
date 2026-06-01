"""Testes da organização em pastas (criar, aninhar, mover, renomear, excluir)."""

import io


def _importar_csv(client, auth_headers, nome="vendas.csv"):
    csv = "data,valor\n2024-01-01,100\n2024-01-02,200\n"
    r = client.post(
        "/vendas/importar-csv",
        files={"file": (nome, io.BytesIO(csv.encode()), "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 201
    return r.json()["arquivo_id"]


def test_criar_e_listar_pasta(client, auth_headers):
    r = client.post("/vendas/pastas", json={"nome": "2024"}, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["nome"] == "2024"
    assert r.json()["parent_id"] is None

    r = client.get("/vendas/pastas", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_pasta_aninhada(client, auth_headers):
    pai = client.post("/vendas/pastas", json={"nome": "Pai"}, headers=auth_headers).json()
    r = client.post(
        "/vendas/pastas", json={"nome": "Filha", "parent_id": pai["id"]}, headers=auth_headers
    )
    assert r.status_code == 201
    assert r.json()["parent_id"] == pai["id"]


def test_pasta_pai_inexistente(client, auth_headers):
    r = client.post("/vendas/pastas", json={"nome": "X", "parent_id": 9999}, headers=auth_headers)
    assert r.status_code == 404


def test_renomear_pasta(client, auth_headers):
    p = client.post("/vendas/pastas", json={"nome": "Antigo"}, headers=auth_headers).json()
    r = client.put(f"/vendas/pastas/{p['id']}", json={"nome": "Novo"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["nome"] == "Novo"


def test_mover_pasta_para_dentro_de_si_mesma_falha(client, auth_headers):
    pai = client.post("/vendas/pastas", json={"nome": "Pai"}, headers=auth_headers).json()
    filha = client.post(
        "/vendas/pastas", json={"nome": "Filha", "parent_id": pai["id"]}, headers=auth_headers
    ).json()
    # mover o pai para dentro da filha (descendente) deve falhar
    r = client.put(
        f"/vendas/pastas/{pai['id']}", json={"parent_id": filha["id"]}, headers=auth_headers
    )
    assert r.status_code == 400


def test_mover_arquivo_para_pasta_e_de_volta(client, auth_headers):
    aid = _importar_csv(client, auth_headers)
    p = client.post("/vendas/pastas", json={"nome": "Pasta"}, headers=auth_headers).json()

    r = client.put(f"/vendas/arquivos/{aid}", json={"pasta_id": p["id"]}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["pasta_id"] == p["id"]

    # voltar para a raiz (pasta_id=None informado explicitamente)
    r = client.put(f"/vendas/arquivos/{aid}", json={"pasta_id": None}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["pasta_id"] is None


def test_renomear_arquivo(client, auth_headers):
    aid = _importar_csv(client, auth_headers)
    r = client.put(
        f"/vendas/arquivos/{aid}", json={"nome_arquivo": "renomeado.csv"}, headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["nome_arquivo"] == "renomeado.csv"


def test_excluir_pasta_devolve_arquivos_para_raiz(client, auth_headers):
    aid = _importar_csv(client, auth_headers)
    p = client.post("/vendas/pastas", json={"nome": "Pasta"}, headers=auth_headers).json()
    client.put(f"/vendas/arquivos/{aid}", json={"pasta_id": p["id"]}, headers=auth_headers)

    r = client.delete(f"/vendas/pastas/{p['id']}", headers=auth_headers)
    assert r.status_code == 204

    # arquivo preservado e de volta à raiz
    arqs = client.get("/vendas/arquivos", headers=auth_headers).json()
    alvo = next(a for a in arqs if a["id"] == aid)
    assert alvo["pasta_id"] is None


def test_excluir_pasta_remove_subpastas(client, auth_headers):
    pai = client.post("/vendas/pastas", json={"nome": "Pai"}, headers=auth_headers).json()
    client.post("/vendas/pastas", json={"nome": "Filha", "parent_id": pai["id"]}, headers=auth_headers)

    client.delete(f"/vendas/pastas/{pai['id']}", headers=auth_headers)
    assert client.get("/vendas/pastas", headers=auth_headers).json() == []
