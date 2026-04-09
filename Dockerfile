# ─────────────────────────────────────────────────────────────
# Dockerfile — PNCP Extrator
# Imagem mínima: Python slim + requests.
# SEM browser, SEM OCR, SEM TensorFlow.
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

LABEL maintainer="PNCP Extrator"
LABEL description="Extração automática de contratações homologadas do PNCP"
LABEL version="1.0"

WORKDIR /app

# Dependências de sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=America/Sao_Paulo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY pncp_client.py .
COPY pncp_normalizer.py .
COPY pncp_extrator.py .

# Criar diretório de saída persistente
RUN mkdir -p /app/saida_pncp

# Volume para persistir saída e progresso
VOLUME ["/app/saida_pncp"]

# ──────────────────────────────────────────────────────────────
# Uso:
#   docker build -t pncp-extrator .
#   docker run -v $(pwd)/saida_pncp:/app/saida_pncp pncp-extrator
#   docker run ... pncp-extrator python pncp_extrator.py --retomar
#   docker run ... pncp-extrator python pncp_extrator.py \
#       --inicio 20250701 --fim 20251231
# ──────────────────────────────────────────────────────────────
CMD ["python", "pncp_extrator.py"]
