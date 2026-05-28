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

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [INFO] Criando ambiente virtual em %VENV_DIR%...
    python -m venv "%VENV_DIR%"
    if %errorlevel% neq 0 (
        echo [ERRO] Falha ao criar ambiente virtual.
        pause
        exit /b 1
    )
)

call "%VENV_DIR%\Scripts\activate.bat"

echo [1/3] Instalando dependencias...
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)

echo [2/3] Configurando motor de IA...
python _setup_ia.py
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

python -m uvicorn app.main:app --reload

echo.
echo  Servidor encerrado.
pause
