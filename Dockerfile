# Imagem de produção do Visia Intelligence (FastAPI + Prophet)
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Dependências de sistema: compilador (fallback p/ builds do Prophet/cmdstan).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependências primeiro (melhor cache de build).
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Garante que o backend do Prophet importa (falha cedo se algo faltar).
RUN python -c "import prophet; print('prophet OK')"

# Código da aplicação.
COPY . .

# Render injeta a porta em $PORT; em local cai para 8000.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=*"]
