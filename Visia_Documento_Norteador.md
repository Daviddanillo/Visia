# Visia — Documento Norteador do Projeto

### Sistema de Previsão de Tendências de Mercado com Inteligência Artificial

**Guia completo da arquitetura, das pastas, dos arquivos e das principais funções do código**

> Versão 3.0.0 · Backend **FastAPI + Prophet** · Banco **SQLAlchemy (SQLite/PostgreSQL)** · Frontend **SPA (HTML/CSS/JS + Plotly)**

---

## Sumário

1. [Visão Geral do Projeto](#1-visão-geral-do-projeto)
2. [Estrutura de Pastas](#2-estrutura-de-pastas)
3. [Ponto de Entrada — `app/main.py`](#3-ponto-de-entrada--appmainpy)
4. [Núcleo — `app/core/`](#4-núcleo--appcore)
5. [Banco de Dados — `app/db/`](#5-banco-de-dados--appdb)
6. [Modelos (Tabelas) — `app/models/`](#6-modelos-tabelas--appmodels)
7. [Esquemas / Validação — `app/schemas/`](#7-esquemas--validação--appschemas)
8. [Rotas da API — `app/routers/`](#8-rotas-da-api--approuters)
9. [Motor de Previsão — `app/services/`](#9-motor-de-previsão--appservices)
10. [Interface Web — `app/frontend/`](#10-interface-web--appfrontend)
11. [Testes Automatizados — `tests/`](#11-testes-automatizados--tests)
12. [Diagramas — `diagramas/`](#12-diagramas--diagramas)
13. [Documentos de Engenharia — `docs/` (BRD e ERS)](#13-documentos-de-engenharia--docs-brd-e-ers)
14. [Arquivos de Configuração e Suporte](#14-arquivos-de-configuração-e-suporte)
15. [Pipelines de CI/CD — `.github/workflows/`](#15-pipelines-de-cicd--githubworkflows)
16. [Glossário Técnico](#16-glossário-técnico)

---

## 1. Visão Geral do Projeto

O **Visia** é uma aplicação web de **Inteligência Artificial Preditiva** voltada para a previsão de
vendas/faturamento. O usuário envia dados históricos (CSV) ou sincroniza uma pasta do computador, e o
sistema treina um modelo de **séries temporais** (Facebook/Meta **Prophet**) que projeta o desempenho
futuro considerando **sazonalidade semanal, sazonalidade anual e feriados brasileiros**. O resultado é
exibido em gráficos interativos, com **alertas de alta/queda**, **métricas de acurácia** (validação
cruzada) e **previsões individuais por categoria/produto**.

### Como o sistema está dividido

- **Backend (Python / FastAPI):** expõe uma API REST que cuida de autenticação, gestão de vendas,
  importação de CSV, organização em pastas, sincronização com o disco e o motor de previsão.
- **Banco de dados (SQLite por padrão):** guarda usuários, vendas, arquivos importados, pastas e
  raízes sincronizadas. Pode usar **PostgreSQL** via Docker, sem alterar o código.
- **Motor de IA (Prophet):** isolado na camada de serviços; recebe os dados do banco e devolve a
  previsão pronta (forecast, componentes, alertas e acurácia) para o frontend.
- **Frontend (HTML/CSS/JS puro):** uma única página (*Single Page Application*) servida pelo próprio
  FastAPI, que consome a API e desenha os gráficos com a biblioteca **Plotly**.

### Fluxo de uma requisição (exemplo: gerar previsão)

```text
Navegador (index.html)
    | GET /predict/?dias=30  (com token JWT no cabeçalho Authorization: Bearer ...)
    v
predict_router.py  --> valida o token (get_current_user) e os parâmetros (dias 1..365)
    |
    v
services/predictor.py  --> lê as vendas no banco, agrupa por dia, constrói feriados,
    |                       treina o Prophet, calcula acurácia (cross-validation),
    |                       monta forecast + alertas + componentes + changepoints
    v
Resposta JSON  --> o frontend desenha os gráficos com Plotly
```

### Arquitetura em camadas

O backend segue uma **separação clássica em camadas**, mantendo cada responsabilidade isolada e o
código fácil de evoluir e testar:

| Camada              | Pasta          | Responsabilidade                                                              |
| ------------------- | -------------- | ---------------------------------------------------------------------------- |
| Rotas (Controllers) | `app/routers`  | Recebem as requisições HTTP, validam o usuário/parâmetros e chamam a lógica. |
| Esquemas (DTOs)     | `app/schemas`  | Definem e validam o formato dos dados que entram e saem da API (Pydantic).   |
| Modelos (ORM)       | `app/models`   | Representam as tabelas do banco como classes Python (SQLAlchemy).            |
| Serviços            | `app/services` | Lógica de negócio pesada — aqui mora o motor de previsão.                    |
| Núcleo              | `app/core`     | Configuração, segurança (JWT/senhas) e limitador de requisições.            |
| Banco               | `app/db`       | Conexão e sessão com o banco de dados.                                       |

> **Princípio-chave:** as rotas são "finas" (apenas orquestram), e toda a lógica pesada de IA está
> isolada em `app/services/predictor.py`. Isso permite trocar o frontend, o banco ou até o algoritmo
> de previsão sem reescrever o resto do sistema.

---

## 2. Estrutura de Pastas

Mapa geral do repositório. Nas seções seguintes cada arquivo é detalhado.

```text
Visia/
├── app/                      # código da aplicação (backend + frontend)
│   ├── core/                 # configuração, segurança e rate limit
│   │   ├── config.py         # Settings (pydantic-settings) lidas do .env
│   │   ├── security.py       # bcrypt, JWT e dependência get_current_user
│   │   └── ratelimit.py      # slowapi (proteção contra força bruta)
│   ├── db/
│   │   └── database.py       # engine, sessão, Base e ajustes do SQLite (WAL)
│   ├── models/               # tabelas do banco (SQLAlchemy ORM)
│   │   ├── usuario.py        # tabela usuarios
│   │   └── venda.py          # Pasta, UploadArquivo, Venda, RaizSincronizada
│   ├── schemas/              # validação de entrada/saída (Pydantic)
│   │   ├── auth.py           # schemas de usuário/login/token
│   │   └── venda.py          # schemas de vendas/arquivos/pastas/sincronização
│   ├── routers/              # endpoints da API REST
│   │   ├── auth_router.py    # /auth (cadastro, login, perfil)
│   │   ├── venda_router.py   # /vendas (CSV, CRUD, pastas, sincronização)
│   │   └── predict_router.py # /predict (motor de IA)
│   ├── services/
│   │   └── predictor.py      # lógica de negócio (motor de previsão)
│   ├── frontend/
│   │   └── index.html        # interface web (SPA em um único HTML)
│   └── main.py               # ponto de entrada: cria o app FastAPI
├── tests/                    # testes automatizados (pytest)
├── diagramas/                # diagramas UML do projeto (classe, ER, sequência, casos de uso)
├── docs/                     # documentos de engenharia BRD e ERS (PDF)
├── .github/workflows/        # pipelines de CI (lint, testes, segurança, CodeQL)
├── requirements.txt          # dependências Python (versões fixas)
├── pyproject.toml            # config de ferramentas (ruff, pytest, bandit)
├── docker-compose.yml        # banco PostgreSQL opcional
├── iniciar.bat               # inicializador automático (Windows)
├── _setup_ia.py              # prepara o motor Prophet/Stan (CmdStan)
├── .env / .env.example       # variáveis de ambiente (a real não vai p/ o Git)
├── .secrets.baseline         # linha de base do detect-secrets (scan de segredos)
├── LICENSE.txt               # licença MIT
└── README.md                 # documentação principal
```

---

## 3. Ponto de Entrada — `app/main.py`

É o arquivo que **cria e configura a aplicação**. Quando o servidor sobe (via `uvicorn app.main:app`),
este arquivo é executado de cima a baixo, realizando, em ordem:

1. Configura o `logging` global (nível INFO, formato padronizado).
2. Cria as tabelas no banco com `Base.metadata.create_all(bind=engine)`.
3. Roda **migrações leves** (`ALTER TABLE`) para bancos antigos ganharem colunas novas.
4. Instancia o `FastAPI` (título, descrição e versão `2.0.0`).
5. Configura o **rate limiting** (slowapi) e o **CORS**.
6. Registra os três grupos de rotas: autenticação, vendas e previsão.
7. Expõe a rota `/health` (monitoramento).
8. Monta o frontend estático na raiz `/`.

### Principais funções

#### `_migrar_coluna_categoria()`
Verifica se a tabela `vendas` já tem a coluna `categoria`; se não tiver, executa um `ALTER TABLE`.
Como o `create_all` **não altera tabelas existentes**, essa migração manual mantém bancos antigos
(`dados.db`) compatíveis sem perder dados. É **idempotente** (só age se a coluna faltar).

#### `_migrar_coluna_pasta_id()`
Garante que arquivos importados antes da feature de organização ganhem a coluna `pasta_id` na tabela
`uploads_arquivos`.

#### `_migrar_colunas_sincronizacao()`
Adiciona as colunas usadas pela sincronização de pastas do disco em bancos antigos:
`pastas.caminho_origem`, `uploads_arquivos.caminho_origem` e `uploads_arquivos.mtime_origem`.

> As três migrações são *best-effort*: se algo falhar, o erro é apenas registrado em log
> (`logging.warning`) sem derrubar a aplicação.

#### `health_check()`
Endpoint `GET /health` que devolve `{"status": "healthy", "version": "2.0.0"}`. Serve para serviços de
monitoramento (ex.: Render, uptime checkers) confirmarem que a aplicação está no ar.

### Configuração do CORS e Rate Limit (trecho real)

```python
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origens_permitidas,  # lê ALLOWED_ORIGINS do .env
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

O frontend é montado por último para não "engolir" as rotas da API:
```python
app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
```

---

## 4. Núcleo — `app/core/`

Reúne as peças transversais usadas por toda a aplicação: **configuração, segurança e proteção contra
abuso de requisições**.

### `app/core/config.py`

Centraliza todas as **configurações** usando `pydantic-settings`. Os valores têm padrões seguros para
desenvolvimento e podem ser sobrescritos por variáveis de ambiente ou pelo arquivo `.env`.

| Configuração                  | Padrão                                              | Para que serve                               |
| ----------------------------- | --------------------------------------------------- | -------------------------------------------- |
| `DATABASE_URL`                | `sqlite:///./dados.db`                               | Conexão com o banco (troque por PostgreSQL). |
| `SECRET_KEY`                  | `dev-secret-key-change-in-production`                | Chave para assinar os tokens JWT.            |
| `ALGORITHM`                   | `HS256`                                              | Algoritmo de assinatura do JWT.              |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60`                                                | Validade do token (em minutos).              |
| `ALLOWED_ORIGINS`             | `http://localhost:8000,http://127.0.0.1:8000`       | Domínios liberados no CORS.                  |

#### `class Settings`
Declara cada configuração com tipo e valor padrão. Lê automaticamente do `.env` (`extra="ignore"`
descarta variáveis desconhecidas sem erro).

#### `origens_permitidas` *(property)*
Converte a string `ALLOWED_ORIGINS` (domínios separados por vírgula) em **uma lista de URLs**, usada na
configuração do CORS no `main.py`.

> ⚠️ **Em produção:** defina uma `SECRET_KEY` forte (`openssl rand -hex 32`) e ajuste `ALLOWED_ORIGINS`
> para o domínio real. O padrão é apenas para desenvolvimento local.

### `app/core/security.py`

Concentra toda a **segurança de autenticação**: criptografia de senhas (**bcrypt**) e tokens de acesso
(**JWT** via `python-jose`).

#### `hash_senha()` / `verificar_senha()`
A primeira transforma a senha em um **hash bcrypt** (com *salt* aleatório) para guardar no banco — a
senha real **nunca** é armazenada. A segunda compara a senha digitada no login com o hash salvo.

#### `criar_token(dados)`
Gera um token JWT assinado com a `SECRET_KEY`, embutindo o e-mail do usuário (`sub`) e uma data de
expiração (`exp`, em UTC). É devolvido no login e usado em todas as requisições seguintes.

#### `get_current_user(...)`
**Dependência** usada por quase todos os endpoints protegidos: lê o token `Bearer` do cabeçalho
(`HTTPBearer`), valida a assinatura, extrai o e-mail, busca o usuário no banco e o injeta na rota. Se o
token for inválido/expirado ou o usuário não existir, devolve **401**.

### `app/core/ratelimit.py`

Configura o **limitador de requisições** (`slowapi`, armazenamento em memória por processo), que protege
endpoints sensíveis — como o login — contra ataques de **força bruta**.

#### `_client_key(request)`
Decide qual IP identifica o cliente. Como a aplicação pode rodar **atrás de um proxy reverso** (ex.:
Render), prioriza o primeiro IP do cabeçalho `X-Forwarded-For` (IP real do usuário) e só cai para o IP
da conexão direta quando não há proxy.

> Os limites são aplicados por decorator nas rotas, ex.: `@limiter.limit("10/minute")` no login e
> `@limiter.limit("5/minute")` no cadastro.

---

## 5. Banco de Dados — `app/db/`

### `app/db/database.py`

Cria a **conexão (engine)** e a **fábrica de sessões** do SQLAlchemy, define a classe `Base` que todos
os modelos herdam e aplica ajustes específicos do SQLite para suportar leituras e escritas simultâneas
(importante durante a sincronização de pastas).

Detalhe relevante: o `connect_args` muda conforme o banco. Para SQLite usa
`{"check_same_thread": False, "timeout": 30}` — o `timeout` faz o driver **aguardar** o bloqueio ser
liberado em vez de já falhar com *"database is locked"*.

#### `_configurar_sqlite(...)`
Executado a cada conexão SQLite (via `event.listens_for`): ativa três PRAGMAs:
- `journal_mode=WAL` (*Write-Ahead Logging*): permite **ler o banco enquanto outra operação escreve**,
  reduzindo erros de *"database is locked"*.
- `busy_timeout=30000`: espera até 30s por um bloqueio.
- `synchronous=NORMAL`: equilíbrio entre desempenho e segurança de gravação.

#### `get_db()`
**Gerador** usado como dependência nas rotas: abre uma sessão de banco, entrega para o endpoint usar
(`yield`) e garante o fechamento ao final (`finally: db.close()`), mesmo se ocorrer erro.

---

## 6. Modelos (Tabelas) — `app/models/`

Cada classe aqui vira uma **tabela** no banco. Os relacionamentos modelam as regras do domínio (um
usuário tem várias vendas, uma pasta contém arquivos, etc.).

### `app/models/usuario.py` → tabela `usuarios`

#### `class Usuario`
Guarda `id`, `nome`, `email` (único, indexado) e `senha_hash`. Possui relacionamentos com **vendas,
arquivos, pastas e raízes sincronizadas** — todos com `cascade="all, delete-orphan"`, ou seja, ao
apagar o usuário, **todos os seus dados vão junto** (essencial para o `DELETE /auth/me`).

### `app/models/venda.py` → quatro tabelas centrais

| Classe / Tabela                         | O que representa                                                                                                  |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `Pasta` (`pastas`)                      | Pasta de organização. Pode ser **aninhada** (`parent_id` → outra pasta) e pode **espelhar** um diretório do disco (`caminho_origem`). |
| `UploadArquivo` (`uploads_arquivos`)    | Um arquivo CSV importado. Sabe a qual pasta pertence (`pasta_id`) e, se veio de sincronização, guarda o caminho (`caminho_origem`) e a data de modificação (`mtime_origem`) do arquivo original. |
| `Venda` (`vendas`)                      | Um registro de venda: `data_venda`, `valor`, `categoria` (opcional) e vínculos com o usuário e o arquivo de origem. |
| `RaizSincronizada` (`raizes_sincronizadas`) | Uma pasta do computador que o usuário escolheu espelhar no app; guarda o caminho no disco, a `Pasta` que a representa e a data da última sincronização. |

#### `class Venda` — a mais usada pelo motor de IA
O campo `categoria` é **opcional** (`nullable=True`, indexado): bases que só têm data e valor continuam
funcionando; quando há categoria, o sistema gera previsões por produto. Os campos essenciais são
`data_venda` (Date) e `valor` (Float).

#### `class Pasta` — auto-referência
Usa uma **auto-referência** (`parent_id` aponta para a própria tabela `pastas`) com
`relationship(... remote_side=[id])`, permitindo árvores de pastas e subpastas com **profundidade
ilimitada**. As subpastas têm `cascade="all, delete-orphan"`.

#### `class RaizSincronizada`
Liga um diretório real do disco (`caminho`) à `Pasta` espelhada dentro do app (`pasta_id`). A
sincronização percorre esse diretório e reflete criações, alterações e remoções no banco.

### `app/models/__init__.py`
Importa e reexporta as classes de modelo (`Usuario`, `Venda`, `UploadArquivo`, `Pasta`), garantindo que
o SQLAlchemy as **registre no metadata** antes de `create_all` criar as tabelas.

---

## 7. Esquemas / Validação — `app/schemas/`

Os *schemas* **Pydantic** definem o formato dos dados que **entram** (corpo das requisições) e **saem**
(respostas) da API. Eles validam tipos automaticamente e geram a documentação interativa em `/docs`.

### `app/schemas/auth.py`

| Schema             | Papel                                                                                  |
| ------------------ | -------------------------------------------------------------------------------------- |
| `UsuarioCriar`     | Cadastro (`nome`, `email`, `senha`). Validador `senha_minima` exige **≥ 6 caracteres**. |
| `UsuarioAtualizar` | Atualização parcial de perfil (todos os campos opcionais).                             |
| `UsuarioResposta`  | Dados públicos do usuário (`id`, `nome`, `email`) — **nunca** expõe o hash da senha.   |
| `LoginRequest`     | Corpo do login (`email`, `senha`).                                                      |
| `TokenResposta`    | Resposta do login: `access_token`, `token_type` (`bearer`) e o `usuario`.              |

> O `email` usa o tipo `EmailStr`, que valida o formato do e-mail automaticamente (via
> `email-validator`).

### `app/schemas/venda.py`

Reúne os schemas de vendas, arquivos, pastas, categorias, estatísticas, importação e sincronização.
Cada operação (criar, atualizar, responder) tem seu próprio modelo. Destaques:

#### `VendaCriar`
Valida uma venda nova: `valor` deve ser **maior que zero** (`Field(..., gt=0)`) e a `categoria` é
opcional.

#### `ArquivoAtualizar`
Permite **renomear** (`nome_arquivo`) e/ou **mover** (`pasta_id`) um arquivo. Usa `model_fields_set`
para distinguir *"campo não enviado"* de *"mover para a raiz"* (`pasta_id = None`).

#### `ImportacaoResposta`
Resumo da importação de CSV: status, mensagem, nº de registros, `arquivo_id`, se há categorias, a lista
de categorias detectadas e **quais colunas** o sistema entendeu como valor/categoria (transparência
para o usuário conferir a detecção automática).

#### `StatsResposta` / `CategoriaResposta`
Métricas do dashboard (total, maior venda, média diária, nº de arquivos, último upload) e agregados por
categoria (registros e valor total).

#### Schemas de sincronização
`RaizCriar` (caminho da pasta), `RaizResposta` (inclui `total_arquivos` e `origem_ausente`),
`SincronizacaoResposta` (`criados`, `atualizados`, `removidos`, `raizes_ausentes`) e
`DialogoPastaResposta` (caminho escolhido no seletor nativo).

### `app/schemas/__init__.py`
Arquivo vazio — apenas marca a pasta como um **pacote Python**.

---

## 8. Rotas da API — `app/routers/`

Cada arquivo agrupa endpoints relacionados sob um **prefixo de URL**. As rotas validam o usuário, chamam
a lógica e devolvem respostas no formato dos schemas.

### `app/routers/auth_router.py` — prefixo `/auth`

| Endpoint            | O que faz                                                          |
| ------------------- | ----------------------------------------------------------------- |
| `POST /auth/cadastro` | Cria um usuário (senha já criptografada). Rate limit **5/min**.   |
| `POST /auth/login`    | Valida credenciais e devolve o token JWT. Rate limit **10/min**.  |
| `GET /auth/me`        | Retorna o perfil do usuário autenticado.                          |
| `PUT /auth/me`        | Atualiza nome, e-mail e/ou senha (verifica e-mail duplicado).     |
| `DELETE /auth/me`     | Apaga a conta e **todos** os dados vinculados (cascade).          |

#### `cadastrar(...)`
Garante que o e-mail ainda não existe, cria o usuário com a senha em hash e o salva. Protegido por rate
limit (5/min).

#### `login(...)`
Busca o usuário pelo e-mail, confere a senha com `verificar_senha` e, se ok, emite o token. Limitado a
**10 tentativas por minuto por IP** contra força bruta. Em falha devolve **401** com mensagem genérica
(*"E-mail ou senha incorretos"*) — não revela se o e-mail existe.

### `app/routers/predict_router.py` — prefixo `/predict`

É a **porta de entrada do motor de IA**: apenas recebe os parâmetros, delega ao serviço de previsão e
converte erros de dados insuficientes em **HTTP 400**.

#### `prever_vendas(dias, arquivo_id, categoria, ...)` → `GET /predict/`
Repassa os filtros para `gerar_previsao()`. O parâmetro `dias` é validado entre **1 e 365**
(`Query(30, ge=1, le=365)`). Pode filtrar por arquivo (`arquivo_id`) e/ou categoria.

#### `prever_por_categoria(...)` → `GET /predict/categorias`
Chama `gerar_previsao_categorias()`: previsões individuais por produto/categoria + insights
consolidados.

### `app/routers/venda_router.py` — prefixo `/vendas`

É o **maior arquivo da API**. Concentra toda a manipulação de dados: importação de CSV, CRUD de vendas,
organização em pastas e a sincronização com o disco. Antes dos endpoints, há funções auxiliares de
processamento de planilhas.

> ⚠️ **Ordem das rotas importa:** rotas literais como `/vendas/arquivos`, `/vendas/categorias`,
> `/vendas/stats`, `/vendas/manuais` e `/vendas/importar-csv` são declaradas **antes** de
> `/vendas/{venda_id}`. Caso contrário o FastAPI interpretaria "arquivos" como um `venda_id`.

#### Endpoints (resumo por grupo)

| Grupo          | Endpoints                                                                    |
| -------------- | --------------------------------------------------------------------------- |
| Importação     | `POST /vendas/importar-csv`                                                  |
| Vendas (CRUD)  | `GET, POST /vendas/` · `GET, PUT, DELETE /vendas/{id}`                       |
| Vendas manuais | `GET, DELETE /vendas/manuais`                                                |
| Estatísticas   | `GET /vendas/stats`                                                          |
| Categorias     | `GET /vendas/categorias`                                                     |
| Arquivos       | `GET /vendas/arquivos` · `PUT, DELETE /vendas/arquivos/{id}`                 |
| Pastas         | `GET, POST /vendas/pastas` · `PUT, DELETE /vendas/pastas/{id}`               |
| Sincronização  | `GET, POST /vendas/sincronizacao` · `POST /vendas/sincronizacao/atualizar` · `DELETE /vendas/sincronizacao/{id}` · `GET /vendas/sincronizacao/selecionar-pasta` |

#### Funções auxiliares de importação

**`_parse_csv(conteudo)`** — Lê os bytes do CSV em um `DataFrame`, **detectando o separador
automaticamente** (`sep=None`, engine Python). Rejeita arquivos inválidos ou vazios com HTTP 400.

**`_detectar_coluna(colunas, sinonimos, bloqueio, excluir)`** — Procura, entre os nomes das colunas,
aquela que casa com uma **lista de sinônimos** (em PT ou EN), respeitando **bloqueios** (ex.: não
confundir `order_id` com categoria) e colunas **já usadas**.

**`_limpar_valor(serie)`** — Normaliza valores monetários: remove `R$`, espaços e o separador de milhar,
troca a vírgula decimal por ponto e converte para número.

**`_consolidar(df)` — o "coração" da importação.** Recebe a planilha bruta e:
1. Normaliza os nomes das colunas (minúsculas, sem aspas/espaços).
2. **Detecta automaticamente** as colunas de **data, valor, categoria e quantidade** — a data é
   detectada primeiro e excluída das buscas seguintes (para `data_venda` não ser confundida com
   `venda`/valor).
3. Define a métrica de `valor`: prioriza a coluna monetária; se não houver, usa a **quantidade**; se
   nenhuma existir, usa **peso unitário `1.0`** por linha (conta ocorrências).
4. **Consolida as vendas por dia** (e por categoria, quando houver), somando os valores.

Retorna `(consolidado, tem_categorias, categorias_detectadas, col_valor, col_categoria)` — é o que faz
o sistema aceitar CSVs de formatos muito diferentes (e-commerce, floricultura, etc.).

**`_inserir_vendas(...)`** — Insere as linhas consolidadas como vendas vinculadas ao arquivo, em lote
(`bulk_insert_mappings`, eficiente).

#### Importação e CRUD

**`importar_csv(...)`** (`POST /vendas/importar-csv`) — Recebe o upload, chama `_consolidar`, grava o
arquivo e as vendas no banco e devolve um resumo (categorias detectadas, colunas reconhecidas, etc.).

**CRUD de vendas** — `listar_vendas`, `criar_venda`, `obter_venda`, `atualizar_venda`, `deletar_venda`.
Todas filtram por `usuario_id`, garantindo **isolamento entre usuários** (ver venda de outro → 404).

**Vendas manuais** — `listar_vendas_manuais` e `deletar_todas_manuais` operam sobre vendas com
`arquivo_id IS NULL` (lançadas à mão, sem CSV).

**`obter_stats(...)`** e **`listar_categorias(...)`** — alimentam o dashboard e a aba de categorias com
agregações.

#### Organização em pastas

**`_validar_pasta_destino(...)`** — garante que a pasta-destino pertence ao usuário (senão 404).

**`_ids_descendentes(pasta_id, ...)`** — retorna o id da pasta + todos os descendentes
(busca em largura/profundidade na árvore). Usado para **impedir mover uma pasta para dentro dela mesma**
e para reorganizar arquivos ao excluir uma pasta.

**`criar_pasta`, `atualizar_pasta`, `deletar_pasta`** — CRUD de pastas. Ao **excluir** uma pasta, os
arquivos dela (e das subpastas) **voltam para a raiz** (`pasta_id = None`) — os dados nunca são
perdidos —, e as subpastas são removidas em cascata.

#### Sincronização com pasta do computador

**`_norm`, `_sob`, `_nome_dir`** — utilitários de caminho (normalização absoluta, verificação de
contenção *"está sob"* e nome exibível de diretório).

**`_importar_arquivo_disco(...)`** — Importa/atualiza um CSV do disco vinculando-o à pasta espelhada. Em
atualização, **apaga as vendas antigas** do arquivo e insere as novas, mantendo o mesmo registro e
guardando o `mtime` (data de modificação).

**`_sincronizar_raiz(raiz, ...)` — a lógica mais complexa do arquivo.** Percorre a pasta do disco com
`os.walk` e **reflete o estado real no banco**:
- cria pastas/CSVs novos;
- **reimporta** os que mudaram (comparando `mtime_origem` com o `mtime` atual do disco);
- **remove** os que sumiram do disco;
- arquivos movidos manualmente para dentro de pastas que sumiram voltam para a raiz;
- CSVs inválidos/vazios são **ignorados** (com log) sem interromper a sincronização.

**`selecionar_pasta(...)`** (`GET /vendas/sincronizacao/selecionar-pasta`) — Abre o seletor de pastas
**nativo** do sistema operacional em um **subprocesso isolado** (Tkinter). Rodar em outro processo
garante que uma falha na janela **nunca derrube o servidor** uvicorn. Em ambientes sem interface
gráfica (servidor remoto), responde **501** para o usuário digitar o caminho manualmente.

**`criar_sincronizacao`, `atualizar_sincronizacao`, `remover_sincronizacao`, `listar_raizes`** —
gerenciam as raízes sincronizadas. A criação valida que a pasta existe e que **não há sobreposição** com
outra já sincronizada. A remoção tem o parâmetro `manter_dados`: se `true`, mantém os dados apenas
desvinculando-os da origem; se `false` (padrão), apaga o espelho.

---

## 9. Motor de Previsão — `app/services/`

### `app/services/predictor.py`

É o **cérebro de IA** do Visia. Usa a biblioteca **Prophet** (Meta) para treinar um modelo de séries
temporais sobre o histórico de vendas e projetar o futuro. Além da previsão, calcula métricas de
acurácia, detecta mudanças de tendência e considera os feriados brasileiros.

#### Helpers de calendário

**`_calcular_pascoa(ano)`** — Implementa o **algoritmo de Gauss** para calcular a data da Páscoa. A
partir dela derivam-se Carnaval (−48 dias), Sexta-feira Santa (−2 dias) e Corpus Christi (+60 dias).

**`_proximo_domingo` / `_ultima_sexta_antes`** — auxiliam a calcular feriados móveis baseados no dia da
semana (Dia das Mães, Dia dos Pais, Black Friday).

**`_construir_feriados(anos)`** — Gera o calendário de feriados brasileiros (fixos e móveis) para os
anos do histórico **e** da previsão. Inclui **janelas de efeito** (`lower_window`/`upper_window`): por
exemplo, os dias **antes** do Natal (−3) e do Dia das Mães (−7) também influenciam a previsão, não só a
data exata. Retorna dois objetos: o `DataFrame` no formato Prophet e um `dict` *lookup* para marcar
`is_holiday` na resposta.

Feriados cobertos: Carnaval, Sexta-feira Santa, Páscoa, Corpus Christi, Ano Novo, Tiradentes, Dia do
Trabalho, Dia dos Namorados, Independência, N. S. Aparecida, Finados, Proclamação da República,
Consciência Negra, Véspera de Natal, Natal, Réveillon, Dia das Mães, Dia dos Pais e Black Friday.

#### Validação cruzada e acurácia

**`_calcular_cv(model, df, dias)`** — Faz **validação cruzada** (*cross-validation*) para estimar o erro
real da previsão. Calcula **MAE, MAPE, RMSE e cobertura** (coverage), inclusive **por horizonte** (erro
no dia 1, no dia 7, etc.). Se o histórico for insuficiente (precisa de ao menos `max(3×dias, 90) + dias`
dias), retorna `disponivel: False` com o motivo.

#### Detecção de changepoints

**`_extrair_changepoints(model)`** — Identifica os **pontos de virada** da tendência (datas em que o
ritmo de vendas mudou de forma relevante). Pega os 8 maiores por magnitude, descarta os abaixo de 20% do
maior (ruído) e classifica cada um como **aceleração** (`delta > 0`) ou **desaceleração**.

#### Função principal

**`gerar_previsao(usuario_id, db, dias, arquivo_id, categoria)`** — Orquestra todo o processo:

1. Carrega as vendas do banco (filtrando por arquivo/categoria, se informados). Exige **no mínimo 5
   registros** — senão lança `ValueError` (vira HTTP 400).
2. Agrupa por dia (`groupby` somando vendas do mesmo dia).
3. Constrói os feriados para o intervalo do histórico + previsão.
4. Treina o **Prophet** com os parâmetros:
   - `changepoint_prior_scale=0.05` (flexibilidade da tendência),
   - `seasonality_prior_scale=10.0`, `holidays_prior_scale=10.0`,
   - `seasonality_mode="additive"`,
   - `yearly_seasonality="auto"` (ativa com ≥ 1 ano), `weekly_seasonality="auto"` (≥ 2 semanas),
   - `interval_width=0.95` (intervalo de confiança de 95% que **cresce com o horizonte**).
5. Projeta `dias` à frente (`make_future_dataframe` + `predict`).
6. Calcula acurácia (cross-validation) e changepoints.
7. Monta os **componentes** (tendência, sazonalidade semanal e anual). Quando há poucos dados e o
   Prophet não retorna o componente, usa um **fallback estatístico** (médias por dia da semana / mês).
8. Gera a lista de previsão futura com **alertas baseados em percentis** (ver abaixo).

Retorna um dicionário rico: `historico`, `forecast` (com intervalos de confiança, dia da semana e
feriados), `componentes`, `acuracia`, `changepoints` e `resumo` (média/mín/máx, contagem de alertas e
lista de feriados do período).

**Detalhe técnico dos alertas:** dias acima do **percentil 75** viram alerta de **"alta"** e abaixo do
**percentil 25**, de **"queda"** (sempre relativo à mediana das previsões positivas). Há **deduplicação
em janelas de 7 dias** (mantém só o mais extremo) e um **limite de 5 alertas** de cada tipo, evitando
poluir a tela.

#### Previsão por categoria/produto

**`_prever_serie_categoria(...)`** — Ajusta um Prophet "leve" (`interval_width=0.80`) a uma série diária
de uma categoria e devolve a porção futura do forecast.

**`_insights_da_serie(categoria, fut)`** — Detecta dias de alta/queda relevantes e gera **frases em
linguagem natural**, ex.: *"15/06 (Sáb): aumento previsto de Chocolate (+22%)"*. Também deduplica em
janelas de 7 dias.

**`gerar_previsao_categorias(...)`** — Para cada categoria do **top 10 por volume**: treina um modelo (ou
usa fallback de média recente se houver < 5 registros), calcula `media_prevista`, `variacao_pct` e
classifica a tendência (`alta`/`queda`/`estavel`). Produz **insights consolidados** e um **resumo** com a
categoria em maior crescimento, a de maior volume e a de maior queda. Se a base não tiver categorias,
retorna `disponivel: False` com orientação ao usuário.

---

## 10. Interface Web — `app/frontend/`

### `app/frontend/index.html`

Toda a interface está em **um único arquivo HTML** (~3.000 linhas) que inclui o CSS e o JavaScript
embutidos. É uma **SPA** (*Single Page Application*): o usuário navega entre páginas sem recarregar, e o
JavaScript conversa com a API por `fetch`. Os gráficos são desenhados com a biblioteca **Plotly**.

#### Páginas (telas) principais
- **Login / Cadastro:** tela de entrada com indicador de força de senha.
- **Dashboard:** cartões de estatísticas (total, maior venda, média diária) e visão geral.
- **Dados:** upload de CSV (arrastar-e-soltar), sincronização de pastas, organização em pastas e vendas
  manuais.
- **Previsão:** abas com gráfico principal, previsão por categoria, tendência, sazonalidade
  semanal/anual, tabela detalhada e acurácia.

#### Principais funções JavaScript

- **`authFetch(url, options)`** — versão de `fetch` que anexa automaticamente o token JWT no cabeçalho.
  Toda chamada autenticada à API passa por ela.
- **`gerarPrevisao()`** — lê os filtros (dias, arquivo, categoria), chama `/predict/` e dispara a
  renderização dos gráficos e da tabela.
- **`uploadCSV(file)` / `sincronizarAgora()`** — a primeira envia um CSV; a segunda dispara a
  sincronização das pastas do disco e atualiza a lista na tela.
- **`renderChartPrincipal(d)` e demais `render*`** — recebem o JSON da previsão e desenham cada gráfico
  Plotly (linha principal com intervalo de confiança, tendência, sazonalidade, categorias, etc.).

---

## 11. Testes Automatizados — `tests/`

A pasta `tests/` contém a suíte **pytest** que valida o comportamento da API de ponta a ponta, usando um
banco SQLite separado (`test.db`).

| Arquivo                  | O que cobre                                                                     |
| ------------------------ | ------------------------------------------------------------------------------ |
| `conftest.py`            | Banco de teste isolado, desativação do rate limit e fixtures (`client`, `auth_headers`). |
| `test_auth.py`           | Cadastro, login, perfil, senha curta, e-mail duplicado e acesso sem token.     |
| `test_vendas.py`         | CRUD de vendas, validações, estatísticas e **isolamento entre usuários**.      |
| `test_predict.py`        | Previsão: erros com poucos dados e estrutura do resultado com dados suficientes.|
| `test_pastas.py`         | Criar, aninhar, mover, renomear e excluir pastas e arquivos.                    |
| `test_sincronizacao.py`  | Sincronização com o disco: importar, detectar mudanças/modificações e remoções.|

#### Funções e técnicas de destaque

- **`conftest.py`** — sobrescreve `get_db` para apontar ao `test.db`, **desativa o `limiter`** (senão a
  fixture `auth_headers`, que faz cadastro+login a cada teste, estouraria os limites e retornaria 429) e
  recria/limpa as tabelas a cada teste (`reset_db`, autouse).
- **`auth_headers`** *(fixture)* — faz cadastro + login automaticamente e devolve o cabeçalho com o
  token, para que cada teste já comece autenticado sem repetir código.
- **`test_isolamento_entre_usuarios`** (`test_vendas.py`) — garante a regra de segurança crucial: um
  usuário **não consegue acessar a venda de outro** (recebe 404), mesmo conhecendo o `id`.
- **`prophet_necessario`** (`test_predict.py`) — *skip* condicional: detecta uma vez se o backend Stan do
  Prophet treina neste ambiente; se não, pula **apenas** os testes que realmente treinam o modelo.
- Os testes de sincronização usam o `tmp_path` do pytest para criar CSVs reais em disco e verificar
  criação, modificação (via `mtime`) e remoção.

Execução: `pytest` (configurado em `pyproject.toml` com `testpaths=["tests"]`).

---

## 12. Diagramas — `diagramas/`

Modelagem visual do sistema (UML e modelo de dados), útil para apresentações e onboarding.

| Arquivo                                  | O que mostra                                                              |
| ---------------------------------------- | ------------------------------------------------------------------------ |
| `Use_Cases_Visia.svg`                    | **Diagrama de Casos de Uso** — atores e interações (cadastrar, importar, prever, etc.). |
| `Diagrama_De_Classe_Visia.html`          | **Diagrama de Classes** — modelos/serviços e seus relacionamentos.       |
| `Diagrama_Entidade_Relacionamento.html`  | **Diagrama ER** — tabelas do banco e suas chaves/relacionamentos.        |
| `Diagrama_Sequencia.png`                 | **Diagrama de Sequência** — fluxo de uma requisição (ex.: gerar previsão).|

> Os diagramas em `.html` são interativos; o ER reflete exatamente as tabelas descritas na
> [Seção 6](#6-modelos-tabelas--appmodels).

---

## 13. Documentos de Engenharia — `docs/` (BRD e ERS)

A pasta `docs/` reúne os **documentos formais de engenharia de software** que fundamentam o projeto.
São o "porquê" e o "o quê" do sistema (enquanto este Documento Norteador explica o "como").

### `docs/BRD_Visia.pdf` — *Business Requirements Document*

O **Documento de Requisitos de Negócio** descreve o **problema de negócio** e os objetivos da solução,
em linguagem voltada para *stakeholders* (não técnica). Tipicamente contém:

- **Contexto e justificativa:** organizações em ambientes **VUCA** (volatilidade, incerteza,
  complexidade e ambiguidade) precisam transformar dados históricos em previsões acionáveis.
- **Objetivos de negócio:** previsões de curto (≤ 30 dias), médio (≤ 180 dias) e longo prazo, com
  alertas de anomalias e interface acessível a não-técnicos.
- **Perfis de usuário e RBAC:** Administrador, Gestor, Analista Financeiro e Usuário Geral, com regras
  de negócio (ex.: **RN04** — só Gestor ou superior exporta relatórios brutos).
- **Pilares de segurança:** a **Tríade CIA** (Confidencialidade, Integridade, Disponibilidade) e
  conformidade com **ISO/IEC 27001** e **NIST SP 800-12**.
- **Critérios de aceitação e escopo do MVP.**

### `docs/ERS_Visia.pdf` — *Especificação de Requisitos de Software*

A **ERS** (equivalente ao *SRS — Software Requirements Specification*) traduz o BRD em **requisitos
técnicos verificáveis**. Tipicamente contém:

- **Requisitos Funcionais (RF):** o que o sistema deve fazer (importar CSV, autenticar via JWT, treinar
  o modelo, exibir gráficos, organizar em pastas, sincronizar com o disco, etc.).
- **Requisitos Não-Funcionais (RNF):** desempenho, segurança (hash bcrypt, rate limiting, CORS),
  usabilidade, portabilidade (SQLite/PostgreSQL) e disponibilidade.
- **Regras de Negócio (RN)** e **rastreabilidade** entre requisitos, casos de uso e implementação.
- **Restrições técnicas:** stack obrigatória (FastAPI, Prophet, SQLAlchemy) e premissas.

> **Relação entre os documentos:** o **BRD** define *por que* e *para quem*; a **ERS** define *o que* o
> software precisa cumprir; e este **Documento Norteador** detalha *como* o código realiza tudo isso.
> O **README.md** é a porta de entrada resumida, com instalação e funcionalidades.

---

## 14. Arquivos de Configuração e Suporte

| Arquivo               | Função                                                                                       |
| --------------------- | -------------------------------------------------------------------------------------------- |
| `requirements.txt`    | Dependências Python com **versões fixas** (FastAPI, SQLAlchemy, Prophet, Pandas, etc.).      |
| `pyproject.toml`      | Configura **ruff** (lint), **pytest** (testes) e **bandit** (segurança).                      |
| `.env` / `.env.example` | Variáveis de ambiente. O `.example` é o modelo versionado; o `.env` real **não** vai p/ Git. |
| `.secrets.baseline`   | Linha de base do **detect-secrets** (define o que já foi auditado no scan de segredos).        |
| `docker-compose.yml`  | Sobe um **PostgreSQL 15** em container, alternativa ao SQLite para produção.                  |
| `iniciar.bat`         | Inicializador para Windows: cria venv, instala dependências, prepara a IA e sobe o servidor.  |
| `_setup_ia.py`        | Verifica/conserta a instalação do Prophet (backend **CmdStan/Stan**).                        |
| `LICENSE.txt`         | Licença **MIT**.                                                                              |
| `README.md`           | Documentação principal: visão, funcionalidades, perfis de usuário e instalação.              |

### `requirements.txt` (principais pacotes)

`fastapi`, `uvicorn` (servidor ASGI), `sqlalchemy` (ORM), `bcrypt` + `python-jose` (segurança),
`python-multipart` (upload), `slowapi` (rate limit), `pydantic` + `pydantic-settings` (validação/config),
`email-validator`, `pandas` (planilhas), `prophet` (IA), `pytest` + `httpx` (testes).

### `pyproject.toml`

- **ruff** (`line-length=100`, regras `E/W/F`, ignora `E501`) — lint do job `lint` do CI.
- **pytest** (`testpaths=["tests"]`, `-q`, filtra `DeprecationWarning`).
- **bandit** (exclui `tests`, `.venv`, `venv`) — SAST do job `sast`.

### `docker-compose.yml`

Sobe o serviço `db` (`postgres:15-alpine`) com credenciais vindas de variáveis de ambiente/`.env`
(**senhas nunca são versionadas** — `POSTGRES_PASSWORD` é obrigatória) e persiste os dados num volume
nomeado. Para usá-lo, basta ajustar `DATABASE_URL` no `.env` para a string de conexão do PostgreSQL.

### `iniciar.bat` (Windows, "duplo clique")

Detecta o Python, cria um ambiente virtual em `C:\visia_env` (com **fallback** para o Python do sistema
caso políticas como Device Guard bloqueiem o venv), instala as dependências **apenas uma vez** (marca
com `.visia_deps_ok`), roda `_setup_ia.py`, cria o `.env` a partir do `.env.example` se faltar e inicia
o `uvicorn`, abrindo o navegador em `http://127.0.0.1:8000`.

### `_setup_ia.py`

Conserta um problema comum do Prophet em que **falta o `makefile` do CmdStan**: copia do CmdStan do
sistema ou, em último caso, **instala o CmdStan automaticamente** (~5 min, só na primeira vez). Nunca
bloqueia o servidor — apenas avisa se o Prophet não estiver disponível.

---

## 15. Pipelines de CI/CD — `.github/workflows/`

Automação de qualidade e segurança executada a cada `push`/`pull request` no GitHub.

### `ci.yml` — qualidade e segurança

| Job                  | Ferramenta       | O que faz                                                                |
| -------------------- | ---------------- | ----------------------------------------------------------------------- |
| `lint`               | **ruff**         | Verifica estilo e erros reais (imports/variáveis não usados).           |
| `sast`               | **bandit**       | Análise estática de segurança do código (falha em severidade média/alta).|
| `secret-scan`        | **detect-secrets** | Procura senhas/chaves vazadas nos arquivos versionados.                |
| `dependency-audit`   | **pip-audit**    | Audita CVEs nas dependências (advisório — não bloqueia o merge).        |
| `tests`              | **pytest**       | Roda toda a suíte de testes em Python 3.11.                             |

### `codeql.yml` — SAST aprofundado

Análise **CodeQL** da GitHub (queries `security-and-quality`) que detecta padrões de bugs e
vulnerabilidades (injeção, *path traversal*, etc.) seguindo o fluxo de dados do código. Roda em
push/PR e também **agendado** (toda segunda-feira às 06:00 UTC).

---

## 16. Glossário Técnico

| Termo                     | Significado                                                                                       |
| ------------------------- | ------------------------------------------------------------------------------------------------ |
| **FastAPI**               | Framework web Python para construir APIs REST rápidas, com validação e docs automáticas.          |
| **Prophet**               | Biblioteca da Meta para previsão de séries temporais com tendência, sazonalidade e feriados.       |
| **SQLAlchemy / ORM**      | Mapeia tabelas do banco em classes Python (Object-Relational Mapping).                            |
| **Pydantic**              | Validação de dados e *settings* baseada em type hints.                                            |
| **JWT**                   | *JSON Web Token* — token assinado que comprova a identidade do usuário em cada requisição.        |
| **bcrypt**                | Algoritmo de hash de senhas com *salt*, resistente a força bruta.                                 |
| **CORS**                  | Política que define quais domínios podem chamar a API pelo navegador.                             |
| **Rate limiting**         | Limite de requisições por IP/tempo, contra abuso e força bruta.                                   |
| **WAL**                   | *Write-Ahead Logging* do SQLite — permite leitura concorrente com escrita.                        |
| **Cross-validation**      | Técnica para estimar o erro real do modelo em dados não vistos.                                   |
| **MAE / MAPE / RMSE**     | Métricas de erro de previsão (absoluto, percentual e quadrático).                                 |
| **Changepoint**           | Ponto no tempo em que a tendência muda de ritmo (aceleração/desaceleração).                       |
| **Intervalo de confiança**| Faixa (aqui 95%) dentro da qual o valor real deve cair; cresce com o horizonte.                   |
| **SPA**                   | *Single Page Application* — interface que navega sem recarregar a página.                         |

---

### Resumo final

O **Visia** é um backend **FastAPI** bem organizado em camadas, com um motor de IA (**Prophet**) isolado
nos serviços, persistência via **SQLAlchemy** (SQLite ou PostgreSQL) e uma interface web autocontida. O
fluxo essencial é:

> **importar/sincronizar dados → armazenar no banco → treinar o modelo → exibir previsões e alertas**

Cada pasta tem uma responsabilidade única, há **testes automatizados** cobrindo os fluxos críticos e
**pipelines de CI/CD** garantindo qualidade e segurança a cada alteração — o que torna o código fácil de
entender, manter e evoluir.
```
