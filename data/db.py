"""Leitura de tabelas MySQL com cache isolado e expiração."""
import logging
import re
import threading
import time

import pandas as pd
from sqlalchemy import create_engine
from config import Config

_CACHE = {}
_LOCK = threading.RLock()
logger = logging.getLogger(__name__)


class DatabaseUnavailable(RuntimeError):
    """Falha de leitura, distinta de uma tabela vazia."""


def cache_fresh(timestamp):
    return timestamp is not None and time.monotonic() - timestamp < Config.CACHE_TTL_SECONDS


def get_engine():
    return create_engine(Config.db_url(), pool_pre_ping=True, connect_args={
        "connect_timeout": Config.DB_CONNECT_TIMEOUT,
        "read_timeout": Config.DB_READ_TIMEOUT,
        "write_timeout": Config.DB_READ_TIMEOUT,
    })


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
    "ANL_MOTIVO_REAGENDA", "ANL_QUEBRA_RESPONSAVEL", "ANL_QUEBRA_CENARIO",
    "ANL_TIPO_TRATAMENTO", "LOG_ULT_TIPO_OS",
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
    """Cache com expiração e cópias isoladas para cada consumidor."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise ValueError("Nome de tabela inválido")
    with _LOCK:
        cached = _CACHE.get(table)
        if force_reload or cached is None or not cache_fresh(cached.get("clock")):
            start = time.monotonic()
            engine = get_engine()
            try:
                query = f"SELECT * FROM `{table}`"
                if table in TABLE_COLS:
                    sample = pd.read_sql(f"SELECT * FROM `{table}` LIMIT 0", engine)
                    available = {str(c).upper(): c for c in sample.columns}
                    cols = [available[c] for c in TABLE_COLS[table] if c in available]
                    if cols:
                        selected = ", ".join("`" + c.replace("`", "``") + "`" for c in cols)
                        query = f"SELECT {selected} FROM `{table}`"
                df = pd.read_sql(query, engine)
                df.columns = [str(c).upper() for c in df.columns]
                _CACHE[table] = {
                    "df": df, "clock": time.monotonic(), "ts": time.time(),
                    "load_time": round(time.monotonic() - start, 2),
                    "mem_mb": round(df.memory_usage(deep=True).sum() / 1024**2, 1),
                    "rows": len(df), "cols": len(df.columns),
                }
            except Exception as exc:
                logger.exception("Falha ao carregar %s", table)
                raise DatabaseUnavailable("Dados temporariamente indisponíveis.") from exc
            finally:
                engine.dispose()
        result = _CACHE[table]["df"].copy(deep=True)
    for col in categorical_cols or []:
        if col in result.columns:
            result[col] = result[col].astype("category")
    return result


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
    with _LOCK:
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

