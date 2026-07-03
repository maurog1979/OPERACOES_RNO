# -*- coding: utf-8 -*-

# Compatibilidade com dashboards legados/migrados
_DF_CACHE = {}
_OPTIONS_CACHE = {}
"""
data/db.py
Cache compartilhado de tabelas MySQL para todos os dashboards.
"""
import time
import pandas as pd
from sqlalchemy import create_engine

DB_URL = "mysql+pymysql://root:@localhost:3306/safra"

# ============================================================
# Cache compartilhado: {nome_tabela: {"df": DataFrame, "ts": timestamp, "load_time": secs}}
# ============================================================
_CACHE = {}

def get_engine():
    return create_engine(DB_URL, pool_pre_ping=True)

# Colunas REALMENTE usadas pelos dashboards (UNIAO de todos)
# Se um dashboard precisar de outra coluna, adicione aqui.
COLS_SAFRA_ENRIQUECIDA = [
    # Base
    "CD_NET", "UF", "NM_CIDADE", "SAFRA", "DS_TIPO_DESCONEXAO",
    "PARCEIRA_NOME", "PENDENCIA", "SITUACAO_AGENDA",
    # Backlog
    "TEM_BACKLOG", "BKL_AGING", "BKL_STATUS_OS",
    "BKL_DATA_AGENDAMENTO", "BKL_TEMPO_ABERTURA_DIAS", "BKL_FX_TEMPO",
    "BKL_MOTIVO_REAG", "BKL_TECNOLOGIA", "BKL_SEGMENTO",
    "BKL_AREA_DESPACHO", "BKL_DIAS_AGENDAMENTO",
    # Outros dashboards
    "FAIXA_LOG", "TEM_ANALITICO", "TEM_TOA", "TEM_QAD",
    "TOA_STATUS", "TOA_PARCEIRA",
    # Aging fallback
    "NR_DIAS_EM_ABERTO", "NR_AGING_OS",
]

# Tabelas suportadas e suas colunas otimizadas
TABLE_COLS = {
    "safra_enriquecida": COLS_SAFRA_ENRIQUECIDA,
    # safra_final, quebra_total, toa: deixa default (SELECT *)
}

def load_table(table, categorical_cols=None, force_reload=False):
    """
    Carrega tabela do MySQL com cache compartilhado.

    - Se a tabela ja esta no cache, retorna instantaneamente.
    - SELECT otimizado apenas das colunas necessarias (se mapeada).
    - Aplica category type para reduzir RAM.

    Args:
        table: nome da tabela MySQL
        categorical_cols: lista de colunas para converter em category
        force_reload: forca recarga ignorando cache
    """
    global _CACHE
    if not force_reload and table in _CACHE:
        return _CACHE[table]["df"]

    t0 = time.time()
    engine = get_engine()

    # Monta SELECT otimizado se a tabela tem colunas mapeadas
    if table in TABLE_COLS:
        cols = TABLE_COLS[table]
        # Verifica quais colunas existem na tabela antes de selecionar
        try:
            sample = pd.read_sql(f"SELECT * FROM {table} LIMIT 1", engine)
            cols_existentes = [c for c in cols if c in sample.columns]
            cols_str = ", ".join(f"`{c}`" for c in cols_existentes)
            query = f"SELECT {cols_str} FROM {table}"
            print(f"[DB] {table}: SELECT otimizado ({len(cols_existentes)} cols)")
        except Exception as e:
            print(f"[DB] {table}: fallback para SELECT * ({e})")
            query = f"SELECT * FROM {table}"
    else:
        query = f"SELECT * FROM {table}"

    try:
        df = pd.read_sql(query, engine)
        engine.dispose()

        # Aplica categoricals para reduzir RAM
        if categorical_cols:
            for col in categorical_cols:
                if col in df.columns:
                    try:
                        df[col] = df[col].astype("category")
                    except Exception:
                        pass

        elapsed = round(time.time() - t0, 2)
        mem_mb = round(df.memory_usage(deep=True).sum() / 1024**2, 1)
        _CACHE[table] = {
            "df": df,
            "ts": time.time(),
            "load_time": elapsed,
            "mem_mb": mem_mb,
            "rows": len(df),
            "cols": len(df.columns),
        }
        print(f"[DB] {table}: {len(df):,} linhas | {mem_mb} MB | carregado em {elapsed}s")
        return df

    except Exception as e:
        print(f"[DB] ERRO ao carregar {table}: {e}")
        return pd.DataFrame()

def preload_tables(tables=None):
    """
    Pre-carrega tabelas no startup do Flask.
    Usado em create_app() para evitar lentidao no primeiro acesso.
    """
    if tables is None:
        tables = ["safra_enriquecida"]
    print("=" * 60)
    print("[DB] PRE-CARREGAMENTO DE TABELAS (startup)")
    print("=" * 60)
    t0 = time.time()
    for tbl in tables:
        # Carrega com categoricals padrao do dash_backlog
        cat_cols = ["SAFRA", "DS_TIPO_DESCONEXAO", "PENDENCIA",
                    "TEM_BACKLOG", "FAIXA_LOG", "UF"]
        load_table(tbl, categorical_cols=cat_cols)
    total = round(time.time() - t0, 2)
    print(f"[DB] Pre-carregamento concluido em {total}s")
    print("=" * 60)

def cache_info():
    """Retorna info de diagnostico do cache."""
    return {
        tbl: {k: v for k, v in d.items() if k != "df"}
        for tbl, d in _CACHE.items()
    }

def clear_cache(table=None):
    """Limpa cache de uma tabela ou de tudo."""
    global _CACHE
    if table:
        _CACHE.pop(table, None)
    else:
        _CACHE.clear()

# ---------- QUEBRA TOTAL ----------
COLS_QUEBRA_TOTAL = [
    "NR_CONTRATO", "NM_CIDADE", "UF", "DT_AGENDA",
    "ANO", "MES", "DIA",
    "NM_TIPO_TRATAMENTO", "NM_MOTIVO_REAGENDA",
    "NM_QUEBRA_RESPONSAVEL", "NM_QUEBRA_CENARIO",
    "PARCEIRA", "PARCEIRA_NOME",
]
