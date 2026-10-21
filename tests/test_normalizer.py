import json
from pathlib import Path

from pncp_normalizer import (COLUNAS_CSV, montar_linha, normalizar_contratacao, normalizar_item,
                             normalizar_resultado)

FIX = Path(__file__).parent / "fixtures"


def carregar(nome):
    return json.loads((FIX / nome).read_text(encoding="utf-8"))


def test_resultado_real_traz_fornecedor_e_valores():
    r = normalizar_resultado(carregar("resultados.json")[0])
    assert r["fornecedor_cnpjCpf"] == "49552222000106"
    assert r["fornecedor_nome"] == "COMERCIAL AGRO VOGEL E ZIMMERMANN LTDA"
    assert r["fornecedor_tipoPessoa"] == "PJ"
    assert r["fornecedor_porteNome"] == "ME"
    assert r["resultado_valorUnitarioHomologado"] == 9600.0
    assert r["resultado_situacaoCodigo"] == 1


def test_item_real_usa_os_nomes_de_campo_da_api():
    i = normalizar_item(carregar("itens.json")[0])
    assert i["item_numero"] == 1
    assert i["item_descricao"]
    assert i["item_situacaoCodigo"] == 2
    assert i["item_criterioJulgamentoCodigo"] == 1
    assert i["item_valorTotalEstimado"] == 12740.0


def test_contratacao_real():
    c = normalizar_contratacao(carregar("compra.json"))
    assert c["numeroControlePNCP"] == "91984492000152-1-000082/2026"
    assert c["orgao_cnpj"] == "91984492000152"
    assert c["unidade_uf"] == "RS"
    assert c["modalidadeId"] == 6


def test_nenhum_campo_essencial_fica_vazio_com_dados_reais():
    linha = montar_linha(normalizar_contratacao(carregar("compra.json")),
                         normalizar_item(carregar("itens.json")[0]),
                         normalizar_resultado(carregar("resultados.json")[0]))
    essenciais = ["numeroControlePNCP", "orgao_cnpj", "item_numero", "item_descricao",
                  "fornecedor_cnpjCpf", "fornecedor_nome", "resultado_valorTotalHomologado"]
    assert all(linha[c] not in ("", None) for c in essenciais)


def test_colunas_sem_repeticao_e_iguais_as_chaves_da_linha():
    assert len(COLUNAS_CSV) == len(set(COLUNAS_CSV))
    linha = montar_linha(normalizar_contratacao({}), normalizar_item({}), normalizar_resultado({}))
    assert list(linha) == COLUNAS_CSV


def test_objeto_vazio_nao_quebra():
    assert normalizar_resultado({})["fornecedor_nome"] == ""
    assert normalizar_item({"quantidade": "abc"})["item_quantidade"] is None
