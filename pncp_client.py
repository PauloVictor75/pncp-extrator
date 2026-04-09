#!/usr/bin/env python3
"""
🔗 PNCP API CLIENT
==================
Cliente REST para a API pública do Portal Nacional de Contratações Públicas.
Sem autenticação, sem CAPTCHA — API aberta e paginada.

Base URL consulta: https://pncp.gov.br/api/consulta/v1/
Base URL dados:    https://pncp.gov.br/api/pncp/v1/

Situações de compra conhecidas:
  1 = Divulgada no PNCP
  2 = Sessão pública
  3 = Em julgamento
  4 = Adjudicada
  5 = Homologada
  6 = Em recurso
  7 = Encerrada
  8 = Cancelada / Anulada / Revogada
  9 = Suspensa
"""

import requests
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

CONSULTA_BASE  = "https://pncp.gov.br/api/consulta/v1"
PNCP_BASE      = "https://pncp.gov.br/api/pncp/v1"

# Situações alvo: Homologada (5) e Encerrada (7)
SITUACOES_ALVO = {5, 7}

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "PNCP-Extrator/1.0 (pesquisa-publica)",
}


class PNCPClient:
    """Cliente HTTP simples com retry e rate-limit respeitoso."""

    def __init__(self, delay_entre_req: float = 0.5, max_retries: int = 5):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.delay = delay_entre_req
        self.max_retries = max_retries
        self._ultima_req = 0.0

    # ------------------------------------------------------------------
    # Camada de transporte
    # ------------------------------------------------------------------

    def _get(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        """GET com throttle, retry exponencial e logging de erro."""
        # respeitar delay entre requisições
        espera = self.delay - (time.time() - self._ultima_req)
        if espera > 0:
            time.sleep(espera)

        for tentativa in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                self._ultima_req = time.time()

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code == 204:   # sem conteúdo — normal
                    return None

                if resp.status_code == 429:   # rate limit
                    wait = int(resp.headers.get("Retry-After", 10))
                    logger.warning(f"⏳ Rate-limit 429, aguardando {wait}s...")
                    time.sleep(wait)
                    continue

                if resp.status_code in (500, 502, 503, 504):
                    wait = 2 ** tentativa
                    logger.warning(f"🔄 HTTP {resp.status_code} em {url}, retry {tentativa}/{self.max_retries} em {wait}s")
                    time.sleep(wait)
                    continue

                if resp.status_code == 404:
                    logger.debug(f"404 em {url}")
                    return None

                logger.error(f"❌ HTTP {resp.status_code} em {url}: {resp.text[:200]}")
                return None

            except requests.exceptions.Timeout:
                logger.warning(f"⏱ Timeout em {url}, retry {tentativa}/{self.max_retries}")
                time.sleep(2 ** tentativa)
            except requests.exceptions.ConnectionError as exc:
                logger.warning(f"🔌 ConnectionError em {url}: {exc}, retry {tentativa}/{self.max_retries}")
                time.sleep(2 ** tentativa)

        logger.error(f"❌ Falha após {self.max_retries} tentativas: {url}")
        return None

    # ------------------------------------------------------------------
    # Endpoint 1 — Contratações por data de publicação (busca em lote)
    # ------------------------------------------------------------------

    def listar_contratacoes_publicacao(
        self,
        data_inicial: str,   # "YYYYMMDD"
        data_final: str,     # "YYYYMMDD"
        pagina: int = 1,
        tamanho: int = 50,
    ) -> Optional[dict]:
        """
        GET /v1/contratacoes/publicacao
        Retorna {"data": [...], "totalRegistros": N, "totalPaginas": N}
        Sem filtro de situação — filtramos em memória pois a API pública
        não expõe o parâmetro situacaoCompraId neste endpoint.
        """
        url = f"{CONSULTA_BASE}/contratacoes/publicacao"
        params = {
            "dataInicial":   data_inicial,
            "dataFinal":     data_final,
            "pagina":        pagina,
            "tamanhoPagina": tamanho,
            "codigoModalidadeContratacao": 5
        }
        return self._get(url, params)

    # ------------------------------------------------------------------
    # Endpoint 2 — Itens de uma compra específica
    # ------------------------------------------------------------------

    def listar_itens_compra(self, cnpj: str, ano: int, sequencial: int) -> Optional[list]:
        """
        GET /v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens
        Retorna lista de itens (cada item tem número, descrição, valores, etc.)
        """
        url = f"{PNCP_BASE}/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens"
        dados = self._get(url)
        # alguns endpoints retornam lista direta, outros dict com "data"
        if isinstance(dados, list):
            return dados
        if isinstance(dados, dict):
            return dados.get("data") or dados.get("itens") or []
        return []

    # ------------------------------------------------------------------
    # Endpoint 3 — Resultados (propostas/vencedores) de um item
    # ------------------------------------------------------------------

    def listar_resultados_item(
        self, cnpj: str, ano: int, sequencial: int, numero_item: int
    ) -> Optional[list]:
        """
        GET /v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens/{numeroItem}/resultados
        Retorna lista com fornecedor vencedor, valor homologado, CNPJ fornecedor, etc.
        """
        url = (
            f"{PNCP_BASE}/orgaos/{cnpj}/compras/{ano}/{sequencial}"
            f"/itens/{numero_item}/resultados"
        )
        dados = self._get(url)
        if isinstance(dados, list):
            return dados
        if isinstance(dados, dict):
            return dados.get("data") or dados.get("resultados") or []
        return []

    # ------------------------------------------------------------------
    # Endpoint 4 — Detalhe de uma compra (confirmar situação / pegar extra)
    # ------------------------------------------------------------------

    def detalhar_compra(self, cnpj: str, ano: int, sequencial: int) -> Optional[dict]:
        """
        GET /v1/orgaos/{cnpj}/compras/{ano}/{sequencial}
        Retorna objeto completo da compra incluindo situacaoCompraId atualizado.
        """
        url = f"{PNCP_BASE}/orgaos/{cnpj}/compras/{ano}/{sequencial}"
        return self._get(url)
