import io
import logging
import os
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.database import get_db
from app.models.usuario import Usuario
from app.models.venda import Pasta, RaizSincronizada, UploadArquivo, Venda
from app.schemas.venda import (
    ArquivoAtualizar,
    ArquivoResposta,
    CategoriaResposta,
    DialogoPastaResposta,
    ImportacaoResposta,
    PastaAtualizar,
    PastaCriar,
    PastaResposta,
    RaizCriar,
    RaizResposta,
    SincronizacaoResposta,
    StatsResposta,
    VendaAtualizar,
    VendaCriar,
    VendaResposta,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/vendas", tags=["Vendas"])

_SINONIMOS_DATA = {
    "shipping_limit_date", "order_purchase_timestamp", "order_approved_at",
    "data_venda", "data", "date", "ds", "dia",
}
_SINONIMOS_VALOR = {
    "price", "payment_value", "valor", "venda", "vendas", "y", "total", "preco",
    "faturamento", "receita", "amount", "revenue", "monto",
}
# Categoria / produto vendido (flor, chocolate, etc.)
_SINONIMOS_CATEGORIA = {
    "categoria", "category", "produto", "product", "item", "tipo", "type",
    "nome_produto", "product_name", "product_category", "departamento",
    "department", "segmento", "linha", "grupo", "setor", "sku", "descricao",
    "description", "nome",
}
# Quantidade vendida — usada como peso quando não há coluna de valor monetário
_SINONIMOS_QUANTIDADE = {
    "quantidade", "qtd", "qtde", "quantity", "qty", "unidades", "units", "volume",
}

# Sinônimos que NÃO devem ser confundidos com categoria (identificadores, etc.)
_BLOQUEIO_CATEGORIA = {"order_id", "customer_id", "id_", "_id", "cpf", "cnpj"}


def _detectar_coluna(
    colunas: list,
    sinonimos: set,
    bloqueio: Optional[set] = None,
    excluir: Optional[set] = None,
) -> Optional[str]:
    bloqueio = bloqueio or set()
    excluir  = excluir or set()
    for c in colunas:
        if c in excluir:
            continue
        if any(b in c for b in bloqueio):
            continue
        if any(s in c for s in sinonimos):
            return c
    return None


def _limpar_valor(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(
        serie.astype(str)
            .str.replace("R$", "", regex=False)
            .str.replace(" ", "", regex=False)
            .str.replace(r"\.(?=\d{3})", "", regex=True)
            .str.replace(",", ".", regex=False),
        errors="coerce",
    )


# ── Parsing de CSV (reutilizado por upload e por sincronização de pasta) ──────

def _parse_csv(conteudo: bytes) -> pd.DataFrame:
    """Lê os bytes de um CSV em DataFrame, detectando o separador automaticamente."""
    try:
        df = pd.read_csv(io.BytesIO(conteudo), sep=None, engine="python")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Arquivo CSV inválido: {exc}")
    if df.empty:
        raise HTTPException(status_code=400, detail="O arquivo está vazio.")
    return df


def _consolidar(df: pd.DataFrame) -> Tuple[pd.DataFrame, bool, list, Optional[str], Optional[str]]:
    """Normaliza colunas, detecta data/valor/categoria e consolida por dia.

    Retorna ``(consolidado, tem_categorias, categorias_detectadas,
    col_valor_detectada, col_categoria_detectada)``.
    """
    df = df.copy()
    df.columns = [str(c).strip().lower().replace('"', "").replace("'", "") for c in df.columns]
    cols = df.columns.tolist()
    # A coluna de data é detectada primeiro e excluída das demais buscas — assim
    # nomes como "data_venda" não são confundidos com a coluna de valor ("venda").
    col_data       = _detectar_coluna(cols, _SINONIMOS_DATA)
    ja_usadas      = {col_data} if col_data else set()
    col_valor      = _detectar_coluna(cols, _SINONIMOS_VALOR, excluir=ja_usadas)
    if col_valor:
        ja_usadas = ja_usadas | {col_valor}
    col_quantidade = _detectar_coluna(cols, _SINONIMOS_QUANTIDADE, excluir=ja_usadas)
    if col_quantidade:
        ja_usadas = ja_usadas | {col_quantidade}
    col_categoria  = _detectar_coluna(
        cols, _SINONIMOS_CATEGORIA, bloqueio=_BLOQUEIO_CATEGORIA, excluir=ja_usadas
    )

    trabalho = pd.DataFrame()
    trabalho["data_venda"] = (
        pd.to_datetime(df[col_data], errors="coerce").dt.date
        if col_data else datetime.now().date()
    )

    # ── Valor: prioriza coluna monetária; senão usa quantidade; senão peso unitário ──
    if col_valor:
        trabalho["valor"] = (
            _limpar_valor(df[col_valor])
            if df[col_valor].dtype == object
            else pd.to_numeric(df[col_valor], errors="coerce")
        )
    elif col_quantidade:
        logger.info("Sem coluna de valor; usando quantidade '%s' como métrica.", col_quantidade)
        trabalho["valor"] = pd.to_numeric(df[col_quantidade], errors="coerce")
    else:
        logger.warning("Coluna de valor não detectada. Usando peso unitário 1.0 por linha.")
        trabalho["valor"] = 1.0

    # ── Categoria: opcional. Se ausente, o sistema funciona só com números ──
    tem_categorias = col_categoria is not None
    if tem_categorias:
        trabalho["categoria"] = (
            df[col_categoria].astype(str).str.strip().replace({"": None, "nan": None})
        )
    else:
        trabalho["categoria"] = None

    trabalho["data_venda"] = trabalho["data_venda"].fillna(datetime.now().date())
    trabalho["valor"]      = trabalho["valor"].fillna(0.0)

    # ── Consolida por dia (+ categoria, quando houver) ──
    if tem_categorias:
        trabalho["categoria"] = trabalho["categoria"].fillna("Sem categoria")
        consolidado = (
            trabalho.groupby(["data_venda", "categoria"])["valor"].sum().reset_index()
        )
        categorias_detectadas = sorted(
            c for c in consolidado["categoria"].unique() if c and c != "Sem categoria"
        )[:50]
    else:
        consolidado = trabalho.groupby("data_venda")["valor"].sum().reset_index()
        consolidado["categoria"] = None
        categorias_detectadas = []

    return consolidado, tem_categorias, categorias_detectadas, (col_valor or col_quantidade), col_categoria


def _inserir_vendas(arquivo: UploadArquivo, consolidado: pd.DataFrame, usuario: Usuario, db: Session) -> None:
    """Insere as linhas consolidadas como vendas vinculadas ao arquivo."""
    db.bulk_insert_mappings(
        Venda,
        [
            {
                "data_venda": row.data_venda,
                "valor":      float(row.valor),
                "categoria":  row.categoria,
                "usuario_id": usuario.id,
                "arquivo_id": arquivo.id,
            }
            for row in consolidado.itertuples(index=False)
        ],
    )


# ── Arquivos (definidos antes de /{venda_id} para evitar conflito de rota) ────

@router.get("/arquivos", response_model=List[ArquivoResposta])
def listar_arquivos(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    return (
        db.query(UploadArquivo)
        .filter(UploadArquivo.usuario_id == usuario.id)
        .order_by(UploadArquivo.id.desc())
        .all()
    )


@router.put("/arquivos/{arquivo_id}", response_model=ArquivoResposta)
def atualizar_arquivo(
    arquivo_id: int,
    dados: ArquivoAtualizar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Renomeia e/ou move (organiza em pasta) um arquivo importado."""
    arquivo = (
        db.query(UploadArquivo)
        .filter(UploadArquivo.id == arquivo_id, UploadArquivo.usuario_id == usuario.id)
        .first()
    )
    if not arquivo:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    informados = dados.model_fields_set
    if "nome_arquivo" in informados and dados.nome_arquivo is not None:
        nome = dados.nome_arquivo.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="O nome não pode ser vazio.")
        arquivo.nome_arquivo = nome
    if "pasta_id" in informados:
        arquivo.pasta_id = _validar_pasta_destino(dados.pasta_id, usuario, db)

    db.commit()
    db.refresh(arquivo)
    return arquivo


@router.delete("/arquivos/{arquivo_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_arquivo(
    arquivo_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    arquivo = (
        db.query(UploadArquivo)
        .filter(UploadArquivo.id == arquivo_id, UploadArquivo.usuario_id == usuario.id)
        .first()
    )
    if not arquivo:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    db.delete(arquivo)
    db.commit()


# ── Pastas (organização) ─────────────────────────────────────────────────────

def _validar_pasta_destino(
    pasta_id: Optional[int], usuario: Usuario, db: Session
) -> Optional[int]:
    """Valida que `pasta_id` (destino de um arquivo/pasta) pertence ao usuário."""
    if pasta_id is None:
        return None
    existe = (
        db.query(Pasta)
        .filter(Pasta.id == pasta_id, Pasta.usuario_id == usuario.id)
        .first()
    )
    if not existe:
        raise HTTPException(status_code=404, detail="Pasta de destino não encontrada.")
    return pasta_id


def _ids_descendentes(pasta_id: int, usuario: Usuario, db: Session) -> set:
    """Retorna o id da pasta + todos os ids descendentes (subpastas, recursivo)."""
    todas = (
        db.query(Pasta.id, Pasta.parent_id)
        .filter(Pasta.usuario_id == usuario.id)
        .all()
    )
    filhos: dict = {}
    for pid, parent in todas:
        filhos.setdefault(parent, []).append(pid)

    coletados: set = set()
    pilha = [pasta_id]
    while pilha:
        atual = pilha.pop()
        if atual in coletados:
            continue
        coletados.add(atual)
        pilha.extend(filhos.get(atual, []))
    return coletados


@router.get("/pastas", response_model=List[PastaResposta])
def listar_pastas(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    return (
        db.query(Pasta)
        .filter(Pasta.usuario_id == usuario.id)
        .order_by(Pasta.nome.asc())
        .all()
    )


@router.post("/pastas", response_model=PastaResposta, status_code=status.HTTP_201_CREATED)
def criar_pasta(
    dados: PastaCriar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="O nome da pasta não pode ser vazio.")
    parent_id = _validar_pasta_destino(dados.parent_id, usuario, db)
    pasta = Pasta(nome=nome, parent_id=parent_id, usuario_id=usuario.id)
    db.add(pasta)
    db.commit()
    db.refresh(pasta)
    return pasta


@router.put("/pastas/{pasta_id}", response_model=PastaResposta)
def atualizar_pasta(
    pasta_id: int,
    dados: PastaAtualizar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Renomeia e/ou move uma pasta (impede mover para dentro dela mesma)."""
    pasta = (
        db.query(Pasta)
        .filter(Pasta.id == pasta_id, Pasta.usuario_id == usuario.id)
        .first()
    )
    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")

    informados = dados.model_fields_set
    if "nome" in informados and dados.nome is not None:
        nome = dados.nome.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="O nome não pode ser vazio.")
        pasta.nome = nome
    if "parent_id" in informados:
        destino = _validar_pasta_destino(dados.parent_id, usuario, db)
        if destino is not None and destino in _ids_descendentes(pasta_id, usuario, db):
            raise HTTPException(
                status_code=400,
                detail="Não é possível mover uma pasta para dentro dela mesma.",
            )
        pasta.parent_id = destino

    db.commit()
    db.refresh(pasta)
    return pasta


@router.delete("/pastas/{pasta_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_pasta(
    pasta_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Remove a pasta e suas subpastas. Os arquivos CSV voltam para a raiz."""
    pasta = (
        db.query(Pasta)
        .filter(Pasta.id == pasta_id, Pasta.usuario_id == usuario.id)
        .first()
    )
    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")

    # Preserva os dados: arquivos da pasta e descendentes voltam para a raiz.
    ids = _ids_descendentes(pasta_id, usuario, db)
    db.query(UploadArquivo).filter(
        UploadArquivo.usuario_id == usuario.id,
        UploadArquivo.pasta_id.in_(ids),
    ).update({UploadArquivo.pasta_id: None}, synchronize_session=False)

    db.delete(pasta)  # cascade remove as subpastas
    db.commit()


# ── Sincronização com pasta do computador ────────────────────────────────────

def _norm(caminho: str) -> str:
    """Caminho absoluto e normalizado (preservando a capitalização original)."""
    return os.path.normpath(os.path.abspath(caminho))


def _sob(caminho: Optional[str], base: str) -> bool:
    """True se ``caminho`` é ``base`` ou está contido dentro de ``base``."""
    if not caminho:
        return False
    c = os.path.normcase(_norm(caminho))
    b = os.path.normcase(_norm(base))
    return c == b or c.startswith(b + os.sep)


def _nome_dir(caminho: str) -> str:
    """Nome exibível de um diretório (cai para o caminho em raízes de disco)."""
    return os.path.basename(caminho) or caminho


def _importar_arquivo_disco(
    caminho: str,
    pasta_id: Optional[int],
    usuario: Usuario,
    db: Session,
    arquivo: Optional[UploadArquivo] = None,
) -> UploadArquivo:
    """Importa/atualiza um CSV do disco, vinculando-o à pasta espelhada.

    Quando ``arquivo`` é informado, reimporta o conteúdo (apaga as vendas
    antigas e insere as novas), mantendo o mesmo registro.
    """
    with open(caminho, "rb") as fh:
        conteudo = fh.read()
    consolidado, *_ = _consolidar(_parse_csv(conteudo))
    nome  = os.path.basename(caminho)
    mtime = os.path.getmtime(caminho)

    if arquivo is None:
        arquivo = UploadArquivo(
            nome_arquivo=nome,
            data_upload=datetime.now().date(),
            usuario_id=usuario.id,
            pasta_id=pasta_id,
            caminho_origem=caminho,
            mtime_origem=mtime,
        )
        db.add(arquivo)
        db.flush()
    else:
        db.query(Venda).filter(Venda.arquivo_id == arquivo.id).delete(synchronize_session=False)
        arquivo.nome_arquivo   = nome
        arquivo.pasta_id       = pasta_id
        arquivo.caminho_origem = caminho
        arquivo.mtime_origem   = mtime

    _inserir_vendas(arquivo, consolidado, usuario, db)
    return arquivo


def _sincronizar_raiz(raiz: RaizSincronizada, usuario: Usuario, db: Session) -> dict:
    """Reflete no banco o estado atual da pasta do disco apontada por ``raiz``.

    Cria pastas/arquivos novos, reimporta os modificados (por data de
    modificação) e remove os que deixaram de existir no disco.
    """
    resultado = {"criados": 0, "atualizados": 0, "removidos": 0, "ausente": False}
    base = _norm(raiz.caminho)
    if not os.path.isdir(base):
        resultado["ausente"] = True
        return resultado

    # Espelhos já existentes pertencentes a esta raiz (indexados por caminho).
    pastas_mirror = {
        os.path.normcase(p.caminho_origem): p
        for p in db.query(Pasta).filter(
            Pasta.usuario_id == usuario.id, Pasta.caminho_origem.isnot(None)
        ).all()
        if _sob(p.caminho_origem, base)
    }
    arquivos_mirror = {
        os.path.normcase(a.caminho_origem): a
        for a in db.query(UploadArquivo).filter(
            UploadArquivo.usuario_id == usuario.id, UploadArquivo.caminho_origem.isnot(None)
        ).all()
        if _sob(a.caminho_origem, base)
    }

    vistos_pastas: set = set()
    vistos_arquivos: set = set()
    mapa_dir: dict = {}  # normcase(dir) -> Pasta

    # Pasta raiz do espelho.
    base_c = os.path.normcase(base)
    root_pasta = db.get(Pasta, raiz.pasta_id) if raiz.pasta_id else None
    if root_pasta is None:
        root_pasta = pastas_mirror.get(base_c)
    if root_pasta is None:
        root_pasta = Pasta(nome=_nome_dir(base), parent_id=None, usuario_id=usuario.id, caminho_origem=base)
        db.add(root_pasta)
        db.flush()
    root_pasta.nome           = _nome_dir(base)
    root_pasta.caminho_origem = base
    raiz.pasta_id             = root_pasta.id
    mapa_dir[base_c] = root_pasta
    vistos_pastas.add(base_c)

    for dirpath, dirnames, filenames in os.walk(base):
        dirnames.sort()
        dn  = _norm(dirpath)
        dnc = os.path.normcase(dn)
        pasta_atual = mapa_dir.get(dnc)
        if pasta_atual is None:
            parent = mapa_dir.get(os.path.normcase(_norm(os.path.dirname(dn))))
            parent_id = parent.id if parent else None
            pasta_atual = pastas_mirror.get(dnc)
            if pasta_atual is not None:
                pasta_atual.nome           = _nome_dir(dn)
                pasta_atual.parent_id      = parent_id
                pasta_atual.caminho_origem = dn
            else:
                pasta_atual = Pasta(
                    nome=_nome_dir(dn), parent_id=parent_id,
                    usuario_id=usuario.id, caminho_origem=dn,
                )
                db.add(pasta_atual)
                db.flush()
            mapa_dir[dnc] = pasta_atual
        vistos_pastas.add(dnc)

        for fn in sorted(filenames):
            if not fn.lower().endswith(".csv"):
                continue
            full  = _norm(os.path.join(dn, fn))
            fullc = os.path.normcase(full)
            try:
                mtime = os.path.getmtime(full)
            except OSError:
                continue
            arq = arquivos_mirror.get(fullc)
            try:
                if arq is None:
                    _importar_arquivo_disco(full, pasta_atual.id, usuario, db)
                    resultado["criados"] += 1
                elif (arq.mtime_origem or 0.0) < mtime - 1e-6:
                    _importar_arquivo_disco(full, pasta_atual.id, usuario, db, arquivo=arq)
                    resultado["atualizados"] += 1
                else:
                    arq.pasta_id     = pasta_atual.id
                    arq.nome_arquivo = fn
                vistos_arquivos.add(fullc)
            except HTTPException:
                # CSV inválido/vazio: ignora o arquivo e segue com o restante.
                logger.warning("Sincronização ignorou CSV inválido: %s", full)
                if arq is not None:
                    vistos_arquivos.add(fullc)  # mantém o registro antigo

    # ── Remoções: o que sumiu do disco é removido do app ──
    for chave, arq in arquivos_mirror.items():
        if chave not in vistos_arquivos:
            db.delete(arq)
            resultado["removidos"] += 1

    sumidas = [p for c, p in pastas_mirror.items() if c not in vistos_pastas]
    ids_sumidas = {p.id for p in sumidas}
    if ids_sumidas:
        # Arquivos não-sincronizados (movidos manualmente p/ dentro) voltam à raiz.
        db.query(UploadArquivo).filter(
            UploadArquivo.usuario_id == usuario.id,
            UploadArquivo.pasta_id.in_(ids_sumidas),
        ).update({UploadArquivo.pasta_id: None}, synchronize_session=False)
    # Remove das subpastas mais profundas para as mais rasas (evita conflito de cascade).
    for p in sorted(sumidas, key=lambda x: len(x.caminho_origem or ""), reverse=True):
        db.delete(p)

    raiz.ultima_sincronizacao = datetime.now()
    db.commit()
    return resultado


# Script do seletor: roda em um PROCESSO separado para que o Tkinter use sua
# própria thread principal. Assim, se a janela travar ou falhar, ela nunca
# derruba o servidor uvicorn (evita "Failed to fetch" em toda a aplicação).
_SCRIPT_SELETOR_PASTA = (
    "import tkinter as tk\n"
    "from tkinter import filedialog\n"
    "r = tk.Tk(); r.withdraw()\n"
    "try:\n"
    "    r.attributes('-topmost', True)\n"
    "except Exception:\n"
    "    pass\n"
    "c = filedialog.askdirectory(title='Escolha a pasta para sincronizar com o Visia')\n"
    "r.destroy()\n"
    "print(c or '')\n"
)


@router.get("/sincronizacao/selecionar-pasta", response_model=DialogoPastaResposta)
def selecionar_pasta(usuario: Usuario = Depends(get_current_user)):
    """Abre o seletor de pastas nativo do sistema (app rodando localmente).

    O diálogo roda em um subprocesso isolado. Se o ambiente não tiver interface
    gráfica (ex.: servidor remoto), responde 501 para o cliente cair no campo manual.
    """
    import subprocess
    import sys

    try:
        proc = subprocess.run(
            [sys.executable, "-c", _SCRIPT_SELETOR_PASTA],
            capture_output=True,
            text=True,
            timeout=300,  # tempo para o usuário escolher a pasta
        )
    except Exception as exc:  # pragma: no cover — depende do ambiente
        logger.warning("Diálogo nativo de pasta indisponível: %s", exc)
        raise HTTPException(
            status_code=501,
            detail="Seleção nativa indisponível neste ambiente. Cole o caminho da pasta manualmente.",
        )

    if proc.returncode != 0:
        logger.warning("Seletor de pasta falhou (rc=%s): %s", proc.returncode, proc.stderr.strip())
        raise HTTPException(
            status_code=501,
            detail="Seleção nativa indisponível neste ambiente. Cole o caminho da pasta manualmente.",
        )

    linhas = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    caminho = linhas[-1] if linhas else ""
    return DialogoPastaResposta(caminho=_norm(caminho) if caminho else None)


def _montar_raiz_resposta(raiz: RaizSincronizada, usuario: Usuario, db: Session) -> RaizResposta:
    total = (
        db.query(UploadArquivo)
        .filter(UploadArquivo.usuario_id == usuario.id, UploadArquivo.caminho_origem.isnot(None))
        .all()
    )
    return RaizResposta(
        id=raiz.id,
        caminho=raiz.caminho,
        pasta_id=raiz.pasta_id,
        ultima_sincronizacao=raiz.ultima_sincronizacao,
        total_arquivos=sum(1 for a in total if _sob(a.caminho_origem, raiz.caminho)),
        origem_ausente=not os.path.isdir(raiz.caminho),
    )


@router.get("/sincronizacao", response_model=List[RaizResposta])
def listar_raizes(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    raizes = (
        db.query(RaizSincronizada)
        .filter(RaizSincronizada.usuario_id == usuario.id)
        .order_by(RaizSincronizada.id.asc())
        .all()
    )
    return [_montar_raiz_resposta(r, usuario, db) for r in raizes]


@router.post("/sincronizacao", response_model=SincronizacaoResposta, status_code=status.HTTP_201_CREATED)
def criar_sincronizacao(
    dados: RaizCriar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Registra uma pasta do computador e faz a primeira sincronização."""
    caminho = _norm(dados.caminho.strip())
    if not os.path.isdir(caminho):
        raise HTTPException(status_code=400, detail="Caminho não encontrado ou não é uma pasta.")

    existentes = (
        db.query(RaizSincronizada).filter(RaizSincronizada.usuario_id == usuario.id).all()
    )
    for r in existentes:
        if _sob(caminho, r.caminho) or _sob(r.caminho, caminho):
            raise HTTPException(
                status_code=400,
                detail="Esta pasta (ou uma que a contém) já está sincronizada.",
            )

    raiz = RaizSincronizada(caminho=caminho, usuario_id=usuario.id)
    db.add(raiz)
    db.flush()
    res = _sincronizar_raiz(raiz, usuario, db)
    return SincronizacaoResposta(
        status="sucesso",
        mensagem=f"Pasta sincronizada: {res['criados']} arquivo(s) importado(s).",
        criados=res["criados"],
        atualizados=res["atualizados"],
        removidos=res["removidos"],
    )


@router.post("/sincronizacao/atualizar", response_model=SincronizacaoResposta)
def atualizar_sincronizacao(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Reexamina todas as pastas sincronizadas e aplica as mudanças do disco."""
    raizes = (
        db.query(RaizSincronizada).filter(RaizSincronizada.usuario_id == usuario.id).all()
    )
    if not raizes:
        return SincronizacaoResposta(status="vazio", mensagem="Nenhuma pasta sincronizada.")

    criados = atualizados = removidos = 0
    ausentes: list = []
    for r in raizes:
        res = _sincronizar_raiz(r, usuario, db)
        if res["ausente"]:
            ausentes.append(r.caminho)
            continue
        criados     += res["criados"]
        atualizados += res["atualizados"]
        removidos   += res["removidos"]

    partes = []
    if criados:
        partes.append(f"{criados} novo(s)")
    if atualizados:
        partes.append(f"{atualizados} atualizado(s)")
    if removidos:
        partes.append(f"{removidos} removido(s)")
    msg = "Tudo sincronizado." if not partes else "Sincronizado: " + ", ".join(partes) + "."
    if ausentes:
        msg += f" {len(ausentes)} pasta(s) não encontrada(s) no disco."

    return SincronizacaoResposta(
        status="sucesso",
        mensagem=msg,
        criados=criados,
        atualizados=atualizados,
        removidos=removidos,
        raizes_ausentes=ausentes,
    )


@router.delete("/sincronizacao/{raiz_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_sincronizacao(
    raiz_id: int,
    manter_dados: bool = False,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Para de sincronizar uma pasta.

    Por padrão remove do app o espelho (pastas e arquivos importados dela).
    Com ``manter_dados=true`` os dados ficam, apenas desvinculados da origem.
    """
    raiz = (
        db.query(RaizSincronizada)
        .filter(RaizSincronizada.id == raiz_id, RaizSincronizada.usuario_id == usuario.id)
        .first()
    )
    if not raiz:
        raise HTTPException(status_code=404, detail="Pasta sincronizada não encontrada.")

    base = raiz.caminho
    arquivos = [
        a for a in db.query(UploadArquivo).filter(
            UploadArquivo.usuario_id == usuario.id, UploadArquivo.caminho_origem.isnot(None)
        ).all()
        if _sob(a.caminho_origem, base)
    ]
    pastas = [
        p for p in db.query(Pasta).filter(
            Pasta.usuario_id == usuario.id, Pasta.caminho_origem.isnot(None)
        ).all()
        if _sob(p.caminho_origem, base)
    ]

    if manter_dados:
        # Mantém os dados, apenas desvincula da origem (vira conteúdo "normal").
        for a in arquivos:
            a.caminho_origem = None
            a.mtime_origem = None
        for p in pastas:
            p.caminho_origem = None
    else:
        for a in arquivos:
            db.delete(a)
        ids = {p.id for p in pastas}
        if ids:
            db.query(UploadArquivo).filter(
                UploadArquivo.usuario_id == usuario.id,
                UploadArquivo.pasta_id.in_(ids),
            ).update({UploadArquivo.pasta_id: None}, synchronize_session=False)
        for p in sorted(pastas, key=lambda x: len(x.caminho_origem or ""), reverse=True):
            db.delete(p)

    raiz.pasta_id = None
    db.delete(raiz)
    db.commit()


# ── Categorias (definido antes de /{venda_id}) ───────────────────────────────

@router.get("/categorias", response_model=List[CategoriaResposta])
def listar_categorias(
    arquivo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Lista as categorias/produtos distintos do usuário, com volume agregado."""
    query = db.query(Venda).filter(
        Venda.usuario_id == usuario.id,
        Venda.categoria.isnot(None),
    )
    if arquivo_id is not None:
        query = query.filter(Venda.arquivo_id == arquivo_id)

    agregados: dict = {}
    for v in query.all():
        cat = v.categoria
        if cat not in agregados:
            agregados[cat] = {"total_registros": 0, "total_valor": 0.0}
        agregados[cat]["total_registros"] += 1
        agregados[cat]["total_valor"] += float(v.valor or 0)

    return [
        CategoriaResposta(
            categoria=cat,
            total_registros=d["total_registros"],
            total_valor=round(d["total_valor"], 2),
        )
        for cat, d in sorted(agregados.items(), key=lambda kv: kv[1]["total_valor"], reverse=True)
    ]


# ── Stats (definido antes de /{venda_id}) ────────────────────────────────────

@router.get("/stats", response_model=StatsResposta)
def obter_stats(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    vendas   = db.query(Venda).filter(Venda.usuario_id == usuario.id).all()
    arquivos = (
        db.query(UploadArquivo)
        .filter(UploadArquivo.usuario_id == usuario.id)
        .order_by(UploadArquivo.id.desc())
        .all()
    )
    if not vendas:
        return StatsResposta(
            total_registros=0,
            total_valor=0.0,
            maior_venda=0.0,
            media_diaria=0.0,
            total_arquivos=len(arquivos),
            ultimo_upload=None,
        )
    valores      = [v.valor for v in vendas]
    datas_unicas = len({str(v.data_venda) for v in vendas})
    return StatsResposta(
        total_registros=len(vendas),
        total_valor=round(sum(valores), 2),
        maior_venda=round(max(valores), 2),
        media_diaria=round(sum(valores) / datas_unicas, 2) if datas_unicas else 0.0,
        total_arquivos=len(arquivos),
        ultimo_upload=arquivos[0].data_upload.strftime("%d/%m/%Y") if arquivos else None,
    )


# ── Importação CSV (definido antes de /{venda_id}) ────────────────────────────

@router.post("/importar-csv", response_model=ImportacaoResposta, status_code=status.HTTP_201_CREATED)
async def importar_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    conteudo = await file.read()
    df = _parse_csv(conteudo)
    consolidado, tem_categorias, categorias_detectadas, col_valor, col_categoria = _consolidar(df)

    arquivo = UploadArquivo(
        nome_arquivo=file.filename,
        data_upload=datetime.now().date(),
        usuario_id=usuario.id,
    )
    db.add(arquivo)
    db.flush()

    _inserir_vendas(arquivo, consolidado, usuario, db)
    db.commit()

    if tem_categorias:
        msg = (
            f"'{file.filename}' importado com sucesso — "
            f"{len(categorias_detectadas)} categoria(s) detectada(s)."
        )
    else:
        msg = f"'{file.filename}' importado com sucesso (sem categorias)."

    return ImportacaoResposta(
        status="sucesso",
        mensagem=msg,
        registros_afetados=len(consolidado),
        arquivo_id=arquivo.id,
        tem_categorias=tem_categorias,
        categorias_detectadas=categorias_detectadas,
        coluna_valor_detectada=col_valor,
        coluna_categoria_detectada=col_categoria,
    )


# ── Vendas manuais (arquivo_id IS NULL) ──────────────────────────────────────

@router.get("/manuais", response_model=List[VendaResposta])
def listar_vendas_manuais(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    return (
        db.query(Venda)
        .filter(Venda.usuario_id == usuario.id, Venda.arquivo_id.is_(None))
        .order_by(Venda.data_venda.desc())
        .all()
    )


@router.delete("/manuais", status_code=status.HTTP_204_NO_CONTENT)
def deletar_todas_manuais(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    db.query(Venda).filter(
        Venda.usuario_id == usuario.id,
        Venda.arquivo_id.is_(None),
    ).delete(synchronize_session=False)
    db.commit()


# ── CRUD de Vendas ────────────────────────────────────────────────────────────

@router.get("/", response_model=List[VendaResposta])
def listar_vendas(
    arquivo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    query = db.query(Venda).filter(Venda.usuario_id == usuario.id)
    if arquivo_id is not None:
        query = query.filter(Venda.arquivo_id == arquivo_id)
    return query.order_by(Venda.data_venda.desc()).all()


@router.post("/", response_model=VendaResposta, status_code=status.HTTP_201_CREATED)
def criar_venda(
    dados: VendaCriar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    venda = Venda(
        data_venda=dados.data_venda,
        valor=dados.valor,
        categoria=(dados.categoria.strip() or None) if dados.categoria else None,
        usuario_id=usuario.id,
    )
    db.add(venda)
    db.commit()
    db.refresh(venda)
    return venda


@router.get("/{venda_id}", response_model=VendaResposta)
def obter_venda(
    venda_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    venda = (
        db.query(Venda)
        .filter(Venda.id == venda_id, Venda.usuario_id == usuario.id)
        .first()
    )
    if not venda:
        raise HTTPException(status_code=404, detail="Venda não encontrada.")
    return venda


@router.put("/{venda_id}", response_model=VendaResposta)
def atualizar_venda(
    venda_id: int,
    dados: VendaAtualizar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    venda = (
        db.query(Venda)
        .filter(Venda.id == venda_id, Venda.usuario_id == usuario.id)
        .first()
    )
    if not venda:
        raise HTTPException(status_code=404, detail="Venda não encontrada.")
    if dados.data_venda is not None:
        venda.data_venda = dados.data_venda
    if dados.valor is not None:
        venda.valor = dados.valor
    if dados.categoria is not None:
        venda.categoria = dados.categoria.strip() or None
    db.commit()
    db.refresh(venda)
    return venda


@router.delete("/{venda_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_venda(
    venda_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    venda = (
        db.query(Venda)
        .filter(Venda.id == venda_id, Venda.usuario_id == usuario.id)
        .first()
    )
    if not venda:
        raise HTTPException(status_code=404, detail="Venda não encontrada.")
    db.delete(venda)
    db.commit()
