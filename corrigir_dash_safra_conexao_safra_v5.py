# corrigir_dash_safra_conexao_safra_v5.py
from pathlib import Path
from datetime import datetime
import re

ROOT = Path.cwd()
PADRAO = Path(r'C:\Users\n5996917\OneDrive - Claro SA\INTRANET\OPERACOES_RNO')
if not (ROOT / 'areas' / 'adm' / 'desconexao').exists() and PADRAO.exists():
    ROOT = PADRAO

DASH = ROOT / 'areas' / 'adm' / 'desconexao' / 'dash_safra.py'
REL = ROOT / 'relatorio_corrigir_dash_safra_conexao_safra_v5.txt'

DB_BLOCK = '''
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "safra",
    "port": 3306,
}

ULTIMO_ERRO_CONEXAO = ""
'''

CONN_FUNC = '''
def _conn():
    global ULTIMO_ERRO_CONEXAO
    erros = []
    try:
        import pymysql
        return pymysql.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            port=int(DB_CONFIG["port"]),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.Cursor,
        )
    except Exception as e:
        erros.append(f"PyMySQL: {type(e).__name__}: {e}")
    try:
        import mysql.connector
        return mysql.connector.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            port=int(DB_CONFIG["port"]),
        )
    except Exception as e:
        erros.append(f"mysql.connector: {type(e).__name__}: {e}")
    ULTIMO_ERRO_CONEXAO = " | ".join(erros)
    raise RuntimeError("Falha de conexão MySQL. " + ULTIMO_ERRO_CONEXAO)
'''

DIAG_ROUTE = '''

@bp.route("/dash/safra/api/diagnostico")
def diagnostico():
    try:
        c = _conn()
        try:
            db = pd.read_sql("SELECT DATABASE() AS banco", c).iloc[0]["banco"]
            tabelas = {}
            for t in [TBL_MENSAL, TBL_DIARIO, TBL_METAS]:
                try:
                    tabelas[t] = int(pd.read_sql(f"SELECT COUNT(*) AS total FROM {t}", c).iloc[0]["total"])
                except Exception as e:
                    tabelas[t] = f"ERRO: {type(e).__name__}: {e}"
            return jsonify({"ok": True, "banco": db, "tabelas": tabelas, "config": {"host": DB_CONFIG["host"], "database": DB_CONFIG["database"], "port": DB_CONFIG["port"]}})
        finally:
            try:
                c.close()
            except Exception:
                pass
    except Exception as e:
        return jsonify({"ok": False, "erro": f"{type(e).__name__}: {e}", "ultimo_erro_conexao": ULTIMO_ERRO_CONEXAO, "config": {"host": DB_CONFIG["host"], "database": DB_CONFIG["database"], "port": DB_CONFIG["port"]}})
'''


def main():
    if not DASH.exists():
        msg = f'ERRO: dash_safra.py não encontrado em {DASH}'
        REL.write_text(msg, encoding='utf-8')
        print(msg)
        return

    original = DASH.read_text(encoding='utf-8', errors='ignore')
    bkp = DASH.with_suffix('.py.bak_conexao_safra_v5_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    bkp.write_text(original, encoding='utf-8')
    txt = original

    txt = txt.replace('database="operacoes_rno"', 'database="safra"')
    txt = txt.replace("database='operacoes_rno'", "database='safra'")
    txt = txt.replace('"database": "operacoes_rno"', '"database": "safra"')
    txt = txt.replace("'database': 'operacoes_rno'", "'database': 'safra'")

    txt = re.sub(r'\nDB_CONFIG\s*=\s*\{.*?\}\s*\n\s*ULTIMO_ERRO_CONEXAO\s*=\s*["\'].*?["\']\s*\n', '\n', txt, flags=re.S)
    if 'TBL_METAS' in txt:
        txt = re.sub(r'(TBL_METAS\s*=\s*["\']safra_metas["\']\s*)', r'\1' + DB_BLOCK, txt, count=1)
    else:
        txt = re.sub(r'(import\s+math\s*)', r'\1' + DB_BLOCK, txt, count=1)

    padrao_conn = r'\ndef _conn\(\):.*?\n\ndef _read_sql\('
    if re.search(padrao_conn, txt, flags=re.S):
        txt = re.sub(padrao_conn, CONN_FUNC + '\n\ndef _read_sql(', txt, count=1, flags=re.S)
        conn_status = '_conn substituida'
    else:
        txt = txt.replace('\ndef _read_sql(', CONN_FUNC + '\n\ndef _read_sql(', 1)
        conn_status = '_conn inserida antes de _read_sql'

    if '/dash/safra/api/diagnostico' not in txt:
        idx = txt.find('@bp.route("/dash/safra/api/options")')
        if idx != -1:
            txt = txt[:idx] + DIAG_ROUTE + '\n' + txt[idx:]
            diag_status = 'diagnostico inserido antes de options'
        else:
            txt += DIAG_ROUTE
            diag_status = 'diagnostico anexado ao final'
    else:
        diag_status = 'diagnostico ja existia'

    DASH.write_text(txt, encoding='utf-8')
    rel = [
        'RELATORIO - CORRIGIR DASH SAFRA CONEXAO SAFRA V5',
        f'Data/hora: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        f'Raiz: {ROOT}',
        f'Arquivo corrigido: {DASH}',
        f'Backup: {bkp}',
        'Banco configurado: safra',
        'Host: localhost',
        'Porta: 3306',
        'Usuario: root',
        f'Status conexao: {conn_status}',
        f'Status diagnostico: {diag_status}',
        'Teste apos reiniciar Flask: /dash/safra/api/diagnostico',
    ]
    REL.write_text('\n'.join(rel), encoding='utf-8')
    print("OK - dash_safra.py corrigido para database='safra'.")
    print('Backup:', bkp)
    print('Relatorio:', REL)
    print('Reinicie o Flask e teste: http://localhost:5000/dash/safra/api/diagnostico')


if __name__ == '__main__':
    main()
