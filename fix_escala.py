# -*- coding: utf-8 -*-
"""Aplica fix de escala 0-100% nos graficos fig1 e fig3."""
import os

PATH = os.path.join("areas", "adm", "desconexao", "dash_executivo.py")

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

# ============================================================
# FIX 1: Forca SAFRA e TIPO como string ANTES do plot do fig1
# ============================================================
old1 = '''            grp["taxa"] = (grp["recup"] / grp["total"] * 100).round(1)
            grp["taxa"] = grp["taxa"].astype(float)
            grp["taxa_fmt"] = grp["taxa"].apply(lambda v: f"{v:.1f}%")'''

new1 = '''            grp["taxa"] = (grp["recup"] / grp["total"] * 100).round(1)
            grp["taxa"] = grp["taxa"].astype(float)
            grp["taxa_fmt"] = grp["taxa"].apply(lambda v: f"{v:.1f}%")
            # Forca tipos primitivos para evitar bug do Plotly com category dtype
            grp["SAFRA"] = grp["SAFRA"].astype(str)
            grp["DS_TIPO_DESCONEXAO"] = grp["DS_TIPO_DESCONEXAO"].astype(str)'''

if old1 in content:
    content = content.replace(old1, new1)
    print("OK fix 1: SAFRA/TIPO como string aplicado no fig1")
else:
    print("AVISO fix 1: trecho nao encontrado (pode ja estar aplicado)")

# ============================================================
# FIX 2: Range fixo 0-105 no eixo Y do fig1
# ============================================================
old2 = '''            fig1.update_layout(
                title="Taxa de Recuperacao por SAFRA e Tipo",
                yaxis_title="%",
                xaxis_title="",
                plot_bgcolor="white",
                margin=dict(t=50, b=40),
                legend=dict(orientation="h", y=-0.25, title=""),
            )'''

new2 = '''            fig1.update_layout(
                title="Taxa de Recuperacao por SAFRA e Tipo",
                yaxis=dict(title="%", range=[0, 105], ticksuffix="%"),
                xaxis_title="",
                plot_bgcolor="white",
                margin=dict(t=50, b=40),
                legend=dict(orientation="h", y=-0.25, title=""),
            )'''

if old2 in content:
    content = content.replace(old2, new2)
    print("OK fix 2: range 0-105 aplicado no fig1")
else:
    print("AVISO fix 2: trecho nao encontrado (pode ja estar aplicado)")

# ============================================================
# FIX 3: Range fixo 0-105 no eixo X do fig3 (cidades)
# ============================================================
old3 = '''            fig3.update_layout(
                title="Top 15 Cidades - Taxa de Recuperacao",
                plot_bgcolor="white",
                margin=dict(t=50, l=140),
            )'''

new3 = '''            fig3.update_layout(
                title="Top 15 Cidades - Taxa de Recuperacao",
                xaxis=dict(title="%", range=[0, 105], ticksuffix="%"),
                plot_bgcolor="white",
                margin=dict(t=50, l=140),
            )'''

if old3 in content:
    content = content.replace(old3, new3)
    print("OK fix 3: range 0-105 aplicado no fig3")
else:
    print("AVISO fix 3: trecho nao encontrado (pode ja estar aplicado)")

# ============================================================
# Salva
# ============================================================
with open(PATH, "w", encoding="utf-8") as f:
    f.write(content)

print()
print("Arquivo salvo:", PATH)
input("Pressione ENTER para fechar...")