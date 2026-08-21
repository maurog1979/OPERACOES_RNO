from pathlib import Path

base = Path(
    r"areas\adm\desconexao\templates"
)

print("\nARQUIVOS HTML ENCONTRADOS:\n")

for arq in sorted(base.glob("*.html")):

    print(arq.name)

    try:

        txt = arq.read_text(
            encoding="utf-8"
        )

        print(
            "  g_safra:",
            "g_safra" in txt
        )

        print(
            "  executive_v10:",
            "executive_v10" in txt
        )

        print(
            "  executive_cards_v10:",
            "executive_cards_v10" in txt
        )

    except Exception as e:

        print("ERRO:", e)

    print()