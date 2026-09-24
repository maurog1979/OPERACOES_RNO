# -*- coding: utf-8 -*-
"""
=====================================================================
PORTAL OPERACOES RNO - DATA MART DESCONEXAO
Script 02 - ETL de carga do STAGING
=====================================================================

O QUE FAZ
  1. Varre as pastas ENTRADA de cada dominio
  2. Identifica mes/ano pelo nome do arquivo
  3. Le o CSV com deteccao automatica de encoding
  4. Carrega nas tabelas stg_* (espelho fiel, sem conversao)
  5. Grava auditoria em tb_auditoria_carga

REGRAS
  - Dominios mensais (QUEBRA, COMPL, TOA, SAFRA):
        DELETE do mes + INSERT     (recarga idempotente)
  - BACKLOG (arquivo unico diario):
        TRUNCATE stg_backlog + INSERT  (a acumulacao ocorre no fato)
  - METAS:
        TRUNCATE + INSERT

USO
    python etl_02_carga_staging.py                # carrega tudo
    python etl_02_carga_staging.py --dominio QUEBRA
    python etl_02_carga_staging.py --mes 2026-08
    python etl_02_carga_staging.py --dominio SAFRA --mes 2026-08
    python etl_02_carga_staging.py --dry-run      # so analisa, nao grava
=====================================================================
"""

import os
import re
import sys
import time
import logging
import argparse
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    sys.exit("ERRO: pandas nao instalado.  Execute:  pip install pandas openpyxl")

try:
    import pymysql
except ImportError:
    sys.exit("ERRO: pymysql nao instalado.  Execute:  pip install pymysql")

from etl_config import (
    DB, PASTAS, PADRAO, MAPA_COLUNAS,
    MES_INICIO_HISTORICO, CSV_SEP, CSV_ENCODINGS, CHUNK_SIZE,
    LOG_DIR, LOG_NIVEL,
)

# =====================================================================
# LOG
# =====================================================================
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"etl_staging_{datetime.now():%Y%m%d_%H%M%S}.log")

logging.basicConfig(
    level=getattr(logging, LOG_NIVEL),
    format="%(asctime)s [%(levelname)-7s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("ETL")


# =====================================================================
# TABELAS DE DESTINO
# =====================================================================
TABELA = {
    "QUEBRA":       "stg_quebra",
    "QUEBRA_COMPL": "stg_quebra_compl",
    "TOA":          "stg_toa",
    "SAFRA":        "stg_safra",
    "BACKLOG":      "stg_backlog",
    "METAS":        "stg_metas",
}

DOMINIOS_MENSAIS = ["QUEBRA", "QUEBRA_COMPL", "TOA", "SAFRA"]


# =====================================================================
# BANCO
# =====================================================================
def conectar():
    try:
        cnx = pymysql.connect(
            host=DB["host"], port=DB["port"], user=DB["user"],
            password=DB["password"], database=DB["database"],
            charset=DB["charset"], autocommit=False,
            local_infile=True,
        )
        log.info(f"Conectado -> {DB['host']}:{DB['port']}/{DB['database']}")
        return cnx
    except Exception as e:
        log.error(f"Falha na conexao: {e}")
        log.error("Verifique se o MySQL do Laragon esta iniciado.")
        sys.exit(1)


def colunas_da_tabela(cnx, tabela):
    """Retorna lista ordenada de colunas reais da tabela."""
    with cnx.cursor() as cur:
        cur.execute(f"""
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """, (DB["database"], tabela))
        return [r[0] for r in cur.fetchall()]


# =====================================================================
# LEITURA DE ARQUIVO
# =====================================================================
def ler_csv(caminho):
    """Le CSV tentando encodings em cascata. Tudo como string."""
    ultimo_erro = None
    for enc in CSV_ENCODINGS:
        try:
            df = pd.read_csv(
                caminho,
                sep=CSV_SEP,
                dtype=str,
                encoding=enc,
                keep_default_na=False,
                na_values=[],
                on_bad_lines="warn",
                engine="python",
            )
            log.info(f"    encoding detectado: {enc}")
            return df
        except UnicodeDecodeError as e:
            ultimo_erro = e
            continue
        except Exception as e:
            ultimo_erro = e
            continue
    raise RuntimeError(f"Nao foi possivel ler o arquivo. Ultimo erro: {ultimo_erro}")


def ler_xlsx(caminho):
    df = pd.read_excel(caminho, dtype=str, keep_default_na=False)
    log.info("    arquivo XLSX lido")
    return df


def normalizar_cabecalho(txt):
    """Remove BOM, espacos duplicados e espacos nas pontas."""
    if txt is None:
        return ""
    t = str(txt).replace("\ufeff", "").strip()
    t = re.sub(r"\s+", " ", t)
    return t


def aplicar_mapa(df, dominio, cols_destino):
    """
    Renomeia colunas do CSV para os nomes da tabela stg_.
    Estrategia:
      1. normaliza cabecalho
      2. aplica MAPA_COLUNAS do dominio
      3. tenta match direto (case-insensitive)
      4. tenta match ignorando acento e caracteres especiais
    """
    mapa = MAPA_COLUNAS.get(dominio, {})

    # indice auxiliar: nome simplificado -> nome real da tabela
    def simplificar(s):
        s = str(s).upper()
        for a, b in [("Á","A"),("À","A"),("Ã","A"),("Â","A"),
                     ("É","E"),("Ê","E"),("Í","I"),
                     ("Ó","O"),("Õ","O"),("Ô","O"),
                     ("Ú","U"),("Ç","C")]:
            s = s.replace(a, b)
        return re.sub(r"[^A-Z0-9]", "", s)

    idx_destino = {simplificar(c): c for c in cols_destino}

    renomear = {}
    nao_mapeadas = []

    for col in df.columns:
        original = normalizar_cabecalho(col)

        # 1. mapa explicito
        if original in mapa:
            renomear[col] = mapa[original]
            continue

        # 2. match simplificado
        chave = simplificar(original)
        if chave in idx_destino:
            renomear[col] = idx_destino[chave]
            continue

        nao_mapeadas.append(original)

    df = df.rename(columns=renomear)

    if nao_mapeadas:
        log.warning(f"    colunas do arquivo sem destino ({len(nao_mapeadas)}): "
                    f"{', '.join(nao_mapeadas[:8])}"
                    f"{' ...' if len(nao_mapeadas) > 8 else ''}")

    faltando = [c for c in cols_destino
                if not c.startswith("_") and c not in df.columns]
    if faltando:
        log.warning(f"    colunas da tabela ausentes no arquivo ({len(faltando)}): "
                    f"{', '.join(faltando[:8])}"
                    f"{' ...' if len(faltando) > 8 else ''}")
        for c in faltando:
            df[c] = None

    return df


# =====================================================================
# DESCOBERTA DE ARQUIVOS
# =====================================================================
def descobrir(dominio, filtro_mes=None):
    """Retorna lista de (caminho, mes_referencia)."""
    pasta = PASTAS[dominio]
    if not os.path.isdir(pasta):
        log.warning(f"  pasta inexistente: {pasta}")
        return []

    regex = re.compile(PADRAO[dominio], re.IGNORECASE)
    achados = []

    for nome in sorted(os.listdir(pasta)):
        m = regex.match(nome)
        if not m:
            continue

        caminho = os.path.join(pasta, nome)

        if dominio in ("BACKLOG", "METAS"):
            achados.append((caminho, None))
            continue

        mes, ano = m.group(1), m.group(2)
        mes_ref = f"{ano}-{mes}"

        if mes_ref < MES_INICIO_HISTORICO:
            log.info(f"  ignorado (fora da janela): {nome}")
            continue
        if filtro_mes and mes_ref != filtro_mes:
            continue

        achados.append((caminho, mes_ref))

    return achados


# =====================================================================
# CARGA
# =====================================================================
def inserir(cnx, tabela, df, cols_destino):
    """Insere em lotes. Retorna total inserido."""
    cols = [c for c in cols_destino if c in df.columns]
    df = df[cols].where(pd.notnull(df), None)

    # normaliza strings vazias para NULL
    df = df.replace({"": None})

    placeholders = ", ".join(["%s"] * len(cols))
    col_list = ", ".join(f"`{c}`" for c in cols)
    sql = f"INSERT INTO {tabela} ({col_list}) VALUES ({placeholders})"

    total = 0
    registros = df.values.tolist()

    with cnx.cursor() as cur:
        for i in range(0, len(registros), CHUNK_SIZE):
            lote = registros[i:i + CHUNK_SIZE]
            cur.executemany(sql, lote)
            total += len(lote)
            log.info(f"    inseridas {total:,} de {len(registros):,} linhas")

    return total


def auditar(cnx, dominio, arquivo, mes_ref, lidos, inseridos,
            t0, status, msg=None):
    with cnx.cursor() as cur:
        cur.execute("""
            INSERT INTO tb_auditoria_carga
                (DT_INICIO, DT_FIM, DOMINIO, ARQUIVO, MES_REFERENCIA,
                 REGISTROS_LIDOS, REGISTROS_INSERIDOS, REGISTROS_REJEITADOS,
                 TEMPO_PROCESSAMENTO_SEG, STATUS, MENSAGEM)
            VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            datetime.fromtimestamp(t0), dominio, os.path.basename(arquivo),
            mes_ref, lidos, inseridos, max(0, lidos - inseridos),
            int(time.time() - t0), status, msg,
        ))


def processar(cnx, dominio, caminho, mes_ref, dry_run=False):
    t0 = time.time()
    tabela = TABELA[dominio]
    nome = os.path.basename(caminho)

    log.info(f"  -> {nome}" + (f"  [{mes_ref}]" if mes_ref else ""))

    try:
        df = ler_xlsx(caminho) if caminho.lower().endswith(".xlsx") else ler_csv(caminho)
        lidos = len(df)
        log.info(f"    linhas lidas: {lidos:,}  |  colunas: {len(df.columns)}")

        if lidos == 0:
            log.warning("    arquivo vazio - ignorado")
            return 0

        cols_destino = colunas_da_tabela(cnx, tabela)
        df = aplicar_mapa(df, dominio, cols_destino)

        # colunas de controle
        df["_ARQUIVO_ORIGEM"] = nome
        df["_LINHA_ARQUIVO"] = range(1, len(df) + 1)

        if dominio == "BACKLOG":
            # data da foto vem de dentro do arquivo
            if "DT_RELATORIO" in df.columns and df["DT_RELATORIO"].notna().any():
                amostra = df["DT_RELATORIO"].dropna().iloc[0]
                dt = pd.to_datetime(amostra, dayfirst=True, errors="coerce")
                df["_DT_POSICAO"] = dt.date() if pd.notna(dt) else datetime.now().date()
                log.info(f"    DT_POSICAO (do arquivo): {df['_DT_POSICAO'].iloc[0]}")
            else:
                df["_DT_POSICAO"] = datetime.now().date()
                log.warning("    DT_RELATORIO ausente - usando data de hoje")
        elif mes_ref:
            df["_MES_REFERENCIA"] = mes_ref

        if dry_run:
            log.info("    [DRY-RUN] nada gravado")
            return lidos

        # limpeza antes do insert
        with cnx.cursor() as cur:
            if dominio in DOMINIOS_MENSAIS:
                cur.execute(f"DELETE FROM {tabela} WHERE _MES_REFERENCIA = %s", (mes_ref,))
                if cur.rowcount:
                    log.info(f"    removidas {cur.rowcount:,} linhas anteriores do mes")
            else:
                cur.execute(f"TRUNCATE TABLE {tabela}")
                log.info("    staging truncada")

        inseridos = inserir(cnx, tabela, df, cols_destino)
        auditar(cnx, dominio, caminho, mes_ref, lidos, inseridos, t0, "OK")
        cnx.commit()

        log.info(f"    OK - {inseridos:,} linhas em {time.time() - t0:.1f}s")
        return inseridos

    except Exception as e:
        cnx.rollback()
        log.error(f"    FALHA: {e}")
        try:
            auditar(cnx, dominio, caminho, mes_ref, 0, 0, t0, "ERRO", str(e)[:1000])
            cnx.commit()
        except Exception:
            pass
        return 0


# =====================================================================
# MAIN
# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="ETL de carga do staging")
    ap.add_argument("--dominio", choices=list(TABELA.keys()),
                    help="carrega apenas um dominio")
    ap.add_argument("--mes", help="filtra mes especifico (ex: 2026-08)")
    ap.add_argument("--dry-run", action="store_true",
                    help="analisa sem gravar no banco")
    args = ap.parse_args()

    print("=" * 70)
    print("  ETL STAGING - DATA MART DESCONEXAO RNO")
    print("=" * 70)
    if args.dry_run:
        print("  MODO DRY-RUN - nenhuma alteracao sera gravada")
        print("=" * 70)

    cnx = conectar()
    dominios = [args.dominio] if args.dominio else list(TABELA.keys())

    resumo = {}
    t_inicio = time.time()

    for dom in dominios:
        log.info("")
        log.info(f"[{dom}]")

        arquivos = descobrir(dom, args.mes)
        if not arquivos:
            log.warning("  nenhum arquivo encontrado")
            resumo[dom] = 0
            continue

        log.info(f"  {len(arquivos)} arquivo(s) encontrado(s)")
        total = 0
        for caminho, mes_ref in arquivos:
            total += processar(cnx, dom, caminho, mes_ref, args.dry_run)
        resumo[dom] = total

    cnx.close()

    print()
    print("=" * 70)
    print("  RESUMO")
    print("=" * 70)
    for dom, qtd in resumo.items():
        print(f"  {dom:<15} {qtd:>12,} linhas")
    print("-" * 70)
    print(f"  {'TOTAL':<15} {sum(resumo.values()):>12,} linhas")
    print(f"  Tempo total: {time.time() - t_inicio:.1f}s")
    print(f"  Log: {LOG_FILE}")
    print("=" * 70)


if __name__ == "__main__":
    main()
