# -*- coding: utf-8 -*-
# CORRIGIR ROTAS DO HUB + DIAGNOSTICAR DASH_LOG/RETIRADA
from pathlib import Path
from datetime import datetime
import shutil
import re

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"
ROUTES = ROOT / "routes"
APP_FILE = ROOT / "app.py"
DB_FILE = ROOT / "data" / "db.py"
COMPAT_FILE = ROUTES / "compat_redirects.py"
RELATORIO = ROOT / "relatorio_corrigir_rotas_hub_log_retirada.txt"
ROTA_CORRETA = "/area/adm/desconexao/"
ROTAS_ERRADAS = ["/areas/adm/desconexao/", "/areas/adm/desconexao", "/adm/desconexao/", "/adm/desconexao"]
EXTS_PATCH_LINKS = {".html", ".py", ".js", ".json"}
IGNORAR = [".bak", "backup", "__pycache__", ".git", "venv", "env", "node_modules"]


def agora():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_file(path):
    if path.exists():
        bkp = path.with_suffix(path.suffix + ".bak_rotas_" + agora())
        shutil.copy2(path, bkp)
        print(f"[BACKUP] {path.name} -> {bkp.name}")
        return bkp
    return None


def read_text_safe(path):
    try:
        return path.read_text(encoding="utf-8"), "utf-8"
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1"), "latin-1"


def write_text_safe(path, text, encoding="utf-8"):
    path.write_text(text, encoding=encoding)


def deve_ignorar(path):
    s = str(path).lower()
    if path.suffix.lower() not in EXTS_PATCH_LINKS:
        return True
    if path.name == Path(__file__).name:
        return True
    return any(item in s for item in IGNORAR)


def criar_compat_redirects():
    ROUTES.mkdir(parents=True, exist_ok=True)
    code_lines = [
        "# -*- coding: utf-8 -*-\n",
        "from flask import Blueprint, redirect\n\n",
        "compat_redirects_bp = Blueprint('compat_redirects', __name__)\n\n",
        "@compat_redirects_bp.route('/areas/adm/desconexao/')\n",
        "@compat_redirects_bp.route('/areas/adm/desconexao')\n",
        "@compat_redirects_bp.route('/adm/desconexao/')\n",
        "@compat_redirects_bp.route('/adm/desconexao')\n",
        "def redirect_desconexao_aliases():\n",
        "    return redirect('/area/adm/desconexao/', code=302)\n",
    ]
    code = "".join(code_lines)
    old = COMPAT_FILE.read_text(encoding="utf-8") if COMPAT_FILE.exists() else ""
    if old != code:
        backup_file(COMPAT_FILE)
        write_text_safe(COMPAT_FILE, code, "utf-8")
        print(f"[OK] Criado/atualizado: {COMPAT_FILE}")
        return True
    print("[INFO] compat_redirects.py ja estava atualizado.")
    return False


def registrar_blueprint_app():
    if not APP_FILE.exists():
        print("[AVISO] app.py nao encontrado; nao registrei compat_redirects_bp.")
        return False
    txt, enc = read_text_safe(APP_FILE)
    original = txt
    import_line = "from routes.compat_redirects import compat_redirects_bp\n"
    if "compat_redirects_bp" not in txt:
        lines = txt.splitlines(keepends=True)
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("from routes.") or line.startswith("import routes"):
                insert_idx = i + 1
        lines.insert(insert_idx, import_line)
        txt = "".join(lines)
        print("[APP] Import compat_redirects_bp adicionado.")
    if "register_blueprint(compat_redirects_bp)" not in txt:
        m = re.search(r"^([ \t]*)return app\s*$", txt, flags=re.MULTILINE)
        if m:
            indent = m.group(1)
            txt = txt[:m.start()] + f"{indent}app.register_blueprint(compat_redirects_bp)\n" + txt[m.start():]
            print("[APP] Registro compat_redirects_bp inserido antes de return app.")
        elif "app =" in txt or "Flask(" in txt:
            txt = txt.rstrip() + "\n\n# Compatibilidade de rotas /areas -> /area\ntry:\n    app.register_blueprint(compat_redirects_bp)\nexcept Exception:\n    pass\n"
            print("[APP] Registro compat_redirects_bp anexado ao final.")
        else:
            print("[AVISO] Nao encontrei ponto seguro para registrar blueprint no app.py.")
    if txt != original:
        backup_file(APP_FILE)
        write_text_safe(APP_FILE, txt, enc)
        print("[OK] app.py atualizado.")
        return True
    print("[INFO] app.py ja estava com compat_redirects_bp.")
    return False


def corrigir_links_errados():
    alterados = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or deve_ignorar(path):
            continue
        try:
            txt, enc = read_text_safe(path)
        except Exception:
            continue
        original = txt
        for rota in ROTAS_ERRADAS:
            txt = txt.replace(rota, ROTA_CORRETA)
        if txt != original:
            backup_file(path)
            write_text_safe(path, txt, enc)
            alterados.append(path)
            print(f"[OK] Links corrigidos em: {path.relative_to(ROOT)}")
    return alterados


def corrigir_data_db_cache():
    if not DB_FILE.exists():
        print(f"[AVISO] data/db.py nao encontrado: {DB_FILE}")
        return False
    txt, enc = read_text_safe(DB_FILE)
    original = txt
    inserts = []
    if re.search(r"^\s*_DF_CACHE\s*=", txt, flags=re.MULTILINE) is None:
        inserts.append("_DF_CACHE = {}")
    if re.search(r"^\s*_OPTIONS_CACHE\s*=", txt, flags=re.MULTILINE) is None:
        inserts.append("_OPTIONS_CACHE = {}")
    if not inserts:
        print("[INFO] data/db.py ja possui _DF_CACHE/_OPTIONS_CACHE.")
        return False
    bloco = "\n# Compatibilidade com dashboards legados/migrados\n" + "\n".join(inserts) + "\n"
    linhas = txt.splitlines(keepends=True)
    idx = 0
    for i, line in enumerate(linhas):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from ") or stripped == "" or stripped.startswith("#"):
            idx = i + 1
            continue
        break
    txt = "".join(linhas[:idx]) + bloco + "".join(linhas[idx:])
    if txt != original:
        backup_file(DB_FILE)
        write_text_safe(DB_FILE, txt, enc)
        print("[OK] data/db.py atualizado com _DF_CACHE/_OPTIONS_CACHE.")
        return True
    return False


def extrair_fetches_dash_log():
    achados = []
    candidatos = [TEMPLATES / "dash_log.html", ROOT / "routes" / "dash_log.py", ROOT / "areas" / "adm" / "desconexao" / "dash_log.py"]
    for path in candidatos:
        if not path.exists():
            continue
        txt, _ = read_text_safe(path)
        for m in re.finditer(r"fetch\(([^\n]+)", txt):
            achados.append((path, m.group(0)[:220]))
        for m in re.finditer(r"@[^\n]*route\(([^\n]+)\)", txt):
            achados.append((path, "ROUTE " + m.group(0)[:220]))
    return achados


def gerar_relatorio(resultados):
    linhas = []
    linhas.append("RELATORIO CORRIGIR ROTAS HUB LOG RETIRADA\n")
    linhas.append(f"ROOT: {ROOT}\n")
    linhas.append(f"Rota correta Hub: {ROTA_CORRETA}\n")
    linhas.append("=" * 72 + "\n\n")
    for k, v in resultados.items():
        if isinstance(v, list):
            linhas.append(f"{k}: {len(v)} arquivo(s)\n")
            for item in v:
                linhas.append(f"  - {item}\n")
        else:
            linhas.append(f"{k}: {'SIM' if v else 'NAO'}\n")
    linhas.append("\nDIAGNOSTICO DASH_LOG\n")
    achados = extrair_fetches_dash_log()
    if achados:
        for path, trecho in achados:
            linhas.append(f"Arquivo: {path}\n")
            linhas.append(f"Trecho: {trecho}\n")
            linhas.append("-" * 72 + "\n")
    else:
        linhas.append("Nao encontrei fetch/routes em dash_log.\n")
    if DB_FILE.exists():
        txt, _ = read_text_safe(DB_FILE)
        linhas.append("\nVALIDACAO DATA/DB\n")
        linhas.append(f"_DF_CACHE presente: {'SIM' if '_DF_CACHE' in txt else 'NAO'}\n")
        linhas.append(f"_OPTIONS_CACHE presente: {'SIM' if '_OPTIONS_CACHE' in txt else 'NAO'}\n")
    RELATORIO.write_text("".join(linhas), encoding="utf-8")
    print(f"[RELATORIO] {RELATORIO}")


def main():
    print("=" * 72)
    print("CORRIGIR ROTAS HUB + DIAGNOSTICAR LOG/RETIRADA")
    print("=" * 72)
    print(f"[ROOT] {ROOT}")
    print(f"[ROTA CORRETA] {ROTA_CORRETA}")
    print("-" * 72)
    resultados = {}
    resultados["Criar compat_redirects.py"] = criar_compat_redirects()
    resultados["Registrar blueprint no app.py"] = registrar_blueprint_app()
    resultados["Corrigir links errados"] = [str(p.relative_to(ROOT)) for p in corrigir_links_errados()]
    resultados["Corrigir data/db.py caches"] = corrigir_data_db_cache()
    gerar_relatorio(resultados)
    print("=" * 72)
    print("CONCLUIDO.")
    print("Pare/suba o Flask e use Ctrl+F5.")
    print("Teste:")
    print("1) /areas/adm/desconexao/ deve redirecionar para /area/adm/desconexao/")
    print("2) /dash/executivo/ deve parar de acusar _DF_CACHE")
    print("3) /dash/log/ se ainda acusar JSON, cole o relatorio gerado.")
    print("=" * 72)


if __name__ == "__main__":
    main()
