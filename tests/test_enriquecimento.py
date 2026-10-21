import csv

from enriquecimento import enriquecer, extrair_marca, extrair_modelo


def test_marca_so_como_palavra_inteira():
    assert extrair_marca("Notebook Dell Inspiron 15") == "Dell"
    assert extrair_marca("Impressora hp laserjet") == "HP"
    assert extrair_marca("Chapa de aço galvanizado") == ""
    assert extrair_marca("Desenvolvimento em PHP") == ""


def test_modelo_precisa_de_letras_e_numeros():
    assert extrair_modelo("Impressora HP M404dn monocromática") == "M404DN"
    assert extrair_modelo("Monitor LG 24MK430H-B") == "24MK430H-B"
    assert extrair_modelo("Papel A4 500 folhas 2026") == ""
    assert extrair_modelo("Pendrive 32GB") == ""


def test_enriquecer_csv_com_bom(tmp_path):
    entrada, saida = tmp_path / "e.csv", tmp_path / "s.csv"
    with open(entrada, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["item_numero", "item_descricao"])
        w.writerow(["1", "Notebook Lenovo ThinkPad E14"])
    assert enriquecer(str(entrada), str(saida)) == 1
    with open(saida, encoding="utf-8-sig", newline="") as f:
        linha = next(csv.DictReader(f, delimiter=";"))
    assert linha["item_numero"] == "1"
    assert linha["item_marca_provavel"] == "Lenovo"
    assert linha["item_modelo_provavel"] == "E14"
