from pathlib import Path

ARQ = Path(
    Path(__file__).resolve().parents[2] / "areas/adm/desconexao/templates/dash_safra_v9_visual.html"
)

txt = ARQ.read_text(
    encoding="utf-8",
    errors="ignore"
)

print("\n" + "="*60)

print("g_safra Plotly:")
print("Plotly.newPlot('g_safra'" in txt)

print()

print("g_tipo Plotly:")
print("Plotly.newPlot('g_tipo'" in txt)

print()

print("renderExecutiveCards:")
print("renderExecutiveCards" in txt)

print()

print("="*60)
