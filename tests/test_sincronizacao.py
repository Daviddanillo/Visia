"""Testes da sincronização de pasta do computador com o aplicativo."""

import os


_CSV = "data,valor\n2024-01-01,100\n2024-01-02,200\n"


def _escrever(caminho, conteudo=_CSV):
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write(conteudo)


def _envelhecer(caminho, delta=10):
    """Empurra o mtime do arquivo para frente, garantindo detecção de mudança."""
    agora = os.path.getmtime(caminho)
    os.utime(caminho, (agora + delta, agora + delta))


def test_registrar_pasta_importa_csvs(client, auth_headers, tmp_path):
    _escrever(tmp_path / "vendas.csv")
    sub = tmp_path / "2024"
    sub.mkdir()
    _escrever(sub / "janeiro.csv")
    # arquivo não-CSV deve ser ignorado
    _escrever(tmp_path / "leiame.txt", "nada")

    r = client.post("/vendas/sincronizacao", json={"caminho": str(tmp_path)}, headers=auth_headers)
    assert r.status_code == 201, r.text
    assert r.json()["criados"] == 2

    arquivos = client.get("/vendas/arquivos", headers=auth_headers).json()
    assert len(arquivos) == 2
    assert all(a["caminho_origem"] for a in arquivos)

    # a raiz e a subpasta viram pastas espelhadas
    pastas = client.get("/vendas/pastas", headers=auth_headers).json()
    nomes = {p["nome"] for p in pastas}
    assert tmp_path.name in nomes
    assert "2024" in nomes


def test_caminho_inexistente_falha(client, auth_headers, tmp_path):
    r = client.post(
        "/vendas/sincronizacao",
        json={"caminho": str(tmp_path / "nao-existe")},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_pastas_sobrepostas_falham(client, auth_headers, tmp_path):
    sub = tmp_path / "interna"
    sub.mkdir()
    r1 = client.post("/vendas/sincronizacao", json={"caminho": str(tmp_path)}, headers=auth_headers)
    assert r1.status_code == 201
    r2 = client.post("/vendas/sincronizacao", json={"caminho": str(sub)}, headers=auth_headers)
    assert r2.status_code == 400


def test_atualizar_detecta_arquivo_novo(client, auth_headers, tmp_path):
    _escrever(tmp_path / "a.csv")
    client.post("/vendas/sincronizacao", json={"caminho": str(tmp_path)}, headers=auth_headers)

    _escrever(tmp_path / "b.csv")
    r = client.post("/vendas/sincronizacao/atualizar", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["criados"] == 1
    assert len(client.get("/vendas/arquivos", headers=auth_headers).json()) == 2


def test_atualizar_detecta_modificacao(client, auth_headers, tmp_path):
    alvo = tmp_path / "a.csv"
    _escrever(alvo)
    client.post("/vendas/sincronizacao", json={"caminho": str(tmp_path)}, headers=auth_headers)

    _escrever(alvo, "data,valor\n2024-03-01,999\n")
    _envelhecer(alvo)
    r = client.post("/vendas/sincronizacao/atualizar", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["atualizados"] == 1
    # não duplica o arquivo
    assert len(client.get("/vendas/arquivos", headers=auth_headers).json()) == 1


def test_atualizar_remove_arquivo_apagado(client, auth_headers, tmp_path):
    alvo = tmp_path / "a.csv"
    _escrever(alvo)
    _escrever(tmp_path / "b.csv")
    client.post("/vendas/sincronizacao", json={"caminho": str(tmp_path)}, headers=auth_headers)

    os.remove(alvo)
    r = client.post("/vendas/sincronizacao/atualizar", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["removidos"] == 1
    assert len(client.get("/vendas/arquivos", headers=auth_headers).json()) == 1


def test_atualizar_remove_subpasta_apagada(client, auth_headers, tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    _escrever(sub / "x.csv")
    client.post("/vendas/sincronizacao", json={"caminho": str(tmp_path)}, headers=auth_headers)
    assert len(client.get("/vendas/arquivos", headers=auth_headers).json()) == 1

    os.remove(sub / "x.csv")
    os.rmdir(sub)
    r = client.post("/vendas/sincronizacao/atualizar", headers=auth_headers)
    assert r.status_code == 200
    assert len(client.get("/vendas/arquivos", headers=auth_headers).json()) == 0
    nomes = {p["nome"] for p in client.get("/vendas/pastas", headers=auth_headers).json()}
    assert "sub" not in nomes


def test_listar_sincronizacao(client, auth_headers, tmp_path):
    _escrever(tmp_path / "a.csv")
    client.post("/vendas/sincronizacao", json={"caminho": str(tmp_path)}, headers=auth_headers)
    r = client.get("/vendas/sincronizacao", headers=auth_headers)
    assert r.status_code == 200
    dados = r.json()
    assert len(dados) == 1
    assert dados[0]["total_arquivos"] == 1
    assert dados[0]["origem_ausente"] is False


def test_remover_sincronizacao_apaga_espelho(client, auth_headers, tmp_path):
    _escrever(tmp_path / "a.csv")
    client.post("/vendas/sincronizacao", json={"caminho": str(tmp_path)}, headers=auth_headers)
    raiz = client.get("/vendas/sincronizacao", headers=auth_headers).json()[0]

    r = client.delete(f"/vendas/sincronizacao/{raiz['id']}", headers=auth_headers)
    assert r.status_code == 204
    assert client.get("/vendas/sincronizacao", headers=auth_headers).json() == []
    assert client.get("/vendas/arquivos", headers=auth_headers).json() == []


def test_remover_sincronizacao_mantendo_dados(client, auth_headers, tmp_path):
    _escrever(tmp_path / "a.csv")
    client.post("/vendas/sincronizacao", json={"caminho": str(tmp_path)}, headers=auth_headers)
    raiz = client.get("/vendas/sincronizacao", headers=auth_headers).json()[0]

    r = client.delete(
        f"/vendas/sincronizacao/{raiz['id']}?manter_dados=true", headers=auth_headers
    )
    assert r.status_code == 204
    arquivos = client.get("/vendas/arquivos", headers=auth_headers).json()
    assert len(arquivos) == 1
    # dados mantidos, mas desvinculados da origem
    assert arquivos[0]["caminho_origem"] is None
