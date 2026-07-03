# diagnosticar_corrigir_safra_dados.py
# FASE 2C — Diagnóstico de dados do Painel Safra
# Objetivo:
# 1) Confirmar qual banco o Flask/dash_safra.py está usando.
# 2) Verificar se safra_resumo_mensal, safra_resumo_diario e safra_metas existem e têm linhas.
# 3) Verificar colunas reais.
# 4) Corrigir dash_safra.py com conexão mais robusta e aliases ampliados.
#
# Execute na raiz do projeto:
# cd "C:\Users\n5996917\OneDrive - Claro SA\INTRANET\OPERACOES_RNO"
# python diagnosticar_corrigir_safra_dados.py

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
REL = ROOT / "relatorio_diagnostico_safra_dados.txt"

TABELAS = ["safra_resumo_mensal", "safra_resumo_diario", "safra_metas"]

DB_CANDIDATOS = [
    "operacoes_rno",
    "portal_desconexao",
    "desconexao",
    "portal_operacoes_rno",
    "operacoesrno",
    "claro_rno",
]


def log_add(log, txt=""):
    log.append(str(txt))


def try_import_connection(log):
    sys.path.insert(0, str(ROOT))
    tentativas = [
        ("data.db", "get_connection"),
        ("data.db", "get_db_connection"),
        ("data.db", "conectar"),
        ("data.db", "connection"),
        ("data.db", "get_conn"),
    ]
    for mod, fn in tentativas:
        try:
            m = __import__(mod, fromlist=[fn])
            f = getattr(m, fn)
            c = f()
            if c:
                log_add(log, f"Conexão via {mod}.{fn}: OK")
                return c, f"{mod}.{fn}"
        except Exception as e:
            log_add(log, f"Conexão via {mod}.{fn}: falhou — {type(e).__name__}: {e}")
    return None, None


def mysql_connect(database=None):
    import mysql.connector
    kwargs = dict(host="localhost", user="root", password="")
    if database:
        kwargs["database"] = database
    return mysql.connector.connect(**kwargs)


def q_all(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params or [])
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description] if cur.description else []
    cur.close()
    return cols, rows


def scalar(conn, sql, params=None):
    cols, rows = q_all(conn, sql, params)
    return rows[0][0] if rows else None


def get_database(conn):
    try:
        return scalar(conn, "SELECT DATABASE()")
    except Exception:
        return None


def table_exists(conn, table):
    try:
        _, rows = q_all(conn, "SHOW TABLES LIKE %s", [table])
        return bool(rows)
    except Exception:
        return False


def table_count(conn, table):
    try:
        return scalar(conn, f"SELECT COUNT(*) FROM {table}")
    except Exception as e:
        return f"ERRO: {type(e).__name__}: {e}"


def table_columns(conn, table):
    try:
        _, rows = q_all(conn, f"SHOW COLUMNS FROM {table}")
        return [r[0] for r in rows]
    except Exception:
        return []


def sample_rows(conn, table, limit=3):
    try:
        cols, rows = q_all(conn, f"SELECT * FROM {table} LIMIT {limit}")
        return cols, rows
    except Exception as e:
        return [], [(f"ERRO: {type(e).__name__}: {e}",)]


def encontrar_banco_com_tabelas(log):
    # 1) tenta conexão oficial do projeto
    conn, origem = try_import_connection(log)
    if conn:
        db = get_database(conn)
        ok = [t for t in TABELAS if table_exists(conn, t)]
        log_add(log, f"Banco ativo pela conexão oficial: {db}")
        log_add(log, f"Tabelas encontradas na conexão oficial: {ok}")
        if ok:
            return conn, origem, db
        try:
            conn.close()
        except Exception:
            pass

    # 2) varre bancos locais
    try:
        base = mysql_connect()
        _, dbs_rows = q_all(base, "SHOW DATABASES")
        dbs = [r[0] for r in dbs_rows]
        try:
            base.close()
        except Exception:
            pass
    except Exception as e:
        log_add(log, f"Falha ao listar bancos MySQL locais: {type(e).__name__}: {e}")
        dbs = []

    ordenados = []
    for d in DB_CANDIDATOS:
        if d in dbs and d not in ordenados:
            ordenados.append(d)
    for d in dbs:
        if d not in ordenados and not str(d).lower().startswith(("information_schema", "mysql", "performance_schema", "sys")):
            ordenados.append(d)

    melhor = None
    melhor_score = -1
    for db in ordenados:
        try:
            c = mysql_connect(db)
            score = sum(1 for t in TABELAS if table_exists(c, t))
            contagens = {t: table_count(c, t) if table_exists(c, t) else "NÃO EXISTE" for t in TABELAS}
            log_add(log, f"Banco analisado: {db} | score={score} | contagens={contagens}")
            if score > melhor_score:
                if melhor:
                    try:
                        melhor.close()
                    except Exception:
                        pass
                melhor = c
                melhor_score = score
            else:
                c.close()
        except Exception as e:
            log_add(log, f"Banco analisado: {db} | falhou: {type(e).__name__}: {e}")

    if melhor and melhor_score > 0:
        return melhor, "mysql.connector varredura", get_database(melhor)

    return None, None, None


def normalizar_lista(cols):
    return ", ".join(cols) if cols else "SEM COLUNAS / TABELA NÃO ENCONTRADA"


def corrigir_dash(db_name, log):
    if not DASH.exists():
        log_add(log, f"dash_safra.py não existe em {DASH}. Não foi possível corrigir.")
        return "NÃO CORRIGIDO — dash_safra.py inexistente"

    txt = DASH.read_text(encoding="utf-8", errors="ignore")
    bkp = DASH.with_suffix(".py.bak_dados_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    bkp.write_text(txt, encoding="utf-8")

    # troca fallback database se houver database="..."
    if db_name:
        txt2 = re.sub(r'database\s*=\s*["\'][^"\']+["\']', f'database="{db_name}"', txt)
    else:
        txt2 = txt

    # amplia aliases se o arquivo tiver esses blocos; se já tiver, não prejudica.
    aliases_desc = '["DESC", "DESCONECTADOS", "TOTAL_DESC", "QTD_DESC", "VOLUME_DESC", "TOTAL_DESCONECTADO", "TOTAL_DESCONECTADOS", "DESCON", "QTD_DESCONECTADO", "QTD_DESCONECTADOS", "TOTAL", "QTDE_DESC"]'
    aliases_rec = '["REC", "RECUPERADOS", "TOTAL_REC", "QTD_REC", "VOLUME_REC", "TOTAL_RECUPERADO", "TOTAL_RECUPERADOS", "RECUP", "QTD_RECUPERADO", "QTD_RECUPERADOS", "QTDE_REC"]'

    txt2 = re.sub(r'\["DESC",\s*"DESCONECTADOS"[^\]]+\]', aliases_desc, txt2)
    txt2 = re.sub(r'\["REC",\s*"RECUPERADOS"[^\]]+\]', aliases_rec, txt2)

    DASH.write_text(txt2, encoding="utf-8")
    return f"CORRIGIDO — backup criado em {bkp}"


def main():
    log = []
    log_add(log, "RELATÓRIO — DIAGNÓSTICO DE DADOS DO PAINEL SAFRA")
    log_add(log, f"Data/hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_add(log, f"Raiz detectada: {ROOT}")
    log_add(log, f"dash_safra.py: {DASH} | existe={DASH.exists()}")
    log_add(log, "")

    try:
        conn, origem, db = encontrar_banco_com_tabelas(log)
        log_add(log, "")
        log_add(log, f"CONEXÃO SELECIONADA: origem={origem} | banco={db}")

        if not conn:
            log_add(log, "ERRO FINAL: nenhuma conexão com as tabelas Safra foi encontrada.")
            REL.write_text("\n".join(log), encoding="utf-8")
            print("ERRO — nenhuma conexão/tabela Safra encontrada. Veja:", REL)
            return

        for t in TABELAS:
            log_add(log, "")
            log_add(log, "=" * 80)
            log_add(log, f"TABELA: {t}")
            existe = table_exists(conn, t)
            log_add(log, f"Existe: {'SIM' if existe else 'NÃO'}")
            if existe:
                log_add(log, f"Linhas: {table_count(conn, t)}")
                cols = table_columns(conn, t)
                log_add(log, f"Colunas: {normalizar_lista(cols)}")
                scols, rows = sample_rows(conn, t, 3)
                log_add(log, f"Amostra colunas: {normalizar_lista(scols)}")
                for r in rows:
                    log_add(log, f"Amostra linha: {r}")

        status = corrigir_dash(db, log)
        log_add(log, "")
        log_add(log, f"Correção aplicada no dash_safra.py: {status}")
        log_add(log, "")
        log_add(log, "PRÓXIMO TESTE:")
        log_add(log, "1) Reinicie o Flask.")
        log_add(log, "2) Abra /dash/safra/api/options")
        log_add(log, "3) Abra /dash/safra/api/data")
        log_add(log, "4) Abra /dash/safra/")

        try:
            conn.close()
        except Exception:
            pass

        REL.write_text("\n".join(log), encoding="utf-8")
        print("OK — diagnóstico concluído e dash_safra.py ajustado.")
        print("Banco selecionado:", db)
        print("Relatório:", REL)
        print("Reinicie o Flask e teste /dash/safra/api/options.")

    except Exception:
        log_add(log, "ERRO INESPERADO:")
        log_add(log, traceback.format_exc())
        REL.write_text("\n".join(log), encoding="utf-8")
        print("ERRO inesperado. Veja:", REL)


if __name__ == "__main__":
    main()
