#!/usr/bin/env python3
"""
🏷️ ENRIQUECIMENTO OPCIONAL — marca e modelo prováveis
=====================================================
A API do PNCP não informa marca nem modelo do item. Este passo, separado da extração,
tenta adivinhar pela descrição e grava em colunas próprias (item_marca_provavel,
item_modelo_provavel) — é palpite, não dado oficial, por isso não se mistura às
colunas da API.

Uso:
  python enriquecimento.py saida_pncp/pncp_resultados_X.csv saida_pncp/enriquecido.csv
"""

import csv
import re
import sys

# Marcas procuradas como palavra inteira ("hp" não casa com "chapa" nem "php").
MARCAS = ["Dell", "HP", "Lenovo", "Asus", "Acer", "Samsung", "LG", "Positivo", "Apple", "Epson", "Brother", "Canon"]

_MARCA = re.compile(r"\b(" + "|".join(re.escape(m) for m in MARCAS) + r")\b", re.IGNORECASE)
_POR_NOME = {m.lower(): m for m in MARCAS}

# Código de modelo: letras e números juntos, com pelo menos um de cada (M404dn, 24MK430H-B, 840G5).
# Número puro (quantidade, ano, voltagem) não conta.
_MODELO = re.compile(r"\b(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{2,}\b")
_NAO_MODELO = re.compile(r"^\d+(GB|TB|MB|GHZ|MHZ|W|V|KG|MM|CM|ML|L|M|POL)$")


def extrair_marca(descricao: str) -> str:
    achou = _MARCA.search(descricao or "")
    return _POR_NOME[achou.group(1).lower()] if achou else ""


def extrair_modelo(descricao: str) -> str:
    for candidato in _MODELO.findall((descricao or "").upper()):
        if not _NAO_MODELO.match(candidato):
            return candidato
    return ""


def enriquecer(entrada: str, saida: str) -> int:
    with open(entrada, encoding="utf-8-sig", newline="") as f_in:
        reader = csv.DictReader(f_in, delimiter=";")
        colunas = list(reader.fieldnames or []) + ["item_marca_provavel", "item_modelo_provavel"]
        with open(saida, "w", newline="", encoding="utf-8-sig") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=colunas, delimiter=";")
            writer.writeheader()
            total = 0
            for row in reader:
                desc = row.get("item_descricao", "")
                row["item_marca_provavel"] = extrair_marca(desc)
                row["item_modelo_provavel"] = extrair_modelo(desc)
                writer.writerow(row)
                total += 1
    return total


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("Uso: python enriquecimento.py entrada.csv saida.csv")
        return 2
    total = enriquecer(argv[0], argv[1])
    print(f"✅ {total} linhas → {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
