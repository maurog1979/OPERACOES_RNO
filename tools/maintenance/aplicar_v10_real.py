from pathlib import Path

ARQ = Path(
    r"areas\adm\desconexao\templates\dash_safra.html"
)

txt = ARQ.read_text(
    encoding="utf-8"
)

print("=" * 70)

print("Arquivo:")
print(ARQ)

print("=" * 70)

print()

alvos = [

    'id="g_meta"',
    'id="g_rank"',
    'id="g_safra"',
    'id="g_tipo"',
    'renderMatrix(',
    'function plotAll'
]

for alvo in alvos:

    print(
        f"{alvo}:",
        alvo in txt
    )

print()

print("Tamanho do arquivo:")
print(len(txt))