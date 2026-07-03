# diagnosticar_registrar_safra.py
# Diagnostica e registra o blueprint do Painel Safra no Portal Operações RNO.
# Execute na raiz do projeto OPERACOES_RNO:
# python diagnosticar_registrar_safra.py

from pathlib import Path
from datetime import datetime
import re
import sys

ROOT = Path.cwd()
ALVO_PADRAO = Path(r"C:\Users\n5996917\OneDrive - Claro SA\INTRANET\OPERACOES_RNO")
if not (ROOT / "areas" / "adm" / "desconexao").exists() and ALVO_PADRAO.exists():
    ROOT = ALVO_PADRAO

DASH = ROOT / "areas" / "adm" / "desconexao" / "dash_safra.py"
HTML = ROOT / "areas" / "adm" / "desconexao" / "templates" / "dash_safra.html"
REL = ROOT / "relatorio_diagnostico_registro_safra.txt"

IMPORT_LINE = "from areas.adm.desconexao.dash_safra import dash_safra_bp"
REGISTER_LINE = "app.register_blueprint(dash_safra_bp)"

CANDIDATOS = [
    ROOT / "app.py",
    ROOT / "main.py",
    ROOT / "run.py",
    ROOT / "wsgi.py",
    ROOT / "application.py",
    ROOT / "server.py",
    ROOT / "__init__.py",
]

# inclui __init__.py de subpastas próximas, caso o projeto use create_app em pacote
for p in ROOT.glob("**/__init__.py"):
    if "venv" not in str(p).lower() and "site-packages" not in str(p).lower():
        if p not in CANDIDATOS:
            CANDIDATOS.append(p)


def read(p):
    return p.read_text(encoding="utf-8", errors="ignore")


def write(p, txt):
    p.write_text(txt, encoding="utf-8")


def backup(p):
    b = p.with_suffix(p.suffix + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    write(b, read(p))
    return b


def tem_rota_safra():
    if not DASH.exists():
        return False
    txt = read(DASH)
    return "/dash/safra/" in txt and "dash_safra_bp" in txt


def localizar_arquivo_app():
    prioridade = []
    for p in CANDIDATOS:
        if not p.exists():
            continue
        txt = read(p)
        score = 0
        if "Flask(" in txt: score += 5
        if "create_app" in txt: score += 4
        if "register_blueprint" in txt: score += 4
        if "dash_log" in txt or "dash_retirada" in txt or "dash_quebra" in txt: score += 6
        if "area_construcao" in txt or "Área em Construção" in txt or "area em construcao" in txt.lower(): score += 2
        if score > 0:
            prioridade.append((score, p, txt))
    prioridade.sort(reverse=True, key=lambda x: x[0])
    return prioridade


def inserir_import(txt):
    if IMPORT_LINE in txt:
        return txt, False
    linhas = txt.splitlines()
    pos = 0
    for i, l in enumerate(linhas):
        if l.startswith("import ") or l.startswith("from "):
            pos = i + 1
    linhas.insert(pos, IMPORT_LINE)
    return "\n".join(linhas) + "\n", True


def inserir_registro(txt):
    if "dash_safra_bp" in txt and "register_blueprint(dash_safra_bp" in txt:
        return txt, False, "já existia"

    linhas = txt.splitlines()

    # caso simples: existe app.register_blueprint(...)
    idxs = [i for i, l in enumerate(linhas) if ".register_blueprint(" in l]
    if idxs:
        i = idxs[-1]
        indent = re.match(r"^(\s*)", linhas[i]).group(1)
        linhas.insert(i + 1, indent + REGISTER_LINE)
        return "\n".join(linhas) + "\n", True, "após último register_blueprint"

    # caso create_app: inserir antes do return app
    idxs = [i for i, l in enumerate(linhas) if re.search(r"\breturn\s+app\b", l)]
    if idxs:
        i = idxs[-1]
        indent = re.match(r"^(\s*)", linhas[i]).group(1)
        linhas.insert(i, indent + REGISTER_LINE)
        return "\n".join(linhas) + "\n", True, "antes do return app"

    # caso app = Flask(__name__) sem registros anteriores: inserir depois da criação do app
    idxs = [i for i, l in enumerate(linhas) if "Flask(" in l and "=" in l]
    if idxs:
        i = idxs[0]
        linhas.insert(i + 1, REGISTER_LINE)
        return "\n".join(linhas) + "\n", True, "depois da criação do app"

    return txt, False, "não encontrou ponto seguro de registro"


def main():
    log = []
    log.append("RELATÓRIO — DIAGNÓSTICO/REGISTRO PAINEL SAFRA")
    log.append(f"Data/hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.append(f"Raiz detectada: {ROOT}")
    log.append("")

    log.append(f"dash_safra.py existe: {'SIM' if DASH.exists() else 'NÃO'} — {DASH}")
    log.append(f"dash_safra.html existe: {'SIM' if HTML.exists() else 'NÃO'} — {HTML}")
    log.append(f"Rota /dash/safra/ encontrada no dash_safra.py: {'SIM' if tem_rota_safra() else 'NÃO'}")
    log.append("")

    apps = localizar_arquivo_app()
    log.append("Arquivos candidatos encontrados:")
    if not apps:
        log.append("- Nenhum arquivo app/main/run com Flask/register_blueprint localizado.")
        write(REL, "\n".join(log))
        print("ERRO: não encontrei arquivo principal Flask. Veja o relatório:", REL)
        return

    for score, p, _ in apps[:10]:
        log.append(f"- score {score}: {p}")

    alvo = apps[0][1]
    txt = apps[0][2]
    log.append("")
    log.append(f"Arquivo escolhido para registro: {alvo}")

    if not DASH.exists():
        log.append("ERRO: dash_safra.py não existe. Crie primeiro o dashboard.")
        write(REL, "\n".join(log))
        print("ERRO: dash_safra.py não existe. Veja o relatório:", REL)
        return

    if "dash_safra" in txt and "register_blueprint(dash_safra_bp" in txt:
        log.append("Status: dash_safra já parecia registrado. Nenhuma alteração aplicada.")
        write(REL, "\n".join(log))
        print("OK: dash_safra já parecia registrado. Relatório:", REL)
        return

    bkp = backup(alvo)
    txt2, imp = inserir_import(txt)
    txt3, reg, modo = inserir_registro(txt2)

    if not reg:
        log.append("ATENÇÃO: não foi possível registrar automaticamente com segurança.")
        log.append(f"Backup criado mesmo assim: {bkp}")
        log.append("Cole manualmente estas duas linhas no arquivo principal Flask, dentro do create_app ou após criar app:")
        log.append(IMPORT_LINE)
        log.append(REGISTER_LINE)
        write(REL, "\n".join(log))
        print("ATENÇÃO: registro automático não aplicado. Veja:", REL)
        return

    write(alvo, txt3)
    log.append(f"Backup criado: {bkp}")
    log.append(f"Import inserido: {'SIM' if imp else 'já existia'}")
    log.append(f"Registro inserido: SIM — modo: {modo}")
    log.append("")
    log.append("Próximos testes no navegador:")
    log.append("- http://localhost:5000/dash/safra/")
    log.append("- http://localhost:5000/dash/safra/api/options")
    log.append("- http://localhost:5000/dash/safra/api/data")
    log.append("")
    log.append("IMPORTANTE: reinicie o Flask depois de executar este script.")

    write(REL, "\n".join(log))
    print("OK: registro do Painel Safra aplicado.")
    print("Arquivo alterado:", alvo)
    print("Backup:", bkp)
    print("Relatório:", REL)
    print("Reinicie o Flask e teste /dash/safra/.")

if __name__ == "__main__":
    main()
