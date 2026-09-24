# -*- coding: utf-8 -*-
"""
=====================================================================
PORTAL OPERACOES RNO - DATA MART DESCONEXAO
diag_01_perfilar.py - Perfilamento automatico das tabelas staging
=====================================================================
ARQUIVO COMPLETO E CORRIGIDO

CORRECAO APLICADA
  TypeError: unsupported operand type(s) for +: 'decimal.Decimal' and 'float'
  O MySQL devolve Decimal em SUM(). Agora todo valor numerico passa
  por num() antes de qualquer operacao aritmetica.

POR QUE ESTE SCRIPT EXISTE
  Tentamos converter campos assumindo o tipo e erramos duas vezes:
    AGING               -> parecia numero, e categoria
    TEMPO_ABERTURA_DIAS -> parecia numero, e categoria

  Este script PERFILA todos os campos ANTES de qualquer conversao.

SAIDA
    diagnostico/perfil_<tabela>.txt     relatorio legivel
    diagnostico/perfil_completo.md      consolidado em markdown
    diagnostico/tipos_sugeridos.sql     DDL sugerido

USO
    python diag_01_perfilar.py
    python diag_01_perfilar.py --tabela stg_backlog
    python diag_01_perfilar.py --tabela stg_safra --top 30
=====================================================================
"""

import os
import sys
import argparse
from decimal import Decimal
from datetime import datetime
from collections import OrderedDict

try:
    import pymysql
except ImportError:
    sys.exit("ERRO: pymysql nao instalado.  Execute:  pip install pymysql")

try:
    from etl_config import DB
except ImportError:
    DB = {
        "host": "127.0.0.1", "port": 3306, "user": "root",
        "password": "", "database": "desconexao_rno", "charset": "utf8mb4",
    }


SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagnostico")
os.makedirs(SAIDA, exist_ok=True)

TABELAS_PADRAO = [
    "stg_quebra", "stg_quebra_compl", "stg_toa",
    "stg_safra", "stg_backlog", "stg_metas",
]

RE_INT      = r"^-?[0-9]+$"
RE_DEC      = r"^-?[0-9]+[.,][0-9]+$"
RE_DATA_BR  = r"^[0-9]{2}/[0-9]{2}/[0-9]{2,4}"
RE_DATA_ISO = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}"


# ---------------------------------------------------------------------
# CORRECAO: converte Decimal/None para float com seguranca
# ---------------------------------------------------------------------
def num(v):
    """Converte Decimal, int, str ou None para float."""
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def inteiro(v):
    """Converte para int com seguranca."""
    return int(num(v))


def conectar():
    try:
        cnx = pymysql.connect(
            host=DB["host"], port=DB["port"], user=DB["user"],
            password=DB["password"], database=DB["database"],
            charset=DB["charset"], cursorclass=pymysql.cursors.DictCursor,
        )
        print(f"Conectado -> {DB['host']}/{DB['database']}\n")
        return cnx
    except Exception as e:
        sys.exit(f"ERRO de conexao: {e}\nVerifique se o MySQL do Laragon esta ativo.")


def listar_colunas(cnx, tabela):
    with cnx.cursor() as cur:
        cur.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """, (DB["database"], tabela))
        return cur.fetchall()


def perfilar_coluna(cnx, tabela, coluna, top=15):
    c = f"`{coluna}`"
    with cnx.cursor() as cur:
        cur.execute(f"""
            SELECT
                COUNT(*)                                  AS total,
                SUM({c} IS NULL)                          AS nulos,
                SUM({c} IS NOT NULL AND TRIM({c}) = '')   AS vazios,
                SUM(TRIM({c}) = '-3')                     AS menos3,
                COUNT(DISTINCT {c})                       AS distintos,
                SUM(TRIM({c}) REGEXP '{RE_INT}')          AS q_int,
                SUM(TRIM({c}) REGEXP '{RE_DEC}')          AS q_dec,
                SUM(TRIM({c}) REGEXP '{RE_DATA_BR}')      AS q_data_br,
                SUM(TRIM({c}) REGEXP '{RE_DATA_ISO}')     AS q_data_iso,
                MAX(CHAR_LENGTH({c}))                     AS max_len,
                ROUND(AVG(CHAR_LENGTH({c})), 1)           AS avg_len
            FROM {tabela}
        """)
        p = cur.fetchone()

        # normaliza TODOS os numericos logo na origem
        for k in ("total", "nulos", "vazios", "menos3", "distintos",
                  "q_int", "q_dec", "q_data_br", "q_data_iso", "max_len"):
            p[k] = inteiro(p.get(k))
        p["avg_len"] = round(num(p.get("avg_len")), 1)

        cur.execute(f"""
            SELECT IFNULL(NULLIF(TRIM({c}), ''), '(vazio)') AS valor,
                   COUNT(*) AS qtd
            FROM {tabela}
            GROUP BY IFNULL(NULLIF(TRIM({c}), ''), '(vazio)')
            ORDER BY qtd DESC
            LIMIT {top}
        """)
        p["top_valores"] = [
            {"valor": r["valor"], "qtd": inteiro(r["qtd"])}
            for r in cur.fetchall()
        ]

    return p


def classificar(p):
    """Decide o tipo real da coluna a partir do perfil."""
    total = p["total"]
    preenchidos = total - p["nulos"] - p["vazios"]

    if preenchidos <= 0:
        return "VAZIO", "campo sem conteudo - descartar"

    def pct(x):
        return num(x) / preenchidos * 100.0

    p_int  = pct(p["q_int"])
    p_dec  = pct(p["q_dec"])
    p_data = pct(p["q_data_br"]) + pct(p["q_data_iso"])
    p_num  = p_int + p_dec

    if p_int >= 99.0:
        return "INTEIRO", "converter com CAST AS SIGNED"
    if p_num >= 99.0:
        return "DECIMAL", "converter com CAST AS DECIMAL"
    if p_data >= 99.0:
        return "DATA", "converter com STR_TO_DATE"
    if p_data >= 20.0 and p_num >= 20.0:
        return "MISTO", (f"MISTURA data ({p_data:.0f}%) e numero ({p_num:.0f}%) "
                         "- manter TEXTO")
    if p_data >= 20.0:
        return "MISTO", (f"parte data ({p_data:.0f}%), parte texto "
                         "- manter TEXTO")
    if p_num >= 20.0:
        return "MISTO", (f"parte numero ({p_num:.0f}%), parte texto "
                         "- manter TEXTO")

    if p["distintos"] <= 50:
        return "CATEGORIA", f"categorico com {p['distintos']} valores"

    return "TEXTO", "texto livre"


def tipo_mysql(p, classe):
    if classe == "VAZIO":
        return "-- descartar"
    if classe == "INTEIRO":
        return "INT" if p["max_len"] <= 9 else "BIGINT"
    if classe == "DECIMAL":
        return "DECIMAL(18,4)"
    if classe == "DATA":
        return "DATE"
    ml = p["max_len"] or 50
    for t in (20, 40, 60, 80, 120, 150, 200, 255):
        if ml <= t:
            return f"VARCHAR({t})"
    return "TEXT"


def relatorio_tabela(cnx, tabela, top=15):
    print(f"[{tabela}]")
    colunas = listar_colunas(cnx, tabela)
    if not colunas:
        print("  tabela nao encontrada\n")
        return None

    with cnx.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS n FROM {tabela}")
        total_linhas = inteiro(cur.fetchone()["n"])

    uteis = [c for c in colunas if not c["COLUMN_NAME"].startswith("_")]
    print(f"  {len(uteis)} colunas | {total_linhas:,} linhas")

    resultado = OrderedDict()
    for i, col in enumerate(uteis, 1):
        nome = col["COLUMN_NAME"]
        try:
            p = perfilar_coluna(cnx, tabela, nome, top)
            classe, obs = classificar(p)
            p["classe"] = classe
            p["observacao"] = obs
            p["tipo_sugerido"] = tipo_mysql(p, classe)
            resultado[nome] = p
            marca = "  <<<" if classe in ("MISTO", "VAZIO") else ""
            print(f"  {i:3d}/{len(uteis)}  {nome:<34} {classe}{marca}")
        except Exception as e:
            print(f"  {i:3d}/{len(uteis)}  {nome:<34} ERRO: {e}")

    print()
    return {"tabela": tabela, "total_linhas": total_linhas, "colunas": resultado}


def gravar_txt(dados, top=15):
    tabela = dados["tabela"]
    caminho = os.path.join(SAIDA, f"perfil_{tabela}.txt")

    with open(caminho, "w", encoding="utf-8") as f:
        f.write("=" * 78 + "\n")
        f.write(f"PERFIL DA TABELA: {tabela}\n")
        f.write(f"Linhas: {dados['total_linhas']:,}\n")
        f.write(f"Gerado em: {datetime.now():%d/%m/%Y %H:%M}\n")
        f.write("=" * 78 + "\n\n")

        f.write("RESUMO POR CLASSE\n")
        f.write("-" * 78 + "\n")
        contagem = {}
        for nome, p in dados["colunas"].items():
            contagem[p["classe"]] = contagem.get(p["classe"], 0) + 1
        for cl, qt in sorted(contagem.items()):
            f.write(f"  {cl:<12} {qt:>3} colunas\n")
        f.write("\n")

        alertas = [(n, p) for n, p in dados["colunas"].items()
                   if p["classe"] in ("MISTO", "VAZIO")]
        if alertas:
            f.write("ATENCAO - CAMPOS QUE EXIGEM DECISAO\n")
            f.write("-" * 78 + "\n")
            for nome, p in alertas:
                f.write(f"  {nome:<34} {p['classe']:<10} {p['observacao']}\n")
            f.write("\n")

        f.write("=" * 78 + "\n")
        f.write("DETALHE POR COLUNA\n")
        f.write("=" * 78 + "\n\n")

        for nome, p in dados["colunas"].items():
            total = p["total"]
            preenchidos = total - p["nulos"] - p["vazios"]
            f.write(f"{nome}\n")
            f.write("-" * len(nome) + "\n")
            f.write(f"  classe ........... {p['classe']}\n")
            f.write(f"  tipo sugerido .... {p['tipo_sugerido']}\n")
            f.write(f"  observacao ....... {p['observacao']}\n")
            f.write(f"  preenchidos ...... {preenchidos:,} de {total:,}\n")
            f.write(f"  nulos / vazios ... {p['nulos']:,} / {p['vazios']:,}\n")
            if p["menos3"]:
                f.write(f"  valores '-3' ..... {p['menos3']:,}\n")
            f.write(f"  distintos ........ {p['distintos']:,}\n")
            f.write(f"  tamanho max/med .. {p['max_len']} / {p['avg_len']}\n")
            if preenchidos > 0:
                f.write(f"  inteiros ......... {p['q_int']:,} "
                        f"({p['q_int']/preenchidos*100:.1f}%)\n")
                f.write(f"  datas ............ {p['q_data_br']:,} "
                        f"({p['q_data_br']/preenchidos*100:.1f}%)\n")
            f.write(f"  top {top} valores:\n")
            for v in p["top_valores"]:
                val = str(v["valor"])[:55]
                f.write(f"      {val:<57} {v['qtd']:>9,}\n")
            f.write("\n")

    print(f"  -> {os.path.basename(caminho)}")
    return caminho


def gravar_markdown(todos):
    caminho = os.path.join(SAIDA, "perfil_completo.md")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("# Perfil das Tabelas de Staging\n\n")
        f.write(f"Gerado em {datetime.now():%d/%m/%Y %H:%M}\n\n")

        f.write("## Campos que exigem decisao\n\n")
        f.write("| Tabela | Coluna | Classe | Observacao |\n")
        f.write("|---|---|---|---|\n")
        achou = False
        for d in todos:
            if not d:
                continue
            for nome, p in d["colunas"].items():
                if p["classe"] in ("MISTO", "VAZIO"):
                    f.write(f"| {d['tabela']} | {nome} | {p['classe']} | "
                            f"{p['observacao']} |\n")
                    achou = True
        if not achou:
            f.write("| - | - | - | nenhum |\n")
        f.write("\n")

        for d in todos:
            if not d:
                continue
            f.write(f"## {d['tabela']}\n\n")
            f.write(f"{d['total_linhas']:,} linhas\n\n")
            f.write("| Coluna | Classe | Tipo sugerido | Distintos | "
                    "Preenchidos | Exemplo |\n")
            f.write("|---|---|---|---:|---:|---|\n")
            for nome, p in d["colunas"].items():
                preenchidos = p["total"] - p["nulos"] - p["vazios"]
                ex = ""
                if p["top_valores"]:
                    ex = str(p["top_valores"][0]["valor"])[:28].replace("|", "/")
                f.write(f"| {nome} | {p['classe']} | {p['tipo_sugerido']} | "
                        f"{p['distintos']:,} | {preenchidos:,} | {ex} |\n")
            f.write("\n")

    print(f"\n-> {os.path.basename(caminho)}")
    return caminho


def gravar_ddl(todos):
    caminho = os.path.join(SAIDA, "tipos_sugeridos.sql")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("-- =================================================\n")
        f.write("-- TIPOS SUGERIDOS A PARTIR DO PERFILAMENTO REAL\n")
        f.write(f"-- Gerado em {datetime.now():%d/%m/%Y %H:%M}\n")
        f.write("-- Revise antes de aplicar.\n")
        f.write("-- =================================================\n\n")
        for d in todos:
            if not d:
                continue
            f.write(f"-- {d['tabela']}  ({d['total_linhas']:,} linhas)\n")
            f.write(f"CREATE TABLE {d['tabela'].replace('stg_', 'norm_')} (\n")
            linhas = []
            for nome, p in d["colunas"].items():
                if p["classe"] == "VAZIO":
                    linhas.append(f"    -- {nome:<34} descartado (campo vazio)")
                    continue
                comentario = ""
                if p["classe"] in ("MISTO", "CATEGORIA"):
                    comentario = f"  -- {p['observacao']}"
                linhas.append(
                    f"    {nome:<34} {p['tipo_sugerido']:<16} NULL,{comentario}")
            f.write("\n".join(linhas).rstrip(","))
            f.write("\n) ENGINE=InnoDB;\n\n")
    print(f"-> {os.path.basename(caminho)}")
    return caminho


def main():
    ap = argparse.ArgumentParser(description="Perfilamento das tabelas staging")
    ap.add_argument("--tabela", help="perfila apenas uma tabela")
    ap.add_argument("--top", type=int, default=15,
                    help="quantidade de valores mais frequentes (padrao 15)")
    args = ap.parse_args()

    print("=" * 70)
    print("  PERFILAMENTO DAS TABELAS STAGING")
    print("=" * 70 + "\n")

    cnx = conectar()
    tabelas = [args.tabela] if args.tabela else TABELAS_PADRAO

    todos = []
    for t in tabelas:
        d = relatorio_tabela(cnx, t, args.top)
        if d:
            gravar_txt(d, args.top)
            todos.append(d)

    cnx.close()

    if todos:
        gravar_markdown(todos)
        gravar_ddl(todos)

    print("\n" + "=" * 70)
    print("  CAMPOS QUE EXIGEM DECISAO")
    print("=" * 70)
    achou = False
    for d in todos:
        for nome, p in d["colunas"].items():
            if p["classe"] in ("MISTO", "VAZIO"):
                print(f"  {d['tabela']:<18} {nome:<34} "
                      f"{p['classe']:<10} {p['observacao']}")
                achou = True
    if not achou:
        print("  nenhum")

    print("\n" + "=" * 70)
    print(f"  Relatorios em: {SAIDA}")
    print("=" * 70)


if __name__ == "__main__":
    main()
