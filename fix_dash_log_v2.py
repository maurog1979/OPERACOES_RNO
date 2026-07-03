# -*- coding: utf-8 -*-
"""
fix_dash_log_kpis.py
Corrige o mapeamento das FAIXAS no dash_log.py:
- SEM LOG (era "0 - SEM LOG")
- 1x, 2-3x, 4-5x, 6x+ (eram "1 - UM LOG", "2 - DOIS LOGS", etc.)
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DASH = ROOT / "areas/area/area/adm/desconexao//dash_log.py"

print("=" * 72)
print("  FIX KPIs dash_log - faixas reais do banco")
print("=" * 72)

if not DASH.exists():
    print("[ERRO] dash_log.py nao encontrado")
    input("\nENTER para sair...")
    raise SystemExit(1)

bak = DASH.with_suffix(".py.backup_kpi")
shutil.copy2(DASH, bak)
print(f"[BAK] {bak.name}")

content = DASH.read_text(encoding="utf-8")

# --------------------------------------------------------------
# 1. CORES_LOG -> mapear pelas chaves reais
# --------------------------------------------------------------
old_cores = '''CORES_LOG = {
    "0 - SEM LOG":      "#9E9E9E",
    "1 - UM LOG":       "#1565C0",
    "2 - DOIS LOGS":    "#F9A825",
    "3 - TRES A CINCO": "#F57C00",
    "4 - SEIS OU MAIS": "#E60000",
}'''

new_cores = '''CORES_LOG = {
    "SEM LOG": "#9E9E9E",
    "1x":      "#1565C0",
    "2-3x":    "#F9A825",
    "4-5x":    "#F57C00",
    "6x+":     "#E60000",
}

# Mapeamento de classificacao das faixas
FAIXA_SEM_LOG = "SEM LOG"
FAIXA_CRITICA = "6x+"'''

if old_cores in content:
    content = content.replace(old_cores, new_cores)
    print("[OK]  CORES_LOG atualizado para valores reais")
else:
    print("[INFO] CORES_LOG ja parece atualizado ou diferente do esperado")

# --------------------------------------------------------------
# 2. KPIs - trocar "0 - SEM LOG" por FAIXA_SEM_LOG
# --------------------------------------------------------------
old_kpi = '''    com_log = int((faixa_str != "0 - SEM LOG").sum())
    sem_log = int((faixa_str == "0 - SEM LOG").sum())
    criticos = int((faixa_str == "4 - SEIS OU MAIS").sum())'''

new_kpi = '''    com_log = int((faixa_str != FAIXA_SEM_LOG).sum())
    sem_log = int((faixa_str == FAIXA_SEM_LOG).sum())
    criticos = int((faixa_str == FAIXA_CRITICA).sum())'''

if old_kpi in content:
    content = content.replace(old_kpi, new_kpi)
    print("[OK]  KPIs com_log/sem_log/criticos corrigidos")
else:
    print("[AVISO] Bloco de KPIs nao encontrado exatamente")

# --------------------------------------------------------------
# 3. G4 - trocar "4 - SEIS OU MAIS" por FAIXA_CRITICA
# --------------------------------------------------------------
old_g4 = '''    df_crit = df[faixa_str == "4 - SEIS OU MAIS"]'''
new_g4 = '''    df_crit = df[faixa_str == FAIXA_CRITICA]'''

if old_g4 in content:
    content = content.replace(old_g4, new_g4)
    print("[OK]  G4 (df_crit) corrigido para usar FAIXA_CRITICA")
else:
    print("[AVISO] Bloco df_crit nao encontrado exatamente")

# Salva
DASH.write_text(content, encoding="utf-8")
print()

# Validacao de sintaxe
import py_compile
try:
    py_compile.compile(str(DASH), doraise=True)
    print("[OK]  dash_log.py sintaxe valida!")
except py_compile.PyCompileError as e:
    print(f"[ERRO] Sintaxe invalida:\n{e}")
    input("\nENTER para sair...")
    raise SystemExit(1)

print()
print("=" * 72)
print("  PRONTO! REINICIE O FLASK:")
print("    1. Ctrl+C no terminal do run.py")
print("    2. python run.py")
print("    3. Ctrl+F5 em http://localhost:5000/dash/log/")
print("=" * 72)
print()
print("  RESULTADO ESPERADO (com base no donut atual):")
print("  - TOTAL:    62.875")
print("  - SEM LOG:  ~26.973  (42.9% de 62.875)")
print("  - COM LOG:  ~35.902  (57.1% de 62.875)")
print("  - CRITICOS: ~4.586   (7.29% de 62.875)")
print("  - % COM LOG: ~57.1%")
print("  - G4 deve mostrar barras agrupadas Cidade x SAFRA")
print()
input("ENTER para encerrar...")