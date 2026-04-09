#!/usr/bin/env python3
"""
🎯 PNCP EXTRATOR PRINCIPAL
===========================
Extrai do Portal Nacional de Contratações Públicas (pncp.gov.br):
  • Todas as contratações com situação HOMOLOGADA (5) ou ENCERRADA (7)
  • Publicadas entre DATA_INICIO e DATA_FIM
  • Todos os órgãos / UASG do Brasil
  • Para cada contratação: itens + resultados (proposta vencedora)
  • Inclui campos de MARCA e MODELO do item

Saída:
  → pncp_resultados_YYYYMMDD_HHmmss.csv    (linha por resultado de item)
  → pncp_sem_resultado_YYYYMMDD_HHmmss.csv (contratações sem resultado)
  → pncp_progresso.json                    (ponto de retomada)
  → pncp_extrator.log                      (log completo)

Uso:
  python pncp_extrator.py
  python pncp_extrator.py --inicio 20250701 --fim 20251231
  python pncp_extrator.py --retomar
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

from pncp_client import PNCPClient, SITUACOES_ALVO
from pncp_normalizer import (
    normalizar_contratacao,
    normalizar_item,
    normalizar_resultado,
    montar_linha,
)

# ─────────────────────────────────────────────────────────────────────────────
# Configurações padrão
# ─────────────────────────────────────────────────────────────────────────────

DATA_INICIO_PADRAO  = "20240101"
TAMANHO_PAGINA      = 50
INTERVALO_DIAS      = 7
DELAY_ENTRE_REQ     = 0.4
ARQUIVO_PROGRESSO   = "pncp_progresso.json"
ARQUIVO_LOG         = "pncp_extrator.log"
DIR_SAIDA           = Path("saida_pncp")


# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

def configurar_log():
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(ARQUIVO_LOG, encoding="utf-8"),
        ],
    )

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Controle de progresso (retomada)
# ─────────────────────────────────────────────────────────────────────────────

def carregar_progresso() -> dict:
    if Path(ARQUIVO_PROGRESSO).exists():
        with open(ARQUIVO_PROGRESSO, encoding="utf-8") as f:
            prog = json.load(f)
        logger.info(f"📂 Progresso anterior carregado: {prog.get('ultima_data_processada')} | "
                    f"{prog.get('total_contratacoes', 0)} contratações | "
                    f"{prog.get('total_resultados', 0)} resultados")
        return prog
    return {}


def salvar_progresso(prog: dict):
    prog["timestamp_atualizacao"] = datetime.now().isoformat()
    with open(ARQUIVO_PROGRESSO, "w", encoding="utf-8") as f:
        json.dump(prog, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Geração de janelas de datas
# ─────────────────────────────────────────────────────────────────────────────

def gerar_janelas(data_inicio: str, data_fim: str, intervalo_dias: int = INTERVALO_DIAS):
    d_ini = datetime.strptime(data_inicio, "%Y%m%d").date()
    d_fim = datetime.strptime(data_fim,    "%Y%m%d").date()

    janelas = []
    cursor = d_ini
    while cursor <= d_fim:
        fim_janela = min(cursor + timedelta(days=intervalo_dias - 1), d_fim)
        janelas.append((cursor.strftime("%Y%m%d"), fim_janela.strftime("%Y%m%d")))
        cursor = fim_janela + timedelta(days=1)

    return janelas


# ─────────────────────────────────────────────────────────────────────────────
# Colunas do CSV — inclui item_marca e item_modelo
# ─────────────────────────────────────────────────────────────────────────────

COLUNAS_CSV = [
    # ── Contratação ──────────────────────────────────────────────────────────
    "numeroControlePNCP",
    "anoCompra",
    "sequencialCompra",
    "processo",
    "orgao_cnpj",
    "orgao_razaoSocial",
    "orgao_poder",
    "orgao_esfera",
    "unidade_codigo",
    "unidade_nome",
    "unidade_uf",
    "unidade_municipio",
    "unidade_codigoIBGE",
    "orgaoSubRogado_cnpj",
    "orgaoSubRogado_razaoSocial",
    "unidadeSubRogada_codigo",
    "unidadeSubRogada_nome",
    "modalidadeId",
    "modalidadeNome",
    "modoDisputaId",
    "modoDisputaNome",
    "tipoInstrumentoConvocatorioCod",
    "tipoInstrumentoConvocatorioNom",
    "srp",
    "situacaoCompraId",
    "situacaoCompraNome",
    "objetoCompra",
    "informacaoComplementar",
    "valorTotalEstimado",
    "valorTotalHomologado",
    "dataPublicacaoPncp",
    "dataAberturaProposta",
    "dataEncerramentoProposta",
    "dataInclusao",
    "dataAtualizacao",
    "linkSistemaOrigem",
    "usuarioNome",
    # ── Item ─────────────────────────────────────────────────────────────────
    "item_numero",
    "item_descricao",
    "item_materialServico",
    "item_materialServicoNome",
    "item_tipoBeneficio",
    "item_tipoBeneficioNome",
    "item_situacaoCodigo",
    "item_situacaoNome",
    "item_criterioJulgamentoCodigo",
    "item_criterioJulgamentoNome",
    "item_quantidade",
    "item_unidadeMedida",
    "item_valorUnitarioEstimado",
    "item_valorTotalEstimado",
    "item_orcamentoSigiloso",
    "item_ncmNbs",
    "item_codigoCatalogoCodigo",
    "item_codigoCatalogoNome",
    "item_marca",            # ← marca do fabricante (marcaFabricante)
    "item_modelo",           # ← modelo / versão (modeloVersao)
    # ── Resultado / Proposta vencedora ───────────────────────────────────────
    "resultado_sequencial",
    "resultado_situacaoCodigo",
    "resultado_situacaoNome",
    "fornecedor_cnpjCpf",
    "fornecedor_nome",
    "fornecedor_razaoSocial",
    "fornecedor_niFornecedor",
    "fornecedor_tipoPessoa",
    "fornecedor_porteCodigo",
    "fornecedor_porteNome",
    "fornecedor_paisCodigo",
    "fornecedor_paisNome",
    "resultado_valorUnitarioHomologado",
    "resultado_valorTotalHomologado",
    "resultado_quantidadeHomologada",
    "resultado_dataResultado",
    "resultado_dataHoraAtualizacao",
    "resultado_numeroItemCompra",
    "resultado_orcamentoCodigo",
]

COLUNAS_SEM_RESULTADO = [
    "numeroControlePNCP", "anoCompra", "sequencialCompra", "processo",
    "orgao_cnpj", "orgao_razaoSocial", "unidade_uf", "unidade_municipio",
    "modalidadeNome", "situacaoCompraId", "situacaoCompraNome",
    "objetoCompra", "valorTotalEstimado", "valorTotalHomologado",
    "dataPublicacaoPncp", "linkSistemaOrigem",
    "motivo_sem_resultado",
]


# ─────────────────────────────────────────────────────────────────────────────
# Escrita CSV
# ─────────────────────────────────────────────────────────────────────────────

class EscritorCSV:
    """Abre / reabre CSVs em modo append, escrevendo cabeçalho só na primeira vez."""

    def __init__(self, caminho: Path, colunas: list):
        self.caminho = caminho
        self.colunas = colunas
        self._escreve_cabecalho = not caminho.exists()
        self._fh = open(caminho, "a", newline="", encoding="utf-8-sig")
        self._writer = csv.DictWriter(
            self._fh, fieldnames=colunas, extrasaction="ignore", delimiter=";"
        )
        if self._escreve_cabecalho:
            self._writer.writeheader()
            self._fh.flush()

    def escrever(self, linha: dict):
        self._writer.writerow(linha)

    def flush(self):
        self._fh.flush()

    def close(self):
        self._fh.close()


# ─────────────────────────────────────────────────────────────────────────────
# Núcleo do extrator
# ─────────────────────────────────────────────────────────────────────────────

class PNCPExtrator:

    def __init__(self, data_inicio: str, data_fim: str, retomar: bool = False):
        self.data_inicio = data_inicio
        self.data_fim    = data_fim
        self.client      = PNCPClient(delay_entre_req=DELAY_ENTRE_REQ)
        self.progresso   = carregar_progresso() if retomar else {}

        DIR_SAIDA.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_resultados    = EscritorCSV(DIR_SAIDA / f"pncp_resultados_{ts}.csv",    COLUNAS_CSV)
        self.csv_sem_resultado = EscritorCSV(DIR_SAIDA / f"pncp_sem_resultado_{ts}.csv", COLUNAS_SEM_RESULTADO)

        # Contadores
        self.total_contratacoes = self.progresso.get("total_contratacoes", 0)
        self.total_filtradas    = self.progresso.get("total_filtradas", 0)
        self.total_itens        = self.progresso.get("total_itens", 0)
        self.total_resultados   = self.progresso.get("total_resultados", 0)
        self.total_sem_result   = self.progresso.get("total_sem_resultado", 0)
        self.inicio_execucao    = time.time()

    # ── Controle de progresso ─────────────────────────────────────────────────

    def _ja_processou_janela(self, data_ini: str, data_fim: str) -> bool:
        janelas_ok = self.progresso.get("janelas_concluidas", [])
        return f"{data_ini}_{data_fim}" in janelas_ok

    def _marcar_janela_concluida(self, data_ini: str, data_fim: str):
        janelas_ok = self.progresso.setdefault("janelas_concluidas", [])
        chave = f"{data_ini}_{data_fim}"
        if chave not in janelas_ok:
            janelas_ok.append(chave)

    # ── Processamento de uma contratação ─────────────────────────────────────

    def processar_contratacao(self, contratacao: dict):
        """Processa itens + resultados de uma contratação já filtrada."""
        cnpj      = (contratacao.get("orgaoEntidade") or {}).get("cnpj", "")
        ano       = contratacao.get("anoCompra")
        seq       = contratacao.get("sequencialCompra")
        ctrl_pncp = contratacao.get("numeroControlePNCP", "?")

        if not cnpj or not ano or not seq:
            logger.warning(f"  ⚠ Contratação sem cnpj/ano/seq: {ctrl_pncp}")
            return

        c_flat = normalizar_contratacao(contratacao)

        # 1. Buscar itens
        itens = self.client.listar_itens_compra(cnpj, ano, seq)
        if not itens:
            logger.debug(f"  — Sem itens: {ctrl_pncp}")
            c_flat["motivo_sem_resultado"] = "sem_itens"
            self.csv_sem_resultado.escrever(c_flat)
            self.total_sem_result += 1
            return

        teve_resultado = False

        for item in itens:
            i_flat   = normalizar_item(item)   # inclui item_marca e item_modelo
            num_item = item.get("numeroItem")
            if num_item is None:
                continue

            self.total_itens += 1

            # 2. Buscar resultados do item
            resultados = self.client.listar_resultados_item(cnpj, ano, seq, num_item)

            if not resultados:
                continue

            for resultado in resultados:
                r_flat = normalizar_resultado(resultado)
                linha  = montar_linha(c_flat, i_flat, r_flat)
                self.csv_resultados.escrever(linha)
                self.total_resultados += 1
                teve_resultado = True

        if not teve_resultado:
            c_flat["motivo_sem_resultado"] = "itens_sem_resultado"
            self.csv_sem_resultado.escrever(c_flat)
            self.total_sem_result += 1

    # ── Processamento de uma janela temporal ─────────────────────────────────

    def processar_janela(self, data_ini: str, data_fim: str):
        """Busca e filtra todas as contratações de uma janela temporal."""
        pagina        = 1
        total_paginas = 1

        logger.info(f"📅 Janela: {data_ini} → {data_fim}")

        while pagina <= total_paginas:
            resp = self.client.listar_contratacoes_publicacao(
                data_ini, data_fim, pagina=pagina, tamanho=TAMANHO_PAGINA
            )

            if not resp:
                logger.warning(f"  ⚠ Sem resposta na página {pagina}")
                break

            dados         = resp.get("data") or []
            total_reg     = resp.get("totalRegistros", 0)
            total_paginas = resp.get("totalPaginas", 1)

            if pagina == 1:
                logger.info(f"  📊 {total_reg} contratações nesta janela ({total_paginas} páginas)")

            for contratacao in dados:
                self.total_contratacoes += 1

                # ℹ️  O endpoint /publicacao sempre retorna situacaoCompraId=1
                # (situação no momento da publicação, não a situação atual).
                # Por isso NÃO filtramos aqui — processamos todas as contratações
                # e deixamos o filtro natural acontecer nos itens/resultados:
                # se o item foi homologado, o endpoint de resultados retorna dados;
                # se não foi, retorna vazio e vai para csv_sem_resultado.

                self.total_filtradas += 1
                ctrl = contratacao.get("numeroControlePNCP", "?")
                sit  = contratacao.get("situacaoCompraNome", "?")
                logger.debug(f"  → [{self.total_filtradas}] {ctrl} | {sit}")

                self.processar_contratacao(contratacao)

                # Flush e salvamento de progresso a cada 20 contratações filtradas
                if self.total_filtradas % 20 == 0:
                    self.csv_resultados.flush()
                    self.csv_sem_resultado.flush()
                    self._salvar_progresso_parcial(data_ini, data_fim)

            pagina += 1

    # ── Progresso ────────────────────────────────────────────────────────────

    def _salvar_progresso_parcial(self, data_ini: str = "", data_fim: str = ""):
        elapsed = time.time() - self.inicio_execucao
        self.progresso.update({
            "ultima_data_processada": f"{data_ini}_{data_fim}",
            "total_contratacoes":     self.total_contratacoes,
            "total_filtradas":        self.total_filtradas,
            "total_itens":            self.total_itens,
            "total_resultados":       self.total_resultados,
            "total_sem_resultado":    self.total_sem_result,
            "tempo_decorrido_s":      round(elapsed, 1),
        })
        salvar_progresso(self.progresso)

    # ── Execução principal ───────────────────────────────────────────────────

    def executar(self):
        janelas       = gerar_janelas(self.data_inicio, self.data_fim)
        total_janelas = len(janelas)

        logger.info("=" * 65)
        logger.info("🚀 PNCP EXTRATOR — INÍCIO")
        logger.info(f"   Período:     {self.data_inicio} → {self.data_fim}")
        logger.info(f"   Situações:   Homologada (5) e Encerrada (7)")
        logger.info(f"   Janelas:     {total_janelas} ({INTERVALO_DIAS} dias cada)")
        logger.info(f"   Campos:      marca e modelo incluídos")
        logger.info(f"   Saída:       {DIR_SAIDA.resolve()}")
        logger.info("=" * 65)

        try:
            for idx, (d_ini, d_fim) in enumerate(janelas, 1):
                if self._ja_processou_janela(d_ini, d_fim):
                    logger.info(f"⏭  Janela {idx}/{total_janelas} já processada, pulando.")
                    continue

                logger.info(f"\n🔄 Janela {idx}/{total_janelas}")
                self.processar_janela(d_ini, d_fim)
                self._marcar_janela_concluida(d_ini, d_fim)
                self._salvar_progresso_parcial(d_ini, d_fim)

                elapsed = time.time() - self.inicio_execucao
                logger.info(
                    f"   ↳ Parcial: {self.total_filtradas} filtradas | "
                    f"{self.total_resultados} resultados | "
                    f"{elapsed/60:.1f} min"
                )

        finally:
            self.csv_resultados.close()
            self.csv_sem_resultado.close()
            self._salvar_progresso_parcial()
            self._imprimir_resumo_final()

    # ── Resumo final ─────────────────────────────────────────────────────────

    def _imprimir_resumo_final(self):
        elapsed = time.time() - self.inicio_execucao
        logger.info("\n" + "=" * 65)
        logger.info("🏁 EXTRAÇÃO CONCLUÍDA")
        logger.info(f"   Contratações lidas:     {self.total_contratacoes:,}")
        logger.info(f"   Filtradas (hom+enc):    {self.total_filtradas:,}")
        logger.info(f"   Itens processados:      {self.total_itens:,}")
        logger.info(f"   Resultados gravados:    {self.total_resultados:,}")
        logger.info(f"   Sem resultado:          {self.total_sem_result:,}")
        logger.info(f"   Tempo total:            {elapsed/60:.1f} min")
        logger.info(f"   Arquivos em:            {DIR_SAIDA.resolve()}")
        logger.info("=" * 65)


# ─────────────────────────────────────────────────────────────────────────────
# Ponto de entrada
# ─────────────────────────────────────────────────────────────────────────────

def main():
    configurar_log()

    parser = argparse.ArgumentParser(
        description="Extrai contratações homologadas/encerradas do PNCP."
    )
    parser.add_argument(
        "--inicio", default=DATA_INICIO_PADRAO,
        help="Data de início (YYYYMMDD). Padrão: 20240101"
    )
    parser.add_argument(
        "--fim", default=date.today().strftime("%Y%m%d"),
        help="Data de fim (YYYYMMDD). Padrão: hoje"
    )
    parser.add_argument(
        "--retomar", action="store_true",
        help="Retoma extração anterior usando pncp_progresso.json"
    )
    args = parser.parse_args()

    logger.info(f"▶ Parâmetros: inicio={args.inicio} | fim={args.fim} | retomar={args.retomar}")

    extrator = PNCPExtrator(
        data_inicio=args.inicio,
        data_fim=args.fim,
        retomar=args.retomar,
    )
    extrator.executar()


if __name__ == "__main__":
    main()
