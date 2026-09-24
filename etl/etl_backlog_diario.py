# -*- coding: utf-8 -*-
"""
=====================================================================
PORTAL OPERACOES RNO - DATA MART DESCONEXAO
etl_backlog_diario.py - Carga diaria do Backlog
=====================================================================

POR QUE ESTE SCRIPT EXISTE
  O arquivo BACKLOG_OS.csv e SOBRESCRITO todos os dias.
  Se ninguem rodar a carga naquele dia, a foto se perde para sempre.

  Este script roda automaticamente as 10h05 (via Agendador de Tarefas
  do Windows) e acumula cada foto no ft_backlog_log, formando o
  historico de movimentacao:

      15/09  AGENDADO     -> agenda para 18/09
      18/09  SEM AGENDA   -> motivo: 106 CLIENTE AUSENTE
      20/09  AGENDADO     -> agenda para 21/09

O QUE FAZ
  1. Le o BACKLOG_OS.csv da pasta ENTRADA
  2. Extrai a data da foto do campo DT_RELATORIO
  3. Verifica se essa data ja foi carregada (evita duplicar)
  4. Carrega no staging
  5. Normaliza e insere no ft_backlog_log (INSERT IGNORE)
  6. Regenera o ft_backlog_atual (ultima posicao por contrato)
  7. Grava auditoria e envia resumo no log

PROTECOES
  - Nao duplica se rodar duas vezes no mesmo dia
  - Nao falha se o arquivo nao existir (registra e sai)
  - Transacao por etapa, com rollback em erro
  - Log em arquivo, para conferir depois

USO MANUAL
    python etl_backlog_diario.py
    python etl_backlog_diario.py --forcar     recarrega mesmo se ja existe
    python etl_backlog_diario.py --dry-run    simula sem gravar

USO AUTOMATICO
    Via agendar_backlog.bat, registrado no Agendador de Tarefas
=====================================================================
"""

import os
import re
import sys
import time
import argparse
from datetime import datetime, date

try:
    import pandas as pd
except ImportError:
    sys.exit("ERRO: pandas nao instalado.  Execute:  pip install pandas")

try:
    import pymysql
except ImportError:
    sys.exit("ERRO: pymysql nao instalado.  Execute:  pip install pymysql")

# ---------------------------------------------------------------------
# CONFIGURACAO
# ---------------------------------------------------------------------
try:
    from etl_config import DB, PASTAS, CSV_SEP, CSV_ENCODINGS
except ImportError:
    DB = {
        "host": "127.0.0.1", "port": 3306, "user": "root",
        "password": "", "database": "desconexao_rno", "charset": "utf8mb4",
    }
    PASTAS = {
        "BACKLOG": r"C:\Users\n5996917\OneDrive - Claro SA\OPERAÇÕES"
                   r"\ADM\DESCONEXAO\ANALITICOS\BACKLOG_OS\ENTRADA",
    }
    CSV_SEP = ";"
    CSV_ENCODINGS = ["utf-8-sig", "cp1252", "latin-1"]

ARQUIVO_CSV = "BACKLOG_OS.csv"

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"backlog_{datetime.now():%Y%m%d}.log")


# =====================================================================
# LOG
# =====================================================================

def log(msg=""):
    linha = f"{datetime.now():%H:%M:%S}  {msg}" if msg else ""
    print(linha)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def cabecalho(t):
    log("=" * 66)
    log(f"  {t}")
    log("=" * 66)


# =====================================================================
# BANCO
# =====================================================================

def conectar():
    try:
        cnx = pymysql.connect(
            host=DB["host"], port=DB["port"], user=DB["user"],
            password=DB["password"], database=DB["database"],
            charset=DB["charset"], autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
        )
        with cnx.cursor() as cur:
            cur.execute("SET SESSION sql_mode = ''")
        cnx.commit()
        return cnx
    except Exception as e:
        log(f"ERRO de conexao: {e}")
        log("Verifique se o MySQL do Laragon esta ativo.")
        sys.exit(1)


def escalar(cnx, sql, params=None):
    with cnx.cursor() as cur:
        cur.execute(sql, params or ())
        r = cur.fetchone()
        return list(r.values())[0] if r else None


# =====================================================================
# LEITURA DO CSV
# =====================================================================

def ler_csv(caminho):
    """Le o CSV tentando os encodings em cascata."""
    ultimo = None
    for enc in CSV_ENCODINGS:
        try:
            df = pd.read_csv(
                caminho, sep=CSV_SEP, dtype=str, encoding=enc,
                keep_default_na=False, na_values=[],
                on_bad_lines="warn", engine="python",
            )
            log(f"  encoding detectado: {enc}")
            return df
        except Exception as e:
            ultimo = e
            continue
    raise RuntimeError(f"nao foi possivel ler o arquivo: {ultimo}")


def extrair_data_foto(df):
    """
    Extrai a data da foto do campo DT_RELATORIO.

    IMPORTANTE: usa a data DE DENTRO do arquivo, nao a data do sistema.
    Assim, se o agendador rodar com atraso, a foto mantem a data certa.
    """
    col = None
    for c in df.columns:
        if c.strip().upper() == "DT_RELATORIO":
            col = c
            break

    if not col:
        log("  AVISO: coluna DT_RELATORIO nao encontrada")
        return date.today()

    valores = df[col].dropna()
    valores = valores[valores.str.strip() != ""]

    if valores.empty:
        log("  AVISO: DT_RELATORIO vazio - usando a data de hoje")
        return date.today()

    amostra = valores.iloc[0].strip()
    dt = pd.to_datetime(amostra, dayfirst=True, errors="coerce")

    if pd.isna(dt):
        log(f"  AVISO: nao foi possivel interpretar '{amostra}'")
        return date.today()

    return dt.date()


def normalizar_colunas(df, cols_destino):
    """Casa os nomes do CSV com as colunas da tabela."""

    def simplificar(s):
        s = str(s).upper()
        for a, b in [("Á","A"),("À","A"),("Ã","A"),("Â","A"),
                     ("É","E"),("Ê","E"),("Í","I"),("Ó","O"),
                     ("Õ","O"),("Ô","O"),("Ú","U"),("Ç","C")]:
            s = s.replace(a, b)
        return re.sub(r"[^A-Z0-9]", "", s)

    idx = {simplificar(c): c for c in cols_destino}
    renomear = {}
    sem_destino = []

    for col in df.columns:
        chave = simplificar(col.replace("\ufeff", "").strip())
        if chave in idx:
            renomear[col] = idx[chave]
        else:
            sem_destino.append(col.strip())

    df = df.rename(columns=renomear)

    if sem_destino:
        log(f"  colunas sem destino: {len(sem_destino)}")

    faltando = [c for c in cols_destino
                if not c.startswith("_") and c not in df.columns]
    for c in faltando:
        df[c] = None

    return df


# =====================================================================
# ETAPAS DA CARGA
# =====================================================================

def carregar_staging(cnx, df, dt_foto, dry_run=False):
    """Carrega o CSV na stg_backlog."""
    log("  [1/4] staging")

    with cnx.cursor() as cur:
        cur.execute("""
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'stg_backlog'
            ORDER BY ORDINAL_POSITION
        """, (DB["database"],))
        cols = [r["COLUMN_NAME"] for r in cur.fetchall()]

    df = normalizar_colunas(df, cols)
    df["_ARQUIVO_ORIGEM"] = ARQUIVO_CSV
    df["_DT_POSICAO"] = dt_foto
    df["_LINHA_ARQUIVO"] = range(1, len(df) + 1)

    if dry_run:
        log(f"        [DRY-RUN] {len(df):,} linhas nao gravadas")
        return len(df)

    usar = [c for c in cols if c in df.columns]
    dados = df[usar].where(pd.notnull(df[usar]), None).replace({"": None})

    ph = ", ".join(["%s"] * len(usar))
    lista = ", ".join(f"`{c}`" for c in usar)
    sql = f"INSERT INTO stg_backlog ({lista}) VALUES ({ph})"

    with cnx.cursor() as cur:
        cur.execute("TRUNCATE TABLE stg_backlog")
        registros = dados.values.tolist()
        for i in range(0, len(registros), 10000):
            cur.executemany(sql, registros[i:i + 10000])

    cnx.commit()
    log(f"        {len(df):,} linhas")
    return len(df)


def normalizar(cnx, dry_run=False):
    """Monta a tmp_backlog_norm a partir do staging."""
    log("  [2/4] normalizacao")

    if dry_run:
        log("        [DRY-RUN] ignorado")
        return 0

    with cnx.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS tmp_backlog_norm")
        cur.execute("""
            CREATE TABLE tmp_backlog_norm (
                ID_UNICO            BIGINT AUTO_INCREMENT PRIMARY KEY,
                CONTRATO_N          BIGINT,
                OPERADORA_N         INT,
                OS_N                BIGINT,
                DT_RELATORIO_N      DATE,
                DT_AGENDA_N         DATE,
                DT_ABERTURA_OS_N    DATE,
                AGING_CLASSIFICACAO VARCHAR(40),
                SITUACAO_AGENDA     VARCHAR(20),
                STATUS_OS           VARCHAR(60),
                MOTIVO_REAG         VARCHAR(255),
                STATUS_CONTRATO     VARCHAR(120),
                SEGMENTO_CONTRATO   VARCHAR(80),
                TIPO_ASSINANTE      VARCHAR(80),
                NM_TECNOLOGIA       VARCHAR(80),
                QTDE_EQUIP_TOTAL    INT,
                NM_CIDADE           VARCHAR(100),
                NM_REGIONAL         VARCHAR(60),
                NM_CLUSTER          VARCHAR(60),
                NM_SUBCLUSTER       VARCHAR(80),
                TEM_REAG            TINYINT
            ) ENGINE=InnoDB
        """)

        cur.execute("""
            INSERT INTO tmp_backlog_norm (
                CONTRATO_N, OPERADORA_N, OS_N,
                DT_RELATORIO_N, DT_AGENDA_N, DT_ABERTURA_OS_N,
                AGING_CLASSIFICACAO, SITUACAO_AGENDA, STATUS_OS,
                MOTIVO_REAG, STATUS_CONTRATO, SEGMENTO_CONTRATO,
                TIPO_ASSINANTE, NM_TECNOLOGIA, QTDE_EQUIP_TOTAL,
                NM_CIDADE, NM_REGIONAL, NM_CLUSTER, NM_SUBCLUSTER,
                TEM_REAG
            )
            SELECT
                CAST(NULLIF(TRIM(CD_CONTRATO), '') AS UNSIGNED),
                CAST(NULLIF(TRIM(CD_OPERADORA), '') AS UNSIGNED),
                CAST(NULLIF(TRIM(CD_OS), '') AS UNSIGNED),
                STR_TO_DATE(SUBSTRING_INDEX(TRIM(DT_RELATORIO),' ',1),
                            '%%d/%%m/%%Y'),
                STR_TO_DATE(SUBSTRING_INDEX(TRIM(DATA_AGENDAMENTO),' ',1),
                            '%%d/%%m/%%Y'),
                STR_TO_DATE(SUBSTRING_INDEX(TRIM(DATA_ABERTURA_OS),' ',1),
                            '%%d/%%m/%%Y'),
                LEFT(TRIM(AGING), 40),
                CASE
                    WHEN UPPER(TRIM(AGING)) LIKE 'SEM AGENDA%%'    THEN 'SEM AGENDA'
                    WHEN UPPER(TRIM(AGING)) LIKE 'SEM AGENDAMENTO%%' THEN 'SEM AGENDA'
                    WHEN UPPER(TRIM(AGING)) LIKE 'AGENDA%%'       THEN 'AGENDADO'
                    WHEN UPPER(TRIM(AGING)) = 'IMEDIATA'          THEN 'AGENDADO'
                    ELSE 'NAO CLASSIFICADO'
                END,
                LEFT(STATUS_OS, 60),
                LEFT(MOTIVO_REAG, 255),
                LEFT(STATUS_CONTRATO, 120),
                LEFT(SEGMENTO_CONTRATO, 80),
                LEFT(TIPO_ASSINANTE, 80),
                LEFT(NM_TECNOLOGIA, 80),
                COALESCE(CAST(NULLIF(TRIM(QTDE_CABLE_EMTAS),'') AS UNSIGNED),0)
                  + COALESCE(CAST(NULLIF(TRIM(QTDE_CABLE_MODEM),'') AS UNSIGNED),0)
                  + COALESCE(CAST(NULLIF(TRIM(QTDE_DECODER_ANALOG),'') AS UNSIGNED),0)
                  + COALESCE(CAST(NULLIF(TRIM(QTDE_DECODER_DIGITAL),'') AS UNSIGNED),0),
                LEFT(NM_CIDADE, 100),
                LEFT(NM_REGIONAL, 60),
                LEFT(NM_CLUSTER, 60),
                LEFT(NM_SUBCLUSTER, 80),
                CASE WHEN DT_REAG IS NOT NULL
                      AND TRIM(DT_REAG) NOT IN ('', '-3') THEN 1 ELSE 0 END
            FROM stg_backlog
            WHERE CD_CONTRATO IS NOT NULL
              AND TRIM(CD_CONTRATO) <> ''
        """)
        n = cur.rowcount

        cur.execute("""CREATE INDEX idx_bkn_ct
                       ON tmp_backlog_norm (CONTRATO_N, OPERADORA_N)""")
        cur.execute("""CREATE INDEX idx_bkn_dt
                       ON tmp_backlog_norm (DT_RELATORIO_N)""")

    cnx.commit()
    log(f"        {n:,} linhas")
    return n


def inserir_log(cnx, dry_run=False):
    """Acumula no ft_backlog_log. INSERT IGNORE evita duplicar."""
    log("  [3/4] log de movimentacao")

    if dry_run:
        log("        [DRY-RUN] ignorado")
        return 0

    antes = escalar(cnx, "SELECT COUNT(*) FROM ft_backlog_log")

    with cnx.cursor() as cur:
        cur.execute("""
            INSERT IGNORE INTO ft_backlog_log (
                HASH_REGISTRO, DT_RELATORIO, MES_REFERENCIA,
                CD_OPERADORA, CD_CONTRATO, CD_OS,
                NM_CIDADE, NM_REGIONAL, NM_CLUSTER, NM_SUBCLUSTER,
                NM_MUNICIPIO, NM_MUNICIPIO_NORM, UF,
                STATUS_OS, SITUACAO_AGENDA, DATA_AGENDAMENTO,
                MOTIVO_REAG, FX_TEMPO_BASE, DATA_ABERTURA_OS,
                STATUS_CONTRATO, SEGMENTO_CONTRATO,
                TIPO_ASSINANTE, NM_TECNOLOGIA,
                QTDE_EQUIP_TOTAL, ARQUIVO_ORIGEM, DT_CARGA
            )
            SELECT
                SHA2(CONCAT_WS('|', n.CONTRATO_N,
                     IFNULL(n.OPERADORA_N,''), IFNULL(n.OS_N,''),
                     n.DT_RELATORIO_N), 256),
                n.DT_RELATORIO_N,
                DATE_FORMAT(n.DT_RELATORIO_N, '%%Y-%%m'),
                n.OPERADORA_N, n.CONTRATO_N, n.OS_N,
                n.NM_CIDADE, n.NM_REGIONAL, n.NM_CLUSTER, n.NM_SUBCLUSTER,
                d.NM_MUNICIPIO, d.NM_MUNICIPIO_NORM, d.UF,
                n.STATUS_OS, n.SITUACAO_AGENDA, n.DT_AGENDA_N,
                n.MOTIVO_REAG, n.AGING_CLASSIFICACAO, n.DT_ABERTURA_OS_N,
                n.STATUS_CONTRATO, n.SEGMENTO_CONTRATO,
                n.TIPO_ASSINANTE, n.NM_TECNOLOGIA,
                n.QTDE_EQUIP_TOTAL, %s, NOW()
            FROM tmp_backlog_norm n
            LEFT JOIN dim_operadora_municipio d
                   ON n.OPERADORA_N = d.CD_OPERADORA
        """, (ARQUIVO_CSV,))
        novos = cur.rowcount

    cnx.commit()

    depois = escalar(cnx, "SELECT COUNT(*) FROM ft_backlog_log")
    datas = escalar(cnx,
        "SELECT COUNT(DISTINCT DT_RELATORIO) FROM ft_backlog_log")

    log(f"        novos: {novos:,}")
    log(f"        total no log: {depois:,}  ({datas} datas)")

    if novos == 0 and antes > 0:
        log("        (essa foto ja estava carregada)")

    return novos


def regenerar_atual(cnx, dry_run=False):
    """Recria o ft_backlog_atual com a ultima posicao de cada contrato."""
    log("  [4/4] posicao atual")

    if dry_run:
        log("        [DRY-RUN] ignorado")
        return 0

    with cnx.cursor() as cur:
        cur.execute("TRUNCATE ft_backlog_atual")
        cur.execute("""
            INSERT INTO ft_backlog_atual
            SELECT l.*, l.DT_RELATORIO, 0, 0
            FROM ft_backlog_log l
            INNER JOIN (
                SELECT CD_CONTRATO, CD_OPERADORA, CD_OS,
                       MAX(DT_RELATORIO) AS dt
                FROM ft_backlog_log
                GROUP BY CD_CONTRATO, CD_OPERADORA, CD_OS
            ) u ON  l.CD_CONTRATO  = u.CD_CONTRATO
                AND l.CD_OPERADORA <=> u.CD_OPERADORA
                AND l.CD_OS        <=> u.CD_OS
                AND l.DT_RELATORIO = u.dt
        """)
        n = cur.rowcount

    cnx.commit()
    log(f"        {n:,} registros")
    return n


def auditar(cnx, dt_foto, lidos, inseridos, t0, status, msg=None):
    try:
        with cnx.cursor() as cur:
            cur.execute("""
                INSERT INTO tb_auditoria_carga
                    (DT_INICIO, DT_FIM, DOMINIO, ARQUIVO, MES_REFERENCIA,
                     REGISTROS_LIDOS, REGISTROS_INSERIDOS,
                     REGISTROS_REJEITADOS, TEMPO_PROCESSAMENTO_SEG,
                     STATUS, MENSAGEM)
                VALUES (%s, NOW(), 'BACKLOG', %s, %s, %s, %s, %s, %s, %s, %s)
            """, (datetime.fromtimestamp(t0), ARQUIVO_CSV,
                  dt_foto.strftime("%Y-%m") if dt_foto else None,
                  lidos, inseridos, max(0, lidos - inseridos),
                  int(time.time() - t0), status, msg))
        cnx.commit()
    except Exception as e:
        log(f"  aviso: falha ao gravar auditoria: {e}")


def resumo_log(cnx):
    """Mostra o historico acumulado ate agora."""
    log("")
    log("  HISTORICO ACUMULADO")
    log("  " + "-" * 58)

    with cnx.cursor() as cur:
        cur.execute("""
            SELECT DT_RELATORIO,
                   COUNT(*) AS os,
                   COUNT(DISTINCT CD_CONTRATO) AS contratos,
                   SUM(SITUACAO_AGENDA = 'AGENDADO') AS agendados,
                   SUM(SITUACAO_AGENDA = 'SEM AGENDA') AS sem_agenda
            FROM ft_backlog_log
            GROUP BY DT_RELATORIO
            ORDER BY DT_RELATORIO DESC
            LIMIT 15
        """)
        rows = cur.fetchall()

    if not rows:
        log("        vazio")
        return

    log(f"        {'DATA':<12}{'OS':>9}{'CONTRATOS':>11}"
        f"{'AGEND':>9}{'S/AGENDA':>10}")
    for r in rows:
        log(f"        {str(r['DT_RELATORIO']):<12}"
            f"{r['os']:>9,}{r['contratos']:>11,}"
            f"{r['agendados']:>9,}{r['sem_agenda']:>10,}")

    if len(rows) >= 2:
        log("")
        log(f"        {len(rows)} fotos acumuladas - "
            f"o log de movimentacao ja esta utilizavel")
    else:
        log("")
        log("        1 foto apenas - o log ganha valor a cada dia")


# =====================================================================
# MAIN
# =====================================================================

def main():
    ap = argparse.ArgumentParser(description="Carga diaria do Backlog")
    ap.add_argument("--forcar", action="store_true",
                    help="recarrega mesmo se a data ja existir")
    ap.add_argument("--dry-run", action="store_true",
                    help="simula sem gravar")
    args = ap.parse_args()

    t0 = time.time()

    cabecalho("CARGA DIARIA DO BACKLOG")
    if args.dry_run:
        log("  MODO DRY-RUN - nada sera gravado")
        log("")

    # ---------- localiza o arquivo ----------
    pasta = PASTAS.get("BACKLOG")
    caminho = os.path.join(pasta, ARQUIVO_CSV)

    if not os.path.exists(caminho):
        log(f"  ARQUIVO NAO ENCONTRADO")
        log(f"  {caminho}")
        log("")
        log("  A carga foi abortada. Verifique se o arquivo foi gerado.")
        sys.exit(2)

    mtime = datetime.fromtimestamp(os.path.getmtime(caminho))
    tamanho = os.path.getsize(caminho) / 1024 / 1024

    log(f"  arquivo   : {ARQUIVO_CSV}")
    log(f"  modificado: {mtime:%d/%m/%Y %H:%M}")
    log(f"  tamanho   : {tamanho:.1f} MB")
    log("")

    # ---------- le o CSV ----------
    try:
        df = ler_csv(caminho)
    except Exception as e:
        log(f"  ERRO ao ler o CSV: {e}")
        sys.exit(3)

    log(f"  linhas lidas: {len(df):,}")

    dt_foto = extrair_data_foto(df)
    log(f"  data da foto: {dt_foto:%d/%m/%Y}  (do campo DT_RELATORIO)")
    log("")

    cnx = conectar()

    # ---------- ja existe? ----------
    ja_existe = escalar(cnx, """
        SELECT COUNT(*) FROM ft_backlog_log WHERE DT_RELATORIO = %s
    """, (dt_foto,))

    if ja_existe and not args.forcar:
        log(f"  A foto de {dt_foto:%d/%m/%Y} ja foi carregada "
            f"({ja_existe:,} registros)")
        log("  Nada a fazer. Use --forcar para recarregar.")
        resumo_log(cnx)
        auditar(cnx, dt_foto, len(df), 0, t0, "OK",
                "foto ja carregada")
        cnx.close()
        return

    if ja_existe and args.forcar:
        log(f"  --forcar ativo: removendo {ja_existe:,} registros "
            f"de {dt_foto:%d/%m/%Y}")
        if not args.dry_run:
            with cnx.cursor() as cur:
                cur.execute(
                    "DELETE FROM ft_backlog_log WHERE DT_RELATORIO = %s",
                    (dt_foto,))
            cnx.commit()
        log("")

    # ---------- executa as etapas ----------
    try:
        lidos = carregar_staging(cnx, df, dt_foto, args.dry_run)
        normalizar(cnx, args.dry_run)
        novos = inserir_log(cnx, args.dry_run)
        regenerar_atual(cnx, args.dry_run)

        if not args.dry_run:
            auditar(cnx, dt_foto, lidos, novos, t0, "OK")

        resumo_log(cnx)

        log("")
        log("=" * 66)
        log(f"  CONCLUIDO em {time.time() - t0:.1f}s")
        log(f"  log: {LOG_FILE}")
        log("=" * 66)

    except Exception as e:
        cnx.rollback()
        log("")
        log(f"  ERRO: {e}")
        import traceback
        log(traceback.format_exc())
        auditar(cnx, dt_foto, len(df), 0, t0, "ERRO", str(e)[:500])
        cnx.close()
        sys.exit(1)

    cnx.close()


if __name__ == "__main__":
    main()
