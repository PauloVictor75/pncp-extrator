# PNCP Extrator — imagem mínima: Python slim + requests (sem navegador, sem OCR).
FROM python:3.11-slim

LABEL org.opencontainers.image.title="PNCP Extrator" \
      org.opencontainers.image.description="Resultados das contratações públicas do PNCP em CSV" \
      org.opencontainers.image.licenses="MIT"

ENV TZ=America/Sao_Paulo \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pncp_client.py pncp_normalizer.py pncp_extrator.py enriquecimento.py ./

# Usuário sem privilégios; a saída fica no volume montado
RUN useradd --create-home extrator && mkdir -p /app/saida_pncp && chown extrator /app/saida_pncp
USER extrator
VOLUME ["/app/saida_pncp"]

CMD ["python", "pncp_extrator.py"]
