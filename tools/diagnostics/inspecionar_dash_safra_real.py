from pathlib import Path

ARQ = Path(
    r"areas\adm\desconexao\templates\dash_safra.html"
)

txt = ARQ.read_text(
    encoding="utf-8",
    errors="ignore"
)

ini = txt.find("function plotAll")

fim = txt.find("function td")

print(txt[ini:fim])