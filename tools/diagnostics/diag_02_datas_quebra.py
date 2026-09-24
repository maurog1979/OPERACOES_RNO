# -*- coding: utf-8 -*-
"""
=====================================================================
PORTAL OPERACOES RNO - DATA MART DESCONEXAO
diag_02_datas_quebra.py - Investiga o 87% dos campos de data
=====================================================================

PROBLEMA
  Todos os campos de data da stg_quebra param em ~87%:
      DH_GERACAO_ARQUIVO  87%
      DATA_INSTALACAO     87%
      DT_AGENDA           87%   <- campo-chave do indicador
      DT_ABERTURA_OS      87%
      DATA_BAIXA_OS       88%
      DH_REAGENDA         86%

  O percentual identico indica causa sistematica, nao ruido.
  Sao aproximadamente 23.800 linhas com formato diferente.

  A stg_quebra_compl tem as datas 100% limpas. So a QUEBRA falha.

ESTE SCRIPT DESCOBRE
  1. Qual mes/arquivo concentra o problema
  2. Como sao os valores que nao batem com o padrao dd/mm/aaaa
  3. Se ha outro formato de data (ISO, com hora, etc)
  4. Se o problema afeta o calculo do indicador de quebra
  5. Amostra de linhas completas para inspecao

NAO ALTERA NADA. Apenas leitura.

USO
    python diag_02_datas_quebra.py
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
    from etl_config import DB
except ImportError:
    DB = {
        "host": "127.0.0.1", "port": 3306, "user": "root",
        "password": "", "database": "desconexao_rno", "charset": "utf8mb4",
    }

SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagnostico")
os.makedirs(SAIDA, exist_ok=True)
ARQ = os.path.join(SAIDA, "datas_quebra.txt")

RE_BR   = r"^[0-9]{2}/[0-9]{2}/[0-9]{4}"
RE_BR2  = r"^[0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}"
RE_ISO  = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}"
RE_NUM  = r"^-?[0-9]+$"


def num(v):
    if v is None:
        return 0
    if isinstance(v, Decimal):
        return int(v)
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def conectar():
    try:
        return pymysql.connect(
            host=DB["host"], port=DB["port"], user=DB["user"],
            password=DB["password"], database=DB["database"],
            charset=DB["charset"], cursorclass=pymysql.cursors.DictCursor,
        )
    except Exception as e:
        sys.exit(f"ERRO de conexao: {e}")


def secao(f, titulo):
    linha = "=" * 74
    for destino in (sys.stdout, f):
        print(linha, file=destino)
        print(f"  {titulo}", file=destino)
        print(linha, file=destino)


def imprimir(f, texto=""):
    print(texto)
    print(texto, file=f)


def main():
    cnx = conectar()
    f = open(ARQ, "w", encoding="utf-8")

    imprimir(f, "INVESTIGACAO DOS CAMPOS DE DATA - stg_quebra")
    imprimir(f, f"Gerado em {datetime.now():%d/%m/%Y %H:%M}")
    imprimir(f)

    with cnx.cursor() as cur:

        # =============================================================
        # 1 - DISTRIBUICAO POR MES
        # =============================================================
        secao(f, "1. DT_AGENDA POR MES DE REFERENCIA")

        cur.execute(f"""
            SELECT _MES_REFERENCIA AS mes,
                   COUNT(*)                                        AS total,
                   SUM(TRIM(DT_AGENDA) REGEXP '{RE_BR}')           AS fmt_br,
                   SUM(TRIM(DT_AGENDA) REGEXP '{RE_ISO}')          AS fmt_iso,
                   SUM(TRIM(DT_AGENDA) REGEXP '{RE_NUM}')          AS so_numero,
                   SUM(DT_AGENDA IS NULL OR TRIM(DT_AGENDA) = '')  AS vazio
            FROM stg_quebra
            GROUP BY _MES_REFERENCIA
            ORDER BY _MES_REFERENCIA
        """)
        imprimir(f, f"{'MES':<10}{'TOTAL':>10}{'dd/mm/aaaa':>13}"
                    f"{'ISO':>8}{'so num':>9}{'vazio':>8}{'% OK':>8}")
        imprimir(f, "-" * 74)
        for r in cur.fetchall():
            t = num(r["total"])
            br = num(r["fmt_br"])
            pct = br / t * 100 if t else 0
            marca = "  <<<" if pct < 95 else ""
            imprimir(f, f"{r['mes']:<10}{t:>10,}{br:>13,}"
                        f"{num(r['fmt_iso']):>8,}{num(r['so_numero']):>9,}"
                        f"{num(r['vazio']):>8,}{pct:>7.1f}%{marca}")
        imprimir(f)

        # =============================================================
        # 2 - VALORES QUE NAO SAO DATA
        # =============================================================
        secao(f, "2. VALORES DE DT_AGENDA FORA DO PADRAO dd/mm/aaaa")

        cur.execute(f"""
            SELECT TRIM(DT_AGENDA) AS valor,
                   CHAR_LENGTH(TRIM(DT_AGENDA)) AS tam,
                   COUNT(*) AS qtd,
                   MIN(_MES_REFERENCIA) AS mes_min,
                   MAX(_MES_REFERENCIA) AS mes_max
            FROM stg_quebra
            WHERE TRIM(DT_AGENDA) NOT REGEXP '{RE_BR}'
              AND DT_AGENDA IS NOT NULL
              AND TRIM(DT_AGENDA) <> ''
            GROUP BY TRIM(DT_AGENDA), CHAR_LENGTH(TRIM(DT_AGENDA))
            ORDER BY qtd DESC
            LIMIT 25
        """)
        linhas = cur.fetchall()
        if linhas:
            imprimir(f, f"{'VALOR':<34}{'TAM':>5}{'QTD':>10}   PERIODO")
            imprimir(f, "-" * 74)
            for r in linhas:
                v = str(r["valor"])[:32]
                per = (r["mes_min"] if r["mes_min"] == r["mes_max"]
                       else f"{r['mes_min']}..{r['mes_max']}")
                imprimir(f, f"{v:<34}{num(r['tam']):>5}"
                            f"{num(r['qtd']):>10,}   {per}")
        else:
            imprimir(f, "nenhum valor fora do padrao")
        imprimir(f)

        # =============================================================
        # 3 - VERIFICA SE O FORMATO E dd/mm/aa (ano com 2 digitos)
        # =============================================================
        secao(f, "3. TESTE DE FORMATO ALTERNATIVO")

        cur.execute(f"""
            SELECT
                COUNT(*)                                       AS total,
                SUM(TRIM(DT_AGENDA) REGEXP '{RE_BR}')          AS ano4,
                SUM(TRIM(DT_AGENDA) REGEXP '{RE_BR2}'
                    AND TRIM(DT_AGENDA) NOT REGEXP '{RE_BR}')  AS outro_br,
                SUM(TRIM(DT_AGENDA) LIKE '%/%')                AS tem_barra,
                SUM(TRIM(DT_AGENDA) LIKE '%-%')                AS tem_hifen,
                SUM(TRIM(DT_AGENDA) LIKE '% %')                AS tem_espaco
            FROM stg_quebra
            WHERE DT_AGENDA IS NOT NULL AND TRIM(DT_AGENDA) <> ''
        """)
        r = cur.fetchone()
        t = num(r["total"])
        imprimir(f, f"  preenchidos ............. {t:,}")
        imprimir(f, f"  dd/mm/aaaa .............. {num(r['ano4']):,}")
        imprimir(f, f"  outro formato com barra . {num(r['outro_br']):,}")
        imprimir(f, f"  contem barra ............ {num(r['tem_barra']):,}")
        imprimir(f, f"  contem hifen ............ {num(r['tem_hifen']):,}")
        imprimir(f, f"  contem espaco ........... {num(r['tem_espaco']):,}")
        imprimir(f)

        # =============================================================
        # 4 - IMPACTO NO INDICADOR
        # =============================================================
        secao(f, "4. IMPACTO NO INDICADOR DE QUEBRA")

        cur.execute(f"""
            SELECT _MES_REFERENCIA AS mes,
                   COUNT(*) AS total,
                   SUM(NM_TIPO_TRATAMENTO = 'COM QUEBRA DE AGENDA') AS com_quebra,
                   SUM(TRIM(DT_AGENDA) NOT REGEXP '{RE_BR}'
                       AND TRIM(DT_AGENDA) <> ''
                       AND DT_AGENDA IS NOT NULL) AS data_ruim
            FROM stg_quebra
            GROUP BY _MES_REFERENCIA
            ORDER BY _MES_REFERENCIA
        """)
        imprimir(f, f"{'MES':<10}{'TOTAL':>10}{'C/QUEBRA':>11}"
                    f"{'% QUEBRA':>11}{'DATA RUIM':>12}")
        imprimir(f, "-" * 74)
        for r in cur.fetchall():
            t = num(r["total"])
            cq = num(r["com_quebra"])
            pct = cq / t * 100 if t else 0
            imprimir(f, f"{r['mes']:<10}{t:>10,}{cq:>11,}"
                        f"{pct:>10.2f}%{num(r['data_ruim']):>12,}")
        imprimir(f)
        imprimir(f, "  Referencia de aceite: 2026-08 deve dar 63,14%")
        imprimir(f, "  (12.934 com quebra de 20.484 total)")
        imprimir(f)

        # =============================================================
        # 5 - AMOSTRA DE LINHAS PROBLEMATICAS
        # =============================================================
        secao(f, "5. AMOSTRA DE LINHAS COM DT_AGENDA FORA DO PADRAO")

        cur.execute(f"""
            SELECT _ARQUIVO_ORIGEM, _LINHA_ARQUIVO,
                   NR_ORDEM_SERVICO, NR_CONTRATO, CD_OPERADORA,
                   STATUS_OS, DT_AGENDA, DT_AGENDA_DIA, DT_AGENDA_MES,
                   NM_TIPO_TRATAMENTO, NM_CIDADE
            FROM stg_quebra
            WHERE TRIM(DT_AGENDA) NOT REGEXP '{RE_BR}'
              AND DT_AGENDA IS NOT NULL
              AND TRIM(DT_AGENDA) <> ''
            LIMIT 8
        """)
        for i, r in enumerate(cur.fetchall(), 1):
            imprimir(f, f"  [{i}] arquivo={r['_ARQUIVO_ORIGEM']} "
                        f"linha={r['_LINHA_ARQUIVO']}")
            imprimir(f, f"      OS={r['NR_ORDEM_SERVICO']}  "
                        f"CONTRATO={r['NR_CONTRATO']}  "
                        f"OPER={r['CD_OPERADORA']}")
            imprimir(f, f"      DT_AGENDA='{r['DT_AGENDA']}'  "
                        f"DIA={r['DT_AGENDA_DIA']}  MES={r['DT_AGENDA_MES']}")
            imprimir(f, f"      STATUS={r['STATUS_OS']}  "
                        f"TRATAMENTO={r['NM_TIPO_TRATAMENTO']}  "
                        f"CIDADE={r['NM_CIDADE']}")
            imprimir(f)

        # =============================================================
        # 6 - AMOSTRA DE LINHAS NORMAIS
        # =============================================================
        secao(f, "6. AMOSTRA DE LINHAS NORMAIS (comparacao)")

        cur.execute(f"""
            SELECT _ARQUIVO_ORIGEM, NR_ORDEM_SERVICO, NR_CONTRATO,
                   DT_AGENDA, DT_AGENDA_DIA, DT_AGENDA_MES,
                   STATUS_OS, NM_TIPO_TRATAMENTO
            FROM stg_quebra
            WHERE TRIM(DT_AGENDA) REGEXP '{RE_BR}'
            LIMIT 5
        """)
        for i, r in enumerate(cur.fetchall(), 1):
            imprimir(f, f"  [{i}] {r['_ARQUIVO_ORIGEM']}  "
                        f"OS={r['NR_ORDEM_SERVICO']}")
            imprimir(f, f"      DT_AGENDA='{r['DT_AGENDA']}'  "
                        f"DIA={r['DT_AGENDA_DIA']}  MES={r['DT_AGENDA_MES']}  "
                        f"{r['NM_TIPO_TRATAMENTO']}")
        imprimir(f)

        # =============================================================
        # 7 - O SENTINELA -3
        # =============================================================
        secao(f, "7. CAMPOS COM SENTINELA '-3' (nao informado)")

        campos = [
            ("stg_quebra_compl", "DSC_CANAL_VENDA"),
            ("stg_quebra_compl", "DSC_CANAL_VENDA_GRUPO"),
            ("stg_quebra_compl", "DSC_CANAL_VENDA_SUBGRUPO"),
            ("stg_quebra_compl", "LOGIN_VENDEDOR"),
            ("stg_quebra_compl", "DSC_PARCEIRO_VENDA"),
            ("stg_quebra_compl", "DSC_AREA_RESP_MOTIVO_BI"),
            ("stg_quebra_compl", "DSC_QUEBRA_CENARIO"),
            ("stg_quebra_compl", "COD_LOGIN_DESPACHO_OS"),
        ]
        imprimir(f, f"{'CAMPO':<34}{'TOTAL':>11}{'= -3':>11}{'% -3':>9}")
        imprimir(f, "-" * 74)
        for tab, col in campos:
            cur.execute(f"""
                SELECT COUNT(*) AS total,
                       SUM(TRIM(`{col}`) = '-3') AS m3
                FROM {tab}
            """)
            r = cur.fetchone()
            t = num(r["total"])
            m3 = num(r["m3"])
            pct = m3 / t * 100 if t else 0
            marca = "  <<< inutil" if pct > 95 else ""
            imprimir(f, f"{col:<34}{t:>11,}{m3:>11,}{pct:>8.1f}%{marca}")
        imprimir(f)

        # =============================================================
        # 8 - DT_AGENDA_DIA e DT_AGENDA_MES COMO ALTERNATIVA
        # =============================================================
        secao(f, "8. ALTERNATIVA: RECONSTRUIR A DATA PELOS CAMPOS DIA/MES")

        cur.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(DT_AGENDA_DIA IS NOT NULL
                    AND TRIM(DT_AGENDA_DIA) <> '')  AS tem_dia,
                SUM(DT_AGENDA_MES IS NOT NULL
                    AND TRIM(DT_AGENDA_MES) <> '')  AS tem_mes
            FROM stg_quebra
        """)
        r = cur.fetchone()
        t = num(r["total"])
        imprimir(f, f"  total .............. {t:,}")
        imprimir(f, f"  com DT_AGENDA_DIA .. {num(r['tem_dia']):,}")
        imprimir(f, f"  com DT_AGENDA_MES .. {num(r['tem_mes']):,}")
        imprimir(f)
        imprimir(f, "  Se DIA e MES estiverem completos, a data pode ser")
        imprimir(f, "  reconstruida combinando com _MES_REFERENCIA.")
        imprimir(f)

    cnx.close()
    f.close()

    print("=" * 74)
    print(f"  Relatorio salvo em: {ARQ}")
    print("=" * 74)


if __name__ == "__main__":
    main()
