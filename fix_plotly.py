# -*- coding: utf-8 -*-
"""Conserta a tag do Plotly no dash_executivo.html sem depender de chat."""
import os

# Usa chr(60) e chr(62) pra evitar qualquer sanitizacao
LT = chr(60)   # <
GT = chr(62)   # >

PATH = os.path.join("areas", "adm", "desconexao", "templates", "dash_executivo.html")

# Linha errada que esta no arquivo
BROKEN = LT + ' + script src="https://cdn.plot.ly/plotly-2.27.0.min.js" + ' + GT + ' + ' + LT + ' + /script + ' + GT

# Linha correta (montada via chr() para nunca ser sanitizada)
FIX = LT + 'script src="https://cdn.plot.ly/plotly-2.27.0.min.js"' + GT + LT + '/script' + GT

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

if BROKEN in content:
    content = content.replace(BROKEN, FIX)
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print("OK! Linha do Plotly corrigida.")
    print(f"Tag inserida: {FIX}")
else:
    print("AVISO: linha quebrada nao encontrada exatamente.")
    print("Procurando pela URL do Plotly no arquivo...")
    if "plotly-2.27.0.min.js" in content:
        # Estrategia alternativa: encontra a linha contendo a URL e substitui ela inteira
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "plotly-2.27.0.min.js" in line and "script src=" not in line:
                print(f"Linha {i+1} ANTES: {line}")
                lines[i] = FIX
                print(f"Linha {i+1} DEPOIS: {FIX}")
                break
        content = "\n".join(lines)
        with open(PATH, "w", encoding="utf-8") as f:
            f.write(content)
        print("OK! Substituicao alternativa aplicada.")
    else:
        print("ERRO: URL do Plotly nao encontrada. Arquivo pode estar diferente.")

input("\nPressione ENTER para fechar...")