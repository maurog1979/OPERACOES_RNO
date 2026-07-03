# localizar_origem_safra_v3.py
# FASE 2C — Localiza a origem real das tabelas Safra e ajusta o fallback do dash_safra.py
# Execute na raiz do projeto:
# cd "C:\Users\n5996917\OneDrive - Claro SA\INTRANET\OPERACOES_RNO"
# python localizar_origem_safra_v3.py

from pathlib import Path
from datetime import datetime
import re
import sys
import traceback

ROOT = Path.cwd()
PADRAO = Path(r"C:\Users\n5996917\OneDrive - Claro SA\INTRANET\OPERACOES_RNO")
if not (ROOT / "areas" / "adm" / "desconexao").exists() and PADRAO.exists():
    ROOT = PADRAO

DASH = ROOT / "areas" / "adm" / "desconexao" / "dash_safra.py"
REL = ROOT / "relatorio_localizar_origem_safra_v3.txt"
TABELAS = ["safra_resumo_mensal", "safra_resumo_diario", "safra_metas", "safra_carga_controle"]


def add(log, txt=""):
    log.append(str(txt))


def read(p):
    return p.read_text(encoding="utf-8", errors="ignore")


def q(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params or [])
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description] if cur.description else []
    cur.close()
    return cols, rows


def scalar(conn, sql, params=None):
    _, rows = q(conn, sql, params)
    return rows[0][0] if rows else None


def db_atual(conn):
    try:
        return scalar(conn, "SELECT DATABASE()")
    except Exception:
        return None


def existe_tabela(conn, tabela):
    try:
        _, rows = q(conn, "SHOW TABLES LIKE %s", [tabela])
        return bool(rows)
    except Exception:
        return False


def contar(conn, tabela):
    try:
        return scalar(conn, f"SELECT COUNT(*) FROM {tabela}")
    except Exception as e:
        return f"ERRO {type(e).__name__}: {e}"


def colunas(conn, tabela):
    try:
        _, rows = q(conn, f"SHOW COLUMNS FROM {tabela}")
        return [r[0] for r in rows]
    except Exception:
        return []


def conectar_mysql(host="localhost", user="root", password="", database=None, port=None):
    import mysql.connector
    kwargs = {"host": host or "localhost", "user": user or "root", "password": password or ""}
    if database:
        kwargs["database"] = database
    if port:
        try:
            kwargs["port"] = int(port)
        except Exception:
            pass
    return mysql.connector.connect(**kwargs)


def extrair_pistas(txt):
    pistas = []

    # mysql.connector.connect(...)
    for m in re.finditer(r"mysql\.connector\.connect\((.*?)\)", txt, flags=re.S | re.I):
        bloco = m.group(1)
        item = {}
        for k in ["host", "user", "password", "passwd", "database", "db", "port"]:
            mm = re.search(k + r"\s*=\s*['\"]([^'\"]*)['\"]", bloco, flags=re.I)
            if mm:
                item[k] = mm.group(1)
        if item:
            pistas.append(item)

    # variáveis comuns em .py/.env
    aliases = {
        "host": ["DB_HOST", "MYSQL_HOST", "HOST"],
        "user": ["DB_USER", "MYSQL_USER", "USER"],
        "password": ["DB_PASSWORD", "MYSQL_PASSWORD", "PASSWORD", "SENHA"],
        "database": ["DB_NAME", "DB_DATABASE", "MYSQL_DATABASE", "DATABASE", "BANCO"],
        "port": ["DB_PORT", "MYSQL_PORT", "PORT"],
    }
    item = {}
    for dest, keys in aliases.items():
        for key in keys:
            mm = re.search(rf"\b{re.escape(key)}\b\s*=\s*['\"]?([^'\"\n\r#]+)", txt, flags=re.I)
            if mm:
                val = mm.group(1).strip().strip(",")
                if val and not any(x in val for x in ["(", ")", "{", "}"]):
                    item[dest] = val
                    break
    if item:
        pistas.append(item)

    # URI mysql://user:pass@host:port/db
    for m in re.finditer(r"mysql(?:\+\w+)?://([^:\s]+):?([^@\s]*)@([^/:\s]+):?(\d*)/([^\s'\"]+)", txt, flags=re.I):
        pistas.append({"user": m.group(1), "password": m.group(2), "host": m.group(3), "port": m.group(4), "database": m.group(5).split("?")[0]})

    return pistas


def normalizar(p):
    return {
        "host": p.get("host") or "localhost",
        "user": p.get("user") or "root",
        "password": p.get("password") or p.get("passwd") or "",
        "database": p.get("database") or p.get("db") or None,
        "port": p.get("port") or None,
    }


def listar_arquivos(log):
    nomes = {"criar_base_painel_safra.py", "relatorio_criar_base_painel_safra.txt", "db.py", "config.py", ".env", "app.py", "main.py", "run.py"}
    achados = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        s = str(p).lower()
        if "venv" in s or "site-packages" in s or "__pycache__" in s:
            continue
        if p.name in nomes or p.name.endswith(".py"):
            try:
                txt = read(p)
            except Exception:
                continue
            if p.name in nomes or any(t in txt.lower() for t in ["safra_resumo", "safra_metas", "mysql", "database", "db_name"]):
                achados.append(p)
    add(log, "ARQUIVOS ANALISADOS:")
    for p in achados:
        add(log, f"- {p}")
    return achados


def tentar_oficial(log):
    sys.path.insert(0, str(ROOT))
    funcoes = [
        ("data.db", "get_connection"),
        ("data.db", "get_db_connection"),
        ("data.db", "conectar"),
        ("data.db", "get_conn"),
        ("db", "get_connection"),
        ("db", "get_db_connection"),
        ("db", "conectar"),
    ]
    for mod, fn in funcoes:
        try:
            m = __import__(mod, fromlist=[fn])
            c = getattr(m, fn)()
            if c:
                add(log, f"Conexão oficial OK: {mod}.{fn} | banco={db_atual(c)}")
                return c, {"origem": f"{mod}.{fn}", "database": db_atual(c)}
        except Exception as e:
            add(log, f"Conexão oficial falhou: {mod}.{fn} | {type(e).__name__}: {e}")
    return None, None


def score_conn(conn, log, origem):
    banco = db_atual(conn)
    score = 0
    add(log, f"\nANALISANDO: {origem} | banco={banco}")
    for t in TABELAS:
        ex = existe_tabela(conn, t)
        cnt = contar(conn, t) if ex else "NÃO EXISTE"
        add(log, f"- {t}: existe={ex} | linhas={cnt}")
        if ex:
            score += 1
    return score


def varrer_com_cred(cred, log):
    resultados = []
    # banco direto
    if cred.get("database"):
        try:
            c = conectar_mysql(**cred)
            sc = score_conn(c, log, f"credencial direta {cred.get('database')}")
            resultados.append((sc, db_atual(c), c, cred, "direta"))
        except Exception as e:
            add(log, f"Falha conexão direta {cred}: {type(e).__name__}: {e}")
    # varredura geral com host/user/senha/porta
    try:
        c0 = conectar_mysql(host=cred.get("host"), user=cred.get("user"), password=cred.get("password"), port=cred.get("port"))
        _, rows = q(c0, "SHOW DATABASES")
        bancos = [r[0] for r in rows]
        c0.close()
    except Exception as e:
        add(log, f"Falha ao listar bancos com {cred}: {type(e).__name__}: {e}")
        return resultados
    for db in bancos:
        if str(db).lower() in ["information_schema", "mysql", "performance_schema", "sys"]:
            continue
        try:
            c = conectar_mysql(host=cred.get("host"), user=cred.get("user"), password=cred.get("password"), database=db, port=cred.get("port"))
            sc = score_conn(c, log, f"varredura {db}")
            resultados.append((sc, db, c, {**cred, "database": db}, "varredura"))
        except Exception as e:
            add(log, f"Falha abrindo banco {db}: {type(e).__name__}: {e}")
    return resultados


def patch_dash(db, cred, log):
    if not DASH.exists():
        add(log, "dash_safra.py não existe; não foi possível aplicar patch.")
        return
    txt = read(DASH)
    bkp = DASH.with_suffix(".py.bak_origem_v3_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    bkp.write_text(txt, encoding="utf-8")

    host = cred.get("host") or "localhost"
    user = cred.get("user") or "root"
    password = cred.get("password") or ""
    port = cred.get("port")

    # Corrige database="..." em fallback existente.
    txt2 = re.sub(r'database\s*=\s*["\'][^"\']+["\']', f'database="{db}"', txt)
    txt2 = re.sub(r'host\s*=\s*["\'][^"\']+["\']', f'host="{host}"', txt2, count=1)
    txt2 = re.sub(r'user\s*=\s*["\'][^"\']+["\']', f'user="{user}"', txt2, count=1)
    txt2 = re.sub(r'password\s*=\s*["\'][^"\']*["\']', f'password="{password}"', txt2, count=1)

    # Se existir DB_FALLBACK dict, substitui tudo.
    if "DB_FALLBACK" in txt2:
        port_txt = f', port={int(port)}' if str(port or '').isdigit() else ''
        txt2 = re.sub(
            r'DB_FALLBACK\s*=\s*dict\([^\)]*\)',
            f'DB_FALLBACK = dict(host="{host}", user="{user}", password="{password}", database="{db}"{port_txt})',
            txt2,
            flags=re.S
        )

    DASH.write_text(txt2, encoding="utf-8")
    add(log, f"dash_safra.py ajustado para banco={db}. Backup: {bkp}")


def main():
    log = []
    add(log, "RELATÓRIO — LOCALIZAR ORIGEM SAFRA V3")
    add(log, f"Data/hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    add(log, f"Raiz detectada: {ROOT}")
    add(log, f"dash_safra.py existe: {DASH.exists()} — {DASH}\n")

    pistas = []
    arquivos = listar_arquivos(log)
    for p in arquivos:
        try:
            txt = read(p)
            ps = extrair_pistas(txt)
            if ps:
                add(log, f"\nPistas extraídas de {p}:")
                for item in ps:
                    safe = dict(item)
                    if safe.get("password"):
                        safe["password"] = "***"
                    if safe.get("passwd"):
                        safe["passwd"] = "***"
                    add(log, f"- {safe}")
                pistas.extend(ps)
        except Exception as e:
            add(log, f"Falha lendo {p}: {type(e).__name__}: {e}")

    # padrões e alternativas prováveis
    pistas.extend([
        {"host": "localhost", "user": "root", "password": "", "database": "operacoes_rno"},
        {"host": "localhost", "user": "root", "password": "", "database": "portal_desconexao"},
        {"host": "localhost", "user": "root", "password": "", "database": "desconexao"},
        {"host": "127.0.0.1", "user": "root", "password": "", "database": None},
        {"host": "localhost", "user": "root", "password": "", "database": None},
    ])

    creds = []
    seen = set()
    for p in pistas:
        c = normalizar(p)
        key = (c.get("host"), c.get("user"), c.get("password"), c.get("database"), c.get("port"))
        if key not in seen:
            seen.add(key)
            creds.append(c)

    add(log, "\nCREDENCIAIS NORMALIZADAS TESTADAS:")
    for c in creds:
        add(log, f"- host={c.get('host')} user={c.get('user')} password={'***' if c.get('password') else ''} database={c.get('database')} port={c.get('port')}")

    melhor = None

    c_oficial, info = tentar_oficial(log)
    if c_oficial:
        sc = score_conn(c_oficial, log, "oficial")
        melhor = (sc, db_atual(c_oficial), c_oficial, {"host":"localhost", "user":"root", "password":""}, "oficial")

    for cred in creds:
        for item in varrer_com_cred(cred, log):
            sc, db, conn, used_cred, origem = item
            if melhor is None or sc > melhor[0]:
                if melhor and melhor[2] is not conn:
                    try: melhor[2].close()
                    except Exception: pass
                melhor = item
            else:
                try: conn.close()
                except Exception: pass

    add(log, "")
    if not melhor or melhor[0] <= 0:
        add(log, "RESULTADO FINAL: nenhuma tabela Safra localizada em qualquer conexão testada.")
        add(log, "CONCLUSÃO TÉCNICA: o script criar_base_painel_safra.py provavelmente gravou em outro ambiente/conexão não detectado, ou a criação das tabelas foi feita em outro banco/instância MySQL.")
        add(log, "PRÓXIMO PASSO: reexecutar criar_base_painel_safra.py e, em seguida, executar este script novamente; ou abrir o relatorio_criar_base_painel_safra.txt para confirmar se ele informa banco/schema/conexão.")
        REL.write_text("\n".join(log), encoding="utf-8")
        print("ERRO — nenhuma tabela Safra localizada.")
        print("Relatório:", REL)
        return

    sc, db, conn, cred, origem = melhor
    add(log, f"RESULTADO FINAL: origem={origem} | banco={db} | score={sc}")
    for t in TABELAS:
        add(log, "")
        add(log, f"TABELA: {t}")
        add(log, f"Existe: {existe_tabela(conn, t)}")
        if existe_tabela(conn, t):
            add(log, f"Linhas: {contar(conn, t)}")
            add(log, f"Colunas: {', '.join(colunas(conn, t))}")

    patch_dash(db, cred, log)
    try: conn.close()
    except Exception: pass

    add(log, "")
    add(log, "AÇÃO: reinicie o Flask e teste /dash/safra/api/options")
    REL.write_text("\n".join(log), encoding="utf-8")
    print("OK — origem Safra localizada e dash_safra.py ajustado.")
    print("Banco:", db)
    print("Score:", sc)
    print("Relatório:", REL)
    print("Reinicie o Flask e teste /dash/safra/api/options")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        REL.write_text(traceback.format_exc(), encoding="utf-8")
        print("ERRO inesperado. Veja:", REL)
