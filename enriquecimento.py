import sys
import csv
import re

def extrair_modelo(descricao):
    if not descricao:
        return ""

    d = descricao

    # 🔥 padrões comuns de modelo
    patterns = [
        r'\b[A-Z]{2,}-?\d{2,}[A-Z0-9\-]*\b',   # Ex: M404dn, 24MK430H-B
        r'\b\d{3,}[A-Z\-]*\b',                # Ex: 3520, 840G5
        r'\b[A-Z]+\s?\d{2,}\b',               # Ex: G15, XPS 13
    ]

    for p in patterns:
        match = re.search(p, d.upper())
        if match:
            return match.group(0)

    return ""


def main():
    if len(sys.argv) < 3:
        print("Uso: python enriquecimento.py input.csv output.csv")
        return

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    print(f"📂 Lendo: {input_file}")

    with open(input_file, encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in, delimiter=";")
        rows = list(reader)

    print(f"🔢 Linhas carregadas: {len(rows)}")

    for i, row in enumerate(rows, 1):
        desc = row.get("item_descricao", "")

        modelo = extrair_modelo(desc)

        if not row.get("item_modelo"):
            row["item_modelo"] = modelo

        if i % 1000 == 0:
            print(f"Processadas: {i}")

    with open(output_file, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=rows[0].keys(), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ Arquivo gerado: {output_file}")


if __name__ == "__main__":
    main()
