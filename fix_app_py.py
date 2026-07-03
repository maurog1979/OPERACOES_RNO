# -*- coding: utf-8 -*-
"""
fix_app_py.py
Corrige o app.py inserindo dash_log_bp com a indentacao correta
dentro do try/except existente em create_app().
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app.py"

print("=" * 72)
print("  FIX app.py - dash_log_bp com indentacao correta")
print("=" * 72)

if not APP.exists():
    print("[ERRO] app.py nao encontrado")
    input("\nENTER para sair...")
    raise SystemExit(1)

# Backup
bak = APP.with_suffix(".py.backup_fix2")
shutil.copy2(APP, bak)
print(f"[BAK] {bak.name}")

content = APP.read_text(encoding="utf-8")

# Bloco antigo (atual no arquivo restaurado)
bloco_antigo = '''    # Registrar Blueprints do setor Desconexão (ADM)
    try:
        from areas.adm.desconexao import dash_executivo_bp
        app.register_blueprint(dash_executivo_bp)
        print("[APP] Blueprint dash_executivo registrado em /dash/executivo/")
    except Exception as e:
        print(f"[APP] AVISO: não foi possível registrar dash_executivo_bp: {e}")'''

# Bloco novo (com dash_log_bp adicionado)
bloco_novo = '''    # Registrar Blueprints do setor Desconexão (ADM)
    try:
        from areas.adm.desconexao import dash_executivo_bp
        app.register_blueprint(dash_executivo_bp)
        print("[APP] Blueprint dash_executivo registrado em /dash/executivo/")
    except Exception as e:
        print(f"[APP] AVISO: não foi possível registrar dash_executivo_bp: {e}")

    try:
        from areas.adm.desconexao import dash_log_bp
        app.register_blueprint(dash_log_bp)
        print("[APP] Blueprint dash_log registrado em /dash/log/")
    except Exception as e:
        print(f"[APP] AVISO: não foi possível registrar dash_log_bp: {e}")'''

if bloco_antigo in content:
    if "dash_log_bp" in content:
        print("[INFO] dash_log_bp ja registrado. Nada a fazer.")
    else:
        novo = content.replace(bloco_antigo, bloco_novo, 1)
        APP.write_text(novo, encoding="utf-8")
        print("[OK]  app.py atualizado com bloco try/except para dash_log_bp")
        print("[OK]  Indentacao correta (8 espacos dentro de create_app)")
else:
    print("[ERRO] Nao encontrei o bloco antigo exato. app.py pode ter mudado.")
    print("       Verifique manualmente.")
    input("\nENTER para sair...")
    raise SystemExit(1)

# Validacao de sintaxe
print()
print("-" * 72)
print("  VALIDANDO SINTAXE PYTHON...")
print("-" * 72)
import py_compile
try:
    py_compile.compile(str(APP), doraise=True)
    print("[OK]  app.py sintaxe valida!")
except py_compile.PyCompileError as e:
    print(f"[ERRO] Sintaxe invalida:\n{e}")
    input("\nENTER para sair...")
    raise SystemExit(1)

print()
print("=" * 72)
print("  PRONTO! Agora rode:  python run.py")
print("=" * 72)
input("\nENTER para encerrar...")