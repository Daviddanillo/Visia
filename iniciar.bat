@echo off
chcp 65001 >nul
echo.
echo  =========================================
echo   Visia Intelligence - Iniciando servidor
echo  =========================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python nao encontrado. Instale em https://python.org
    pause
    exit /b 1
)

set VENV_DIR=C:\visia_env
set "PYEXE="
set "PIP_USER="

REM ── Tenta criar/usar um ambiente virtual ──────────────────────────────────
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [INFO] Criando ambiente virtual em %VENV_DIR%...
    python -m venv "%VENV_DIR%" 2>nul
)

REM Verifica se o python do venv EXECUTA (politicas como Device Guard podem
REM bloquear executaveis recem-criados dentro do venv).
if exist "%VENV_DIR%\Scripts\python.exe" call :testar_venv

REM Sem venv utilizavel: usa o Python do sistema (ja permitido pela politica).
if not defined PYEXE (
    echo [AVISO] Ambiente virtual indisponivel ^(possivel politica de seguranca^).
    echo [AVISO] Usando o Python do sistema com instalacao no perfil do usuario.
    set "PYEXE=python"
    set "PIP_USER=--user"
)

echo.
echo [1/3] Instalando dependencias...
REM IMPORTANTE: usar "python -m pip" (NUNCA o pip.exe), que e bloqueado pelo
REM Device Guard por ser um executavel gerado/nao assinado.
"%PYEXE%" -m pip install --upgrade pip %PIP_USER% --quiet
"%PYEXE%" -m pip install -r requirements.txt %PIP_USER% --quiet
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao instalar dependencias.
    echo        Se aparecer bloqueio do Device Guard, peca ao TI para liberar
    echo        o Python, ou rode este .bat em uma maquina sem essa politica.
    pause
    exit /b 1
)

echo [2/3] Configurando motor de IA...
"%PYEXE%" _setup_ia.py
if %errorlevel% neq 0 (
    echo [AVISO] Configuracao da IA falhou. Previsao pode nao funcionar.
)

if not exist ".env" (
    echo [INFO] Criando .env a partir do .env.example...
    copy .env.example .env >nul
    echo [AVISO] Edite o arquivo .env com uma SECRET_KEY segura antes de usar em producao.
)

echo [3/3] Iniciando servidor...
echo.
echo  Acesse no navegador: http://127.0.0.1:8000
echo  Documentacao da API:  http://127.0.0.1:8000/docs
echo  Para encerrar, pressione Ctrl+C
echo.

start "" cmd /c "timeout /t 2 >nul && start http://127.0.0.1:8000"

"%PYEXE%" -m uvicorn app.main:app --reload

echo.
echo  Servidor encerrado.
pause
exit /b 0

REM ── Sub-rotina: define PYEXE se o python do venv executar normalmente ──────
:testar_venv
"%VENV_DIR%\Scripts\python.exe" -c "pass" >nul 2>&1
if %errorlevel%==0 set "PYEXE=%VENV_DIR%\Scripts\python.exe"
goto :eof
