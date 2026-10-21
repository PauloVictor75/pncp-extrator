#!/usr/bin/env python3
"""
🔗 PNCP API CLIENT
==================
Cliente REST para a API pública do Portal Nacional de Contratações Públicas.
Sem autenticação, sem CAPTCHA — API aberta e paginada.

Base URL consulta: https://pncp.gov.br/api/consulta/v1/
Base URL dados:    https://pncp.gov.br/api/pncp/v1/

A listagem por data de publicação EXIGE a modalidade (sem ela a API responde 400),
então o extrator percorre uma modalidade por vez.
"""

import logging
import time
from email.utils import parsedate_to_datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

CONSULTA_BASE = "https://pncp.gov.br/api/consulta/v1"
PNCP_BASE     = "https://pncp.gov.br/api/pncp/v1"

# Tabela de modalidades do PNCP (codigoModalidadeContratacao)
MODALIDADES = {
    1:  "Leilão - Eletrônico",
    2:  "Diálogo Competitivo",
    3:  "Concurso",
    4:  "Concorrência - Eletrônica",
    5:  "Concorrência - Presencial",
    6:  "Pregão - Eletrônico",
    7:  "Pregão - Presencial",
    8:  "Dispensa de Licitação",
    9:  "Inexigibilidade",
    10: "Manifestação de Interesse",
    11: "Pré-qualificação",
    12: "Credenciamento",
    13: "Leilão - Presencial",
}

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "PNCP-Extrator/2.0 (pesquisa-publica)",
}

_RETENTAVEIS = (429, 500, 502, 503, 504)


class FalhaAPI(Exception):
    """A API não respondeu direito mesmo depois das novas tentativas."""


def _segundos_retry_after(valor: Optional[str], padrao: int = 10) -> int:
    """Retry-After pode vir em segundos ou como data HTTP."""
    if not valor:
        return padrao
    try:
        return max(0, int(valor))
    except ValueError:
        pass
    try:
        return max(0, int(parsedate_to_datetime(valor).timestamp() - time.time()))
    except (TypeError, ValueError):
        return padrao


class PNCPClient:
    """Cliente HTTP com intervalo mínimo entre chamadas e novas tentativas."""

    def __init__(self, delay_entre_req: float = 0.5, max_retries: int = 5, session=None):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)
        self.delay = delay_entre_req
        self.max_retries = max_retries
        self._ultima_req = 0.0

    # ------------------------------------------------------------------
    # Camada de transporte
    # ------------------------------------------------------------------

    def _esperar_vez(self):
        espera = self.delay - (time.time() - self._ultima_req)
        if espera > 0:
            time.sleep(espera)

    def _get(self, url: str, params: Optional[dict] = None):
        """
        GET com intervalo mínimo e novas tentativas.
        Devolve o JSON, ou None quando a API diz que não há nada (204/404).
        Levanta FalhaAPI em qualquer outro caso — quem chama decide o que fazer,
        em vez de confundir "a API falhou" com "não há dados".
        """
        motivo = ""
        for tentativa in range(1, self.max_retries + 1):
            self._esperar_vez()
            try:
                resp = self.session.get(url, params=params, timeout=30)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                self._ultima_req = time.time()
                motivo = exc.__class__.__name__
                logger.warning(f"🔌 {motivo} em {url}, tentativa {tentativa}/{self.max_retries}")
                time.sleep(2 ** tentativa)
                continue
            self._ultima_req = time.time()

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (204, 404):
                return None
            if resp.status_code in _RETENTAVEIS:
                motivo = f"HTTP {resp.status_code}"
                if resp.status_code == 429:
                    wait = _segundos_retry_after(resp.headers.get("Retry-After"))
                else:
                    wait = 2 ** tentativa
                logger.warning(f"🔄 {motivo} em {url}, tentativa {tentativa}/{self.max_retries} em {wait}s")
                time.sleep(wait)
                continue
            raise FalhaAPI(f"HTTP {resp.status_code} em {url}: {resp.text[:200]}")

        raise FalhaAPI(f"{motivo} após {self.max_retries} tentativas: {url}")

    # ------------------------------------------------------------------
    # Endpoint 1 — Contratações por data de publicação (busca em lote)
    # ------------------------------------------------------------------

    def listar_contratacoes_publicacao(
        self,
        data_inicial: str,   # "YYYYMMDD"
        data_final: str,     # "YYYYMMDD"
        modalidade: int,
        pagina: int = 1,
        tamanho: int = 50,
    ) -> dict:
        """
        GET /v1/contratacoes/publicacao
        Retorna {"data": [...], "totalRegistros": N, "totalPaginas": N}.
        A situação que vem aqui é a da publicação (quase sempre "Divulgada"),
        não a atual — o que conta é o item ter resultado.
        """
        url = f"{CONSULTA_BASE}/contratacoes/publicacao"
        params = {
            "dataInicial":                 data_inicial,
            "dataFinal":                   data_final,
            "codigoModalidadeContratacao": modalidade,
            "pagina":                      pagina,
            "tamanhoPagina":               tamanho,
        }
        return self._get(url, params) or {"data": [], "totalRegistros": 0, "totalPaginas": 0}

    # ------------------------------------------------------------------
    # Endpoint 2 — Itens de uma compra específica
    # ------------------------------------------------------------------

    def listar_itens_compra(self, cnpj: str, ano: int, sequencial: int) -> list:
        """GET /v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens"""
        url = f"{PNCP_BASE}/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens"
        return _como_lista(self._get(url), "itens")

    # ------------------------------------------------------------------
    # Endpoint 3 — Resultados (propostas/vencedores) de um item
    # ------------------------------------------------------------------

    def listar_resultados_item(self, cnpj: str, ano: int, sequencial: int, numero_item: int) -> list:
        """GET /v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens/{numeroItem}/resultados"""
        url = (
            f"{PNCP_BASE}/orgaos/{cnpj}/compras/{ano}/{sequencial}"
            f"/itens/{numero_item}/resultados"
        )
        return _como_lista(self._get(url), "resultados")


def _como_lista(dados, chave: str) -> list:
    """Alguns endpoints devolvem a lista direto, outros um dict com "data"."""
    if isinstance(dados, list):
        return dados
    if isinstance(dados, dict):
        return dados.get("data") or dados.get(chave) or []
    return []
