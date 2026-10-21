import csv
import json

import pytest

from pncp_client import FalhaAPI
from pncp_extrator import PNCPExtrator, gerar_janelas, main


def compra(seq):
    return {"numeroControlePNCP": f"X-1-{seq:06d}/2026", "anoCompra": 2026, "sequencialCompra": seq,
            "orgaoEntidade": {"cnpj": "00000000000191", "razaoSocial": "ÓRGÃO"}}


class ClienteFalso:
    """Por modalidade: lista de páginas; cada compra tem 1 item com resultado, salvo indicação."""

    def __init__(self, paginas, sem_resultado=(), falha_em=None):
        self.paginas = paginas
        self.sem_resultado = set(sem_resultado)
        self.falha_em = falha_em          # (modalidade, pagina) que levanta FalhaAPI
        self.chamadas_resultado = 0

    def listar_contratacoes_publicacao(self, d_ini, d_fim, modalidade, pagina=1, tamanho=50):
        if (modalidade, pagina) == self.falha_em:
            raise FalhaAPI("HTTP 503 após 5 tentativas")
        paginas = self.paginas.get(modalidade, [])
        dados = paginas[pagina - 1] if pagina <= len(paginas) else []
        return {"data": dados, "totalRegistros": sum(map(len, paginas)), "totalPaginas": len(paginas)}

    def listar_itens_compra(self, cnpj, ano, seq):
        return [{"numeroItem": 1, "descricao": f"item da compra {seq}", "temResultado": seq not in self.sem_resultado}]

    def listar_resultados_item(self, cnpj, ano, seq, num):
        self.chamadas_resultado += 1
        return [{"niFornecedor": f"F{seq}", "nomeRazaoSocialFornecedor": "FORNECEDOR", "valorTotalHomologado": 10.0}]


def ler(caminho):
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def extrator(tmp_path, cliente, modalidades=(6, 8), retomar=False):
    return PNCPExtrator("20260101", "20260107", list(modalidades), pasta=tmp_path, retomar=retomar, client=cliente)


def test_janelas_cobrem_o_periodo_sem_buracos():
    assert gerar_janelas("20260101", "20260115", 7) == [
        ("20260101", "20260107"), ("20260108", "20260114"), ("20260115", "20260115")]
    with pytest.raises(ValueError):
        gerar_janelas("20260110", "20260101")


def test_percorre_todas_as_modalidades_e_paginas(tmp_path):
    cliente = ClienteFalso({6: [[compra(1), compra(2)], [compra(3)]], 8: [[compra(4)]]})
    ex = extrator(tmp_path, cliente)
    assert ex.executar() == 0
    linhas = ler(ex.csv_resultados)
    assert [l["fornecedor_cnpjCpf"] for l in linhas] == ["F1", "F2", "F3", "F4"]
    assert ex.progresso["totais"]["resultados"] == 4
    assert not list(tmp_path.glob("parcial_*"))


def test_item_sem_resultado_nao_gasta_chamada_e_vai_para_o_outro_csv(tmp_path):
    cliente = ClienteFalso({6: [[compra(1), compra(2)]]}, sem_resultado={2})
    ex = extrator(tmp_path, cliente, modalidades=[6])
    ex.executar()
    assert cliente.chamadas_resultado == 1
    sem = ler(ex.csv_sem_resultado)
    assert [(s["sequencialCompra"], s["motivo_sem_resultado"]) for s in sem] == [("2", "itens_sem_resultado")]


def test_falha_da_api_nao_grava_a_unidade_pela_metade_e_retomar_completa_sem_duplicar(tmp_path):
    paginas = {6: [[compra(1)]], 8: [[compra(2)], [compra(3)]]}
    ex = extrator(tmp_path, ClienteFalso(paginas, falha_em=(8, 2)))
    assert ex.executar() == 1                                    # a página 2 da modalidade 8 falhou
    assert [l["fornecedor_cnpjCpf"] for l in ler(ex.csv_resultados)] == ["F1"]   # nada da modalidade 8
    prog = json.loads((tmp_path / "pncp_progresso.json").read_text(encoding="utf-8"))
    assert prog["unidades_concluidas"] == ["20260101_20260107_m6"]

    ex2 = PNCPExtrator("20990101", "20990101", [1], pasta=tmp_path, retomar=True, client=ClienteFalso(paginas))
    assert (ex2.data_inicio, ex2.modalidades) == ("20260101", [6, 8])   # retomar ignora parâmetros novos
    assert ex2.executar() == 0
    assert [l["fornecedor_cnpjCpf"] for l in ler(ex2.csv_resultados)] == ["F1", "F2", "F3"]
    assert ex2.progresso["totais"]["resultados"] == 3


def test_ctrl_c_descarta_a_unidade_em_andamento(tmp_path):
    class Interrompe(ClienteFalso):
        def listar_resultados_item(self, *a):
            raise KeyboardInterrupt

    ex = extrator(tmp_path, Interrompe({6: [[compra(1)]]}), modalidades=[6])
    assert ex.executar() == 130
    assert not ex.csv_resultados.exists() and not list(tmp_path.glob("parcial_*"))


def test_linha_de_comando_valida_modalidades(tmp_path):
    with pytest.raises(SystemExit):
        main(["--modalidades", "99", "--saida", str(tmp_path)])
