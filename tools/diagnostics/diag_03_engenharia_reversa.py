# -*- coding: utf-8 -*-
"""
=====================================================================
PORTAL OPERACOES RNO
diag_03_engenharia_reversa.py
Deduz as regras do enriquecimento da safra_enriquecida
=====================================================================

CONTEXTO
  O script que gerou a tabela safra_enriquecida nao existe mais.
  Precisamos reconstruir as regras de negocio dos campos derivados
  para aplica-las ao novo fato ft_safra_historico.

CAMPOS A DECIFRAR
  FAIXA_LOG           SEM LOG | 1x | 2-3x | 4-5x | 6x+
  SITUACAO_AGENDA     EXECUTADA | COM QUEBRA | SEM ANALITICO
  PARCEIRA_NOME       normalizacao das variacoes do nome
  TEM_BACKLOG         SIM | NAO
  TEM_TOA             SIM | NAO
  TEM_ANALITICO       SIM | NAO
  TEM_QAD             SIM | NAO
  PENDENCIA           RECUPERADO | PENDENTE   (texto, nao 0/1)

ESTRATEGIA
  1. Perfila cada campo derivado
  2. Cruza com os campos de origem para inferir a formula
  3. Testa hipoteses e mede a taxa de acerto
  4. Gera um relatorio com as regras deduzidas

NAO ALTERA NADA. Apenas leitura.

USO
    python diag_03_engenharia_reversa.py
=====================================================================
"""

import os
import sys
from decimal import Decimal
from datetime import datetime

try:
    import pymysql
except ImportError:
    sys.exit("ERRO: pymysql nao instalado.  Execute:  pip install pymysql")

try:
    from config import Config
    DB_LEGADO = Config.db_config_pymysql()
except Exception:
    DB_LEGADO = {
        "host": "127.0.0.1", "port": 3306, "user": "root",
        "password": "", "database": "safra", "charset": "utf8mb4",
    }

SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagnostico")
os.makedirs(SAIDA, exist_ok=True)
ARQ = os.path.join(SAIDA, "engenharia_reversa.txt")

_f = None


def num(v):
    if v is None:
        return 0
    if isinstance(v, Decimal):
        return int(v)
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def p(txt=""):
    print(txt)
    if _f:
        _f.write(txt + "\n")


def titulo(t):
    p("=" * 74)
    p(f"  {t}")
    p("=" * 74)


def conectar():
    try:
        return pymysql.connect(
            **DB_LEGADO, cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        sys.exit(f"ERRO de conexao ao banco legado: {e}")


def q(cur, sql):
    cur.execute(sql)
    return cur.fetchall()


def main():
    global _f
    _f = open(ARQ, "w", encoding="utf-8")

    cnx = conectar()
    cur = cnx.cursor()

    p("ENGENHARIA REVERSA DO ENRIQUECIMENTO")
    p(f"Banco: {DB_LEGADO['database']}")
    p(f"Gerado em {datetime.now():%d/%m/%Y %H:%M}")
    p()

    # =================================================================
    # 1 - ESTRUTURA DA TABELA
    # =================================================================
    titulo("1. COLUNAS DA safra_enriquecida")

    cols = q(cur, f"""
        SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = '{DB_LEGADO['database']}'
          AND TABLE_NAME = 'safra_enriquecida'
        ORDER BY ORDINAL_POSITION
    """)

    if not cols:
        p("  TABELA NAO ENCONTRADA")
        p("  Verifique o nome do banco em config.py")
        _f.close()
        return

    p(f"  {len(cols)} colunas")
    p()
    nomes = [c["COLUMN_NAME"] for c in cols]
    for i, c in enumerate(cols, 1):
        tam = f"({c['CHARACTER_MAXIMUM_LENGTH']})" if c["CHARACTER_MAXIMUM_LENGTH"] else ""
        p(f"  {i:3d}  {c['COLUMN_NAME']:<32} {c['DATA_TYPE']}{tam}")
    p()

    total = num(q(cur, "SELECT COUNT(*) AS n FROM safra_enriquecida")[0]["n"])
    p(f"  total de linhas: {total:,}")
    p()

    # =================================================================
    # 2 - VALORES DOS CAMPOS DERIVADOS
    # =================================================================
    titulo("2. VALORES DOS CAMPOS DERIVADOS")

    derivados = [
        "FAIXA_LOG", "SITUACAO_AGENDA", "PENDENCIA",
        "TEM_BACKLOG", "TEM_TOA", "TEM_ANALITICO", "TEM_QAD",
        "STATUS_OPERACIONAL", "PARCEIRA_NOME",
    ]

    for campo in derivados:
        if campo not in nomes:
            p(f"  {campo:<24} nao existe na tabela")
            continue

        rows = q(cur, f"""
            SELECT `{campo}` AS v, COUNT(*) AS n
            FROM safra_enriquecida
            GROUP BY `{campo}`
            ORDER BY n DESC
            LIMIT 25
        """)
        p(f"  {campo}")
        p("  " + "-" * 60)
        for r in rows:
            val = str(r["v"])[:40] if r["v"] is not None else "(nulo)"
            pct = num(r["n"]) / total * 100 if total else 0
            p(f"      {val:<42} {num(r['n']):>8,}  {pct:5.1f}%")
        p()

    # =================================================================
    # 3 - FAIXA_LOG vs CAMPOS DE ORIGEM
    # =================================================================
    titulo("3. DEDUZINDO A REGRA DO FAIXA_LOG")

    if "FAIXA_LOG" in nomes:
        # procura colunas que possam ser a contagem de origem
        candidatos = [c for c in nomes
                      if any(k in c.upper()
                             for k in ["LOG", "QTD", "CONT", "NUM", "TOTAL"])
                      and c != "FAIXA_LOG"]

        p(f"  colunas candidatas a origem: {', '.join(candidatos) or 'nenhuma'}")
        p()

        for cand in candidatos[:6]:
            try:
                rows = q(cur, f"""
                    SELECT FAIXA_LOG,
                           MIN(`{cand}`) AS v_min,
                           MAX(`{cand}`) AS v_max,
                           COUNT(*) AS n
                    FROM safra_enriquecida
                    WHERE FAIXA_LOG IS NOT NULL
                    GROUP BY FAIXA_LOG
                    ORDER BY v_min
                """)
                if rows and any(r["v_min"] is not None for r in rows):
                    p(f"  FAIXA_LOG x {cand}")
                    p("  " + "-" * 60)
                    for r in rows:
                        p(f"      {str(r['FAIXA_LOG']):<16} "
                          f"min={str(r['v_min']):<8} "
                          f"max={str(r['v_max']):<8} "
                          f"n={num(r['n']):>7,}")
                    p()
            except Exception:
                continue
    else:
        p("  FAIXA_LOG nao existe")
        p()

    # =================================================================
    # 4 - SITUACAO_AGENDA vs ORIGEM
    # =================================================================
    titulo("4. DEDUZINDO A REGRA DO SITUACAO_AGENDA")

    if "SITUACAO_AGENDA" in nomes:
        origem = [c for c in nomes
                  if any(k in c.upper()
                         for k in ["STATUS", "TRATAMENTO", "ANALITICO",
                                   "TOA", "AGENDA"])
                  and c != "SITUACAO_AGENDA"]

        p(f"  colunas candidatas: {', '.join(origem[:10])}")
        p()

        for cand in origem[:5]:
            try:
                rows = q(cur, f"""
                    SELECT SITUACAO_AGENDA, `{cand}` AS origem, COUNT(*) AS n
                    FROM safra_enriquecida
                    GROUP BY SITUACAO_AGENDA, `{cand}`
                    HAVING n > 100
                    ORDER BY SITUACAO_AGENDA, n DESC
                    LIMIT 20
                """)
                if rows:
                    p(f"  SITUACAO_AGENDA x {cand}")
                    p("  " + "-" * 60)
                    for r in rows:
                        p(f"      {str(r['SITUACAO_AGENDA']):<20} "
                          f"{str(r['origem'])[:28]:<30} {num(r['n']):>7,}")
                    p()
            except Exception:
                continue
    else:
        p("  SITUACAO_AGENDA nao existe")
        p()

    # =================================================================
    # 5 - PARCEIRA_NOME - O DE-PARA
    # =================================================================
    titulo("5. NORMALIZACAO DE PARCEIRAS (DE-PARA)")

    col_origem = None
    for c in ["PARCEIRA", "TOA_PARCEIRA", "DSC_EMPRESA_EXECUCAO"]:
        if c in nomes:
            col_origem = c
            break

    if "PARCEIRA_NOME" in nomes and col_origem:
        rows = q(cur, f"""
            SELECT `{col_origem}` AS de, PARCEIRA_NOME AS para,
                   COUNT(*) AS n
            FROM safra_enriquecida
            WHERE PARCEIRA_NOME IS NOT NULL
              AND TRIM(PARCEIRA_NOME) <> ''
            GROUP BY `{col_origem}`, PARCEIRA_NOME
            ORDER BY PARCEIRA_NOME, n DESC
        """)
        p(f"  mapeamento {col_origem} -> PARCEIRA_NOME")
        p("  " + "-" * 70)
        atual = None
        for r in rows:
            if r["para"] != atual:
                atual = r["para"]
                p(f"\n  {atual}")
            p(f"      <- {str(r['de'])[:50]:<52} {num(r['n']):>7,}")
        p()
    else:
        p("  PARCEIRA_NOME ou coluna de origem nao encontrada")
        p()

    # =================================================================
    # 6 - FLAGS TEM_*
    # =================================================================
    titulo("6. REGRAS DAS FLAGS TEM_*")

    flags = [c for c in nomes if c.startswith("TEM_")]
    for flag in flags:
        sufixo = flag.replace("TEM_", "")
        relacionadas = [c for c in nomes
                        if sufixo in c.upper() and c != flag]
        if not relacionadas:
            continue

        p(f"  {flag}  (colunas relacionadas: {', '.join(relacionadas[:4])})")
        p("  " + "-" * 60)
        for rel in relacionadas[:3]:
            try:
                rows = q(cur, f"""
                    SELECT `{flag}` AS flag,
                           SUM(`{rel}` IS NULL
                               OR TRIM(`{rel}`) = '') AS vazios,
                           SUM(`{rel}` IS NOT NULL
                               AND TRIM(`{rel}`) <> '') AS preenchidos,
                           COUNT(*) AS n
                    FROM safra_enriquecida
                    GROUP BY `{flag}`
                """)
                p(f"      contra {rel}")
                for r in rows:
                    p(f"          {str(r['flag']):<6} "
                      f"vazios={num(r['vazios']):>7,}  "
                      f"preenchidos={num(r['preenchidos']):>7,}")
            except Exception:
                continue
        p()

    # =================================================================
    # 7 - AMOSTRA COMPLETA
    # =================================================================
    titulo("7. AMOSTRA DE LINHAS")

    principais = [c for c in [
        "CD_NET", "SAFRA", "DS_TIPO_DESCONEXAO", "PENDENCIA",
        "SITUACAO_AGENDA", "FAIXA_LOG", "PARCEIRA_NOME",
        "TEM_BACKLOG", "TEM_TOA", "TEM_ANALITICO",
    ] if c in nomes]

    if principais:
        sel = ", ".join(f"`{c}`" for c in principais)
        rows = q(cur, f"SELECT {sel} FROM safra_enriquecida LIMIT 8")
        for i, r in enumerate(rows, 1):
            p(f"  [{i}]")
            for k, v in r.items():
                p(f"      {k:<24} {v}")
            p()

    # =================================================================
    # 8 - RESUMO PARA A RECONSTRUCAO
    # =================================================================
    titulo("8. CAMPOS A REPLICAR NO ft_safra_historico")

    p("  Campos derivados encontrados:")
    for c in derivados:
        marca = "OK " if c in nomes else "-- "
        p(f"      [{marca}] {c}")
    p()
    p("  Proximo passo:")
    p("    Com as regras deduzidas acima, aplicar os mesmos campos")
    p("    ao ft_safra_historico do banco desconexao_rno.")
    p()

    cur.close()
    cnx.close()
    _f.close()

    print("=" * 74)
    print(f"  Relatorio salvo em: {ARQ}")
    print("=" * 74)


if __name__ == "__main__":
    main()
