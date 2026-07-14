# Imagem da aplicação Visia (FastAPI).
# Banco: PostgreSQL/Neon via DATABASE_URL, ou SQLite local (volume em /data).
FROM python:3.11-slim

# Evita .pyc e força logs sem buffer (aparecem na hora no `docker logs`).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependências de sistema para compilar pandas/prophet (cmdstanpy) quando não há wheel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências primeiro (camada cacheada enquanto requirements.txt não muda).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação.
COPY . .

# Diretório onde o arquivo SQLite (dados.db) vive — montado como volume no compose.
RUN mkdir -p /data

EXPOSE 8000

# O Render injeta a porta em $PORT; localmente cai no padrão 8000.
# Forma shell (sem colchetes) para o ${PORT:-8000} ser expandido.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
