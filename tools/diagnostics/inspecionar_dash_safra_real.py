from pathlib import Path

ARQ = Path(
    Path(__file__).resolve().parents[2] / "areas/adm/desconexao/templates/dash_safra_v9_visual.html"
)

txt = ARQ.read_text(
    encoding="utf-8",
    errors="ignore"
)

ini = txt.find("function plotAll")

fim = txt.find("function td")

print(txt[ini:fim])
