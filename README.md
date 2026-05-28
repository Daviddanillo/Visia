<div align="center">

<img src="https://img.shields.io/badge/Visia-Sistema%20Preditivo-4A90D9?style=for-the-badge&logo=chartdotjs&logoColor=white"/>

# 📈 Visia — Sistema de Previsão de Tendências de Mercado

> Plataforma de **Inteligência Artificial Preditiva** para organizações corporativas,
> transformando dados históricos em insights acionáveis de desempenho financeiro.

[![Versão](https://img.shields.io/badge/Versão-MVP%201.0-blue?style=flat-square)](https://github.com/Daviddanillo/Visia)
[![Status](https://img.shields.io/badge/Status-Em%20Desenvolvimento-yellow?style=flat-square)](https://github.com/Daviddanillo/Visia)
[![Idioma](https://img.shields.io/badge/Idioma-PT--BR-blueviolet?style=flat-square)](https://github.com/Daviddanillo/Visia)
[![Licença](https://img.shields.io/badge/Licença-MIT-green?style=flat-square)](./LICENSE)

</div>

---

## 📋 Sumário

- [Sobre o Projeto](#-sobre-o-projeto)
- [Funcionalidades](#-funcionalidades)
- [Arquitetura e Segurança](#-arquitetura-e-segurança)
- [Perfis de Usuário](#-perfis-de-usuário)
- [Requisitos do Sistema](#-requisitos-do-sistema)
- [Instalação e Configuração](#-instalação-e-configuração)
- [Como Usar](#-como-usar)
- [Casos de Uso](#-casos-de-uso)
- [Critérios de Aceitação](#-critérios-de-aceitação)
- [Escopo do MVP](#-escopo-do-mvp)
- [Rastreabilidade de Requisitos](#-rastreabilidade-de-requisitos)
- [Estrutura do Repositório](#-estrutura-do-repositório)
- [Equipe](#-equipe)
- [Documentação](#-documentação)
- [Licença](#-licença)

---

## 🧠 Sobre o Projeto

O **Visia** é uma solução corporativa baseada em **Inteligência Artificial Preditiva**,
desenvolvida para organizações que operam em ambientes **VUCA**
*(Volatility, Uncertainty, Complexity and Ambiguity)* — realidade global marcada
por mercados altamente dinâmicos e de difícil previsão.

### 🎯 O Problema

Organizações modernas acumulam volumes massivos de dados, mas carecem de
infraestrutura analítica para transformá-los em **previsões confiáveis e acionáveis**.
Os principais gargalos identificados foram:

| Gargalo | Descrição |
|---|---|
| 📉 Baixa qualidade de dados | Dados internos inconsistentes ou mal estruturados |
| 🌪️ Volatilidade externa | Variáveis de mercado que mudam de forma rápida e imprevisível |
| 🧱 Limitações técnicas e humanas | Falta de infraestrutura analítica especializada |

### ✅ O que o Visia entrega

- 📅 Previsões de desempenho financeiro de **curto prazo (até 30 dias)**
- 📅 Previsões de desempenho financeiro de **médio prazo (até 180 dias)**
- 📅 Indicações de tendências de **longo prazo** *(sinalizadas como "⚠️ Altamente Voláteis")*
- 🔔 Alertas automáticos de anomalias e variações expressivas
- 🖥️ Interface visual e intuitiva para usuários sem perfil técnico

---

## ⚙️ Funcionalidades

### 🗄️ Módulo de Dados
- 📥 Importação de dados históricos nos formatos **CSV** e **JSON**
- 🧹 Tratamento, limpeza e classificação seguindo a **Tríade CIA**
- 🔒 Criptografia de dados sensíveis **em repouso e em trânsito** (TLS/HTTPS)
- 📋 Registro completo de **logs de auditoria** para todas as operações

### 🤖 Módulo Preditivo
- ⚡ Execução de **modelos de I.A. Preditiva** treinados sobre dados da organização
- 📊 Exibição do **grau de confiança** e **margem de erro** em cada previsão
- ⚠️ Marcação automática de previsões de longo prazo como **"Altamente Voláteis"**
- 🔔 Emissão de **alertas automáticos** para anomalias detectadas

### 📊 Módulo de Interface
- 📉 Painéis e gráficos interativos interpretáveis por qualquer usuário
- 📆 Painel dedicado de **métricas de desempenho semanal**
- 🗂️ Histórico completo de previsões com comparação a resultados reais
- 📤 Exportação de relatórios em **PDF** e **CSV** (perfis autorizados)

### 🛡️ Módulo de Acesso
- 👤 Cadastro, autenticação e gestão de perfis com **RBAC**
  *(Role-Based Access Control)*
- 🔑 Controle rigoroso de acesso por nível de perfil
- 📖 Seção de **documentação integrada** à interface

---

## 🏗️ Arquitetura e Segurança

O Visia foi projetado sobre os três pilares da **Tríade CIA de Segurança da Informação**:

| Pilar | Significado | Como é implementado |
|---|---|---|
| 🔐 **Confidencialidade** | Acesso restrito conforme o perfil | RBAC + autenticação por níveis |
| ✅ **Integridade** | Dados protegidos contra alterações indevidas | Logs de auditoria + criptografia |
| 🟢 **Disponibilidade** | Sistema acessível sempre que necessário | Alta disponibilidade + mínimo de downtime |

### 🔑 Segurança Técnica
- Comunicação via **HTTPS** com criptografia **TLS** em todas as requisições
- Dados em repouso criptografados com protocolos reconhecidos pelo mercado
- Fontes externas exigem **certificados de procedência e integridade validados**
- **Zero tolerância** a alterações de dados sem rastro de auditoria
- Conformidade com **ISO/IEC 27001:2022** e **NIST SP 800-12**

---

## 👥 Perfis de Usuário

| Perfil | Nível | Principais Permissões |
|---|---|---|
| 🔴 **Administrador** | Total | Gerenciar usuários, importar dados, auditar logs e configurar o sistema |
| 🟠 **Gestor** | Elevado | Visualizar painéis, gerar e **exportar** relatórios, receber alertas |
| 🟡 **Analista Financeiro** | Padrão | Selecionar ativos, gerar previsões, consultar histórico e receber alertas |
| 🟢 **Usuário Geral** | Básico | Visualizar painéis e consultar documentação |

> ⚠️ **Regra de Negócio (RN04):** Apenas perfis **Gestor ou superior** podem
> exportar relatórios brutos de tendências de mercado.

---

## 📦 Requisitos do Sistema

### Ambiente
- Navegador moderno: **Google Chrome**, **Mozilla Firefox** ou **Microsoft Edge**
- Sem instalação de software adicional
- Conexão com internet (HTTPS/TLS obrigatório)

### Dados
- Arquivos históricos em **CSV** ou **JSON**, devidamente estruturados
- Qualidade mínima garantida pela organização contratante
- Fontes externas devem possuir **certificados de procedência validados**

---

## 🚀 Instalação e Configuração

Existem **duas formas** de instalar e executar o Visia. Escolha a que melhor se adequa ao seu ambiente:

---

### 🐍 Versão 1 — Via Python (Manual)

> Recomendado para desenvolvedores e ambientes Linux/macOS/Windows com Python instalado.

```bash
# Passo 1 — Clone o repositório
git clone https://github.com/Daviddanillo/Visia.git

# Passo 2 — Acesse o diretório do projeto
cd Visia

# Passo 3 — Crie e ative o ambiente virtual
python -m venv venv

# Ativação no Linux/macOS:
source venv/bin/activate

# Ativação no Windows:
venv\Scripts\activate

# Passo 4 — Instale as dependências
pip install -r requirements.txt

# Passo 5 — Configure as variáveis de ambiente
cp .env.example .env
# Abra o arquivo .env e preencha com suas configurações locais

# Passo 6 — Execute a aplicação
python app.py
```

---

### 🪟 Versão 2 — Via Instalador `.bat` (Windows)

> Recomendado para usuários finais no Windows que preferem uma inicialização rápida e automática.

```bash
# Passo 1 — Clone o repositório
git clone https://github.com/Daviddanillo/Visia.git

# Passo 2 — Acesse o diretório do projeto
cd Visia
```

**Passo 3 —** Localize o arquivo **`iniciar.bat`** na raiz do projeto e execute-o com **duplo clique**:

```
📁 Visia/
└── ▶️ iniciar.bat   ← Execute este arquivo
```

> ✅ O script irá configurar o ambiente e iniciar a aplicação automaticamente,
> sem necessidade de configuração manual.

---
