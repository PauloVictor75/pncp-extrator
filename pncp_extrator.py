#!/usr/bin/env python3
"""
🎯 PNCP EXTRATOR PRINCIPAL
===========================
Extrai do Portal Nacional de Contratações Públicas (pncp.gov.br) os resultados
(fornecedor vencedor e valores homologados) de cada item das contratações
publicadas num período, de todos os órgãos do Brasil.

O trabalho é dividido em unidades (janela de dias × modalidade). Cada unidade é
gravada inteira ou não é gravada: as linhas vão para arquivos parciais e só entram
nos CSVs finais quando a unidade termina. Assim, uma interrupção ou uma falha da
API nunca deixa linhas pela metade nem duplicadas — o --retomar refaz só o que faltou.

Saída (pasta saida_pncp/):
  → pncp_resultados_YYYYMMDD_HHmmss.csv    (linha por resultado de item)
  → pncp_sem_resultado_YYYYMMDD_HHmmss.csv (contratações sem resultado)
  → pncp_progresso.json                    (ponto de retomada)
  → pncp_extrator.log                      (log completo)

Uso:
  python pncp_extrator.py                                  # últimos 7 dias, todas as modalidades
  python pncp_extrator.py --inicio 20250701 --fim 20251231
  python pncp_extrator.py --modalidades 6,8                # só pregão eletrônico e dispensa
  python pncp_extrator.py --retomar
"""

import argparse
import csv
import json
import logging
import sys
import shutil
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from pncp_client import MODALIDADES, FalhaAPI, PNCPClient
from pncp_normalizer import (
    COLUNAS_CSV,
    COLUNAS_SEM_RESULTADO,
    montar_linha,
    normalizar_contratacao,
    normalizar_item,
    normalizar_resultado,
)

# ─────────────────────────────────────────────────────────────────────────────
# Configurações padrão
# ─────────────────────────────────────────────────────────────────────────────

TAMANHO_PAGINA  = 50     # máximo aceito pela API
INTERVALO_DIAS  = 7      # tamanho de cada janela de busca
DELAY_ENTRE_REQ = 0.4    # segundos entre chamadas (respeito à API)
DIR_SAIDA       = Path("saida_pncp")

logger = logging.getLogger(__name__)


def configurar_log(pasta: Path):
    pasta.mkdir(parents=True, exist_ok=True)
    if hasattr(sys.stdout, "reconfigure"):   # terminal do Windows (cp1252) não mostra os emojis do log
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(pasta / "pncp_extrator.log", encoding="utf-8"),
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Janelas de datas
# ─────────────────────────────────────────────────────────────────────────────

def gerar_janelas(data_inicio: str, data_fim: str, intervalo_dias: int = INTERVALO_DIAS):
    d_ini = datetime.strptime(data_inicio, "%Y%m%d").date()
    d_fim = datetime.strptime(data_fim, "%Y%m%d").date()
    if d_ini > d_fim:
        raise ValueError(f"Início {data_inicio} depois do fim {data_fim}.")

    janelas = []
    cursor = d_ini
    while cursor <= d_fim:
        fim_janela = min(cursor + timedelta(days=intervalo_dias - 1), d_fim)
        janelas.append((cursor.strftime("%Y%m%d"), fim_janela.strftime("%Y%m%d")))
        cursor = fim_janela + timedelta(days=1)
    return janelas


def chave_unidade(d_ini: str, d_fim: str, modalidade: int) -> str:
    return f"{d_ini}_{d_fim}_m{modalidade}"


# ─────────────────────────────────────────────────────────────────────────────
# Escrita CSV
# ─────────────────────────────────────────────────────────────────────────────

class ParcialCSV:
    """CSV sem cabeçalho de uma unidade em andamento; só vai para o final se a unidade terminar."""

    def __init__(self, caminho: Path, colunas: list):
        self.caminho = caminho
        self.colunas = colunas
        self.linhas = 0
        self._fh = open(caminho, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._fh, fieldnames=colunas, extrasaction="ignore", delimiter=";")

    def escrever(self, linha: dict):
        self._writer.writerow(linha)
        self.linhas += 1

    def acrescentar_em(self, destino: Path):
        """Copia as linhas para o CSV final (cabeçalho e BOM só quando ele é novo)."""
        self._fh.close()
        if self.linhas:
            novo = not destino.exists()
            with open(destino, "a", newline="", encoding="utf-8-sig" if novo else "utf-8") as saida:
                if novo:
                    csv.writer(saida, delimiter=";").writerow(self.colunas)
                with open(self.caminho, encoding="utf-8", newline="") as origem:
                    shutil.copyfileobj(origem, saida)
        self.caminho.unlink()

    def descartar(self):
        self._fh.close()
        self.caminho.unlink(missing_ok=True)


class Unidade:
    """Uma janela × modalidade: as linhas ficam em arquivos parciais até ela terminar."""

    def __init__(self, pasta: Path):
        self.resultados = ParcialCSV(pasta / "parcial_resultados.csv", COLUNAS_CSV)
        self.sem_resultado = ParcialCSV(pasta / "parcial_sem_resultado.csv", COLUNAS_SEM_RESULTADO)
        self.contratacoes = 0
        self.itens = 0

    def descartar(self):
        self.resultados.descartar()
        self.sem_resultado.descartar()


# ─────────────────────────────────────────────────────────────────────────────
# Núcleo do extrator
# ─────────────────────────────────────────────────────────────────────────────

class PNCPExtrator:

    def __init__(self, data_inicio: str, data_fim: str, modalidades: list,
                 pasta: Path = DIR_SAIDA, retomar: bool = False, client=None):
        self.pasta = pasta
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.arquivo_progresso = pasta / "pncp_progresso.json"
        self.client = client or PNCPClient(delay_entre_req=DELAY_ENTRE_REQ)

        self.progresso = self._carregar_progresso() if retomar else {}
        if self.progresso:
            # retomar continua exatamente a extração anterior
            data_inicio = self.progresso["inicio"]
            data_fim = self.progresso["fim"]
            modalidades = self.progresso["modalidades"]
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.progresso = {
                "inicio": data_inicio,
                "fim": data_fim,
                "modalidades": modalidades,
                "arquivo_resultados": f"pncp_resultados_{ts}.csv",
                "arquivo_sem_resultado": f"pncp_sem_resultado_{ts}.csv",
                "unidades_concluidas": [],
                "totais": {"contratacoes": 0, "itens": 0, "resultados": 0, "sem_resultado": 0},
            }
        self.data_inicio = data_inicio
        self.data_fim = data_fim
        self.modalidades = modalidades
        self.csv_resultados = pasta / self.progresso["arquivo_resultados"]
        self.csv_sem_resultado = pasta / self.progresso["arquivo_sem_resultado"]
        self.falhas = []

    # ── Progresso ────────────────────────────────────────────────────────────

    def _carregar_progresso(self) -> dict:
        if not self.arquivo_progresso.exists():
            logger.warning("Nada para retomar: começando do zero.")
            return {}
        prog = json.loads(self.arquivo_progresso.read_text(encoding="utf-8"))
        logger.info(f"📂 Retomando: {prog['inicio']} → {prog['fim']}, "
                    f"{len(prog['unidades_concluidas'])} unidades já concluídas")
        return prog

    def _salvar_progresso(self):
        self.progresso["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
        temporario = self.arquivo_progresso.with_suffix(".tmp")
        temporario.write_text(json.dumps(self.progresso, ensure_ascii=False, indent=2), encoding="utf-8")
        temporario.replace(self.arquivo_progresso)

    # ── Uma contratação ──────────────────────────────────────────────────────

    def processar_contratacao(self, contratacao: dict, unidade: Unidade):
        """Itens + resultados de uma contratação. FalhaAPI sobe e derruba a unidade."""
        cnpj = (contratacao.get("orgaoEntidade") or {}).get("cnpj", "")
        ano = contratacao.get("anoCompra")
        seq = contratacao.get("sequencialCompra")
        unidade.contratacoes += 1
        c_flat = normalizar_contratacao(contratacao)

        if not cnpj or not ano or not seq:
            unidade.sem_resultado.escrever({**c_flat, "motivo_sem_resultado": "sem_identificacao"})
            return

        itens = self.client.listar_itens_compra(cnpj, ano, seq)
        if not itens:
            unidade.sem_resultado.escrever({**c_flat, "motivo_sem_resultado": "sem_itens"})
            return

        teve_resultado = False
        for item in itens:
            num_item = item.get("numeroItem")
            if num_item is None:
                continue
            unidade.itens += 1
            # a API avisa se o item tem resultado: evita uma chamada por item sem vencedor
            if item.get("temResultado") is False:
                continue
            i_flat = normalizar_item(item)
            for resultado in self.client.listar_resultados_item(cnpj, ano, seq, num_item):
                unidade.resultados.escrever(montar_linha(c_flat, i_flat, normalizar_resultado(resultado)))
                teve_resultado = True

        if not teve_resultado:
            unidade.sem_resultado.escrever({**c_flat, "motivo_sem_resultado": "itens_sem_resultado"})

    # ── Uma unidade (janela × modalidade) ────────────────────────────────────

    def processar_unidade(self, d_ini: str, d_fim: str, modalidade: int) -> Unidade:
        unidade = Unidade(self.pasta)
        try:
            self._ler_paginas(d_ini, d_fim, modalidade, unidade)
        except BaseException:
            unidade.descartar()   # falha da API ou Ctrl+C: nada desta unidade entra nos CSVs
            raise
        return unidade

    def _ler_paginas(self, d_ini: str, d_fim: str, modalidade: int, unidade: Unidade):
        pagina, total_paginas = 1, 1
        while pagina <= total_paginas:
            resp = self.client.listar_contratacoes_publicacao(
                d_ini, d_fim, modalidade, pagina=pagina, tamanho=TAMANHO_PAGINA
            )
            total_paginas = resp.get("totalPaginas") or 0
            if pagina == 1 and total_paginas:
                logger.info(f"   {MODALIDADES.get(modalidade, modalidade)}: "
                            f"{resp.get('totalRegistros', 0)} contratações ({total_paginas} páginas)")
            for contratacao in resp.get("data") or []:
                self.processar_contratacao(contratacao, unidade)
            pagina += 1

    def _gravar_unidade(self, chave: str, unidade: Unidade):
        """Só aqui as linhas entram nos CSVs finais — e logo depois a unidade vira concluída."""
        n_resultados, n_sem = unidade.resultados.linhas, unidade.sem_resultado.linhas
        unidade.resultados.acrescentar_em(self.csv_resultados)
        unidade.sem_resultado.acrescentar_em(self.csv_sem_resultado)
        totais = self.progresso["totais"]
        totais["contratacoes"] += unidade.contratacoes
        totais["itens"] += unidade.itens
        totais["resultados"] += n_resultados
        totais["sem_resultado"] += n_sem
        self.progresso["unidades_concluidas"].append(chave)
        self._salvar_progresso()

    # ── Execução principal ───────────────────────────────────────────────────

    def executar(self) -> int:
        """0 = tudo extraído; 1 = alguma unidade falhou (rode de novo com --retomar)."""
        inicio = time.time()
        janelas = gerar_janelas(self.data_inicio, self.data_fim)
        unidades = [(d_ini, d_fim, m) for d_ini, d_fim in janelas for m in self.modalidades]
        concluidas = set(self.progresso["unidades_concluidas"])

        logger.info("=" * 65)
        logger.info("🚀 PNCP EXTRATOR")
        logger.info(f"   Período:     {self.data_inicio} → {self.data_fim}")
        logger.info(f"   Modalidades: {', '.join(str(m) for m in self.modalidades)}")
        logger.info(f"   Unidades:    {len(unidades)} ({len(janelas)} janelas × {len(self.modalidades)} modalidades)")
        logger.info(f"   Saída:       {self.pasta.resolve()}")
        logger.info("=" * 65)
        self._salvar_progresso()

        for idx, (d_ini, d_fim, modalidade) in enumerate(unidades, 1):
            chave = chave_unidade(d_ini, d_fim, modalidade)
            if chave in concluidas:
                continue
            logger.info(f"🔄 [{idx}/{len(unidades)}] {d_ini} → {d_fim}, modalidade {modalidade}")
            try:
                unidade = self.processar_unidade(d_ini, d_fim, modalidade)
            except KeyboardInterrupt:
                logger.warning("⏹ Interrompido. O que já foi gravado fica; continue com --retomar.")
                return 130
            except FalhaAPI as erro:
                logger.error(f"   ❌ Unidade não gravada ({erro}). Rode de novo com --retomar.")
                self.falhas.append(chave)
                continue
            self._gravar_unidade(chave, unidade)

        self._imprimir_resumo(time.time() - inicio)
        return 1 if self.falhas else 0

    def _imprimir_resumo(self, segundos: float):
        t = self.progresso["totais"]
        logger.info("=" * 65)
        logger.info("🏁 EXTRAÇÃO " + ("INCOMPLETA" if self.falhas else "CONCLUÍDA"))
        logger.info(f"   Contratações lidas:   {t['contratacoes']:,}")
        logger.info(f"   Itens:                {t['itens']:,}")
        logger.info(f"   Resultados gravados:  {t['resultados']:,}")
        logger.info(f"   Sem resultado:        {t['sem_resultado']:,}")
        logger.info(f"   Tempo desta execução: {segundos / 60:.1f} min")
        if self.falhas:
            logger.info(f"   Unidades com falha:   {len(self.falhas)} → python pncp_extrator.py --retomar")
        logger.info("=" * 65)


# ─────────────────────────────────────────────────────────────────────────────
# Ponto de entrada
# ─────────────────────────────────────────────────────────────────────────────

def _data(valor: str) -> str:
    datetime.strptime(valor, "%Y%m%d")  # valida
    return valor


def _modalidades(valor: str) -> list:
    codigos = sorted({int(v) for v in valor.split(",") if v.strip()})
    invalidos = [c for c in codigos if c not in MODALIDADES]
    if invalidos or not codigos:
        raise argparse.ArgumentTypeError(f"modalidades válidas: {', '.join(map(str, MODALIDADES))}")
    return codigos


def main(argv=None) -> int:
    ontem = date.today() - timedelta(days=1)
    parser = argparse.ArgumentParser(description="Extrai os resultados das contratações do PNCP.")
    parser.add_argument("--inicio", type=_data, default=(ontem - timedelta(days=6)).strftime("%Y%m%d"),
                        help="data de início AAAAMMDD (padrão: 7 dias atrás)")
    parser.add_argument("--fim", type=_data, default=ontem.strftime("%Y%m%d"),
                        help="data de fim AAAAMMDD (padrão: ontem)")
    parser.add_argument("--modalidades", type=_modalidades, default=list(MODALIDADES),
                        help="códigos separados por vírgula (padrão: todas). "
                             + "; ".join(f"{c}={n}" for c, n in MODALIDADES.items()))
    parser.add_argument("--saida", type=Path, default=DIR_SAIDA, help="pasta de saída (padrão: saida_pncp)")
    parser.add_argument("--retomar", action="store_true",
                        help="continua a extração anterior (mesmo período, modalidades e arquivos)")
    args = parser.parse_args(argv)

    configurar_log(args.saida)
    extrator = PNCPExtrator(args.inicio, args.fim, args.modalidades, pasta=args.saida, retomar=args.retomar)
    return extrator.executar()


if __name__ == "__main__":
    sys.exit(main())
