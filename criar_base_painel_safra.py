# -*- coding: utf-8 -*-
"""
criar_base_painel_safra.py

PAINEL SAFRA — BASE HISTÓRICA E RESUMOS
Projeto: OPERACOES_RNO

Objetivo:
- Criar as tabelas de apoio do Painel Safra.
- Usar preferencialmente a tabela safra_enriquecida; se não existir, usar safra.
- Gerar resumo mensal histórico por:
    RNO e CIDADE
    ANO, MES, UF, CIDADE, SAFRA, DS_TIPO_DESCONEXAO
- Gerar resumo diário somente do mês mais recente encontrado na base.
- Criar/atualizar tabela de metas com as metas informadas:
    SAFRA 1 MES:    Opção 85% / Inadimplência 45%
    SAFRA 4 MESES:  Opção 92% / Inadimplência 56%
    SAFRA 13 MESES: Opção 98% / Inadimplência 67%

Observação importante:
- Os painéis principais NÃO usam PARCEIRA, conforme orientação do Mauro.
- A estrutura é baseada em RNO consolidado e Cidades da Regional Norte.
- PARCEIRA poderá ser usada depois em gráficos acessórios, mas não entra nas tabelas principais deste script.

Como usar:
1) Confirme que o MySQL/Laragon está rodando.
2) Confirme que existe a tabela safra_enriquecida ou safra no banco safra.
3) Rode na raiz do projeto:
   python criar_base_painel_safra.py

Saídas:
- Tabelas criadas/atualizadas no MySQL:
    safra_metas
    safra_resumo_mensal
    safra_resumo_diario
    safra_carga_controle
- Relatório:
    relatorio_criar_base_painel_safra.txt
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, date
from calendar import monthrange
import math
import sys
import traceback
import unicodedata
from typing import Dict, List, Tuple, Optional

import pandas as pd
from sqlalchemy import create_engine, text


# ============================================================
# CONFIGURAÇÕES
# ============================================================

ROOT_FIXO = Path(r"C:\Users\n5996917\OneDrive - Claro SA\INTRANET\OPERACOES_RNO")
ROOT = ROOT_FIXO if ROOT_FIXO.exists() else Path.cwd()

DB_URL = "mysql+pymysql://root:@localhost:3306/safra?charset=utf8mb4"

REPORT_FILE = ROOT / "relatorio_criar_base_painel_safra.txt"

SOURCE_TABLE_PRIORITY = [
    "safra_enriquecida",
    "SAFRA_ENRIQUECIDA",
    "safra",
    "SAFRA",
]

# Se no futuro precisar validar por contrato único, trocar para "distinct_cd_net".
# Para manter aderência aos totais atuais dos dashboards, o padrão é contagem de linhas.
COUNT_MODE = "rows"  # opções: "rows" ou "distinct_cd_net"

# Metas oficiais informadas pelo usuário.
METAS_PADRAO = [
    {"SAFRA": "1 MES", "DS_TIPO_DESCONEXAO": "Opção", "META_PERCENTUAL": 85.00},
    {"SAFRA": "1 MES", "DS_TIPO_DESCONEXAO": "Inadimplência", "META_PERCENTUAL": 45.00},
    {"SAFRA": "4 MESES", "DS_TIPO_DESCONEXAO": "Opção", "META_PERCENTUAL": 92.00},
    {"SAFRA": "4 MESES", "DS_TIPO_DESCONEXAO": "Inadimplência", "META_PERCENTUAL": 56.00},
    {"SAFRA": "13 MESES", "DS_TIPO_DESCONEXAO": "Opção", "META_PERCENTUAL": 98.00},
    {"SAFRA": "13 MESES", "DS_TIPO_DESCONEXAO": "Inadimplência", "META_PERCENTUAL": 67.00},
]

# Mapeamento objetivo das cidades da Regional Norte usadas nos painéis.
MAPA_CIDADE_UF = {
    "BELEM": "PA",
    "ANANINDEUA": "PA",
    "CASTANHAL": "PA",
    "MARABA": "PA",
    "PARAUAPEBAS": "PA",
    "PARAGOMINAS": "PA",
    "MANAUS": "AM",
    "MACAPA": "AP",
    "SANTANA": "AP",
    "SAO LUIS": "MA",
    "IMPERATRIZ": "MA",
    "CAXIAS": "MA",
    "TIMON": "MA",
}

COL_ALTERNATIVAS = {
    "DT_BASE": ["DT_BASE", "DATA_BASE", "BASE"],
    "DT_ACAO": ["DT_ACAO", "DATA_ACAO", "DATA AÇÃO", "DATA_ACAO", "MÊS/ANO AÇÃO", "MES/ANO ACAO"],
    "DATA_PEND": ["DATA_PEND", "DT_PEND", "DATA_PENDENCIA", "MÊS/ANO PEND.", "MES/ANO PEND.", "MES_ANO_PEND"],
    "NM_CIDADE": ["NM_CIDADE", "CIDADE", "ANL_CIDADE_NORM", "ANL_CIDADE", "TOA_CIDADE"],
    "UF": ["UF", "TOA_UF", "ANL_UF"],
    "SAFRA": ["SAFRA"],
    "DS_TIPO_DESCONEXAO": ["DS_TIPO_DESCONEXAO", "TIPO_DESCONEXAO", "TIPO", "TIPO DESC", "TIPO_DESCONEXÃO"],
    "PENDENCIA": ["PENDENCIA", "PENDÊNCIA", "STATUS_PENDENCIA", "STATUS", "SITUACAO", "SITUAÇÃO"],
    "CD_NET": ["CD_NET", "CONTRATO", "COD_CONTRATO"],
}


# ============================================================
# UTILITÁRIOS
# ============================================================

def norm_txt(value) -> str:
    if value is None:
        return ""
    txt = str(value).strip()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    return txt


def norm_key(value) -> str:
    return norm_txt(value).upper().replace("  ", " ")


def norm_col(value) -> str:
    txt = norm_key(value)
    txt = txt.replace(" ", "_").replace(".", "").replace("-", "_").replace("/", "_")
    while "__" in txt:
        txt = txt.replace("__", "_")
    return txt.strip("_")


def log_append(lines: List[str], text_line: str = ""):
    lines.append(text_line)


def parse_date_series(s: pd.Series) -> pd.Series:
    """Parse flexível para datas brasileiras/americanas."""
    if s is None:
        return pd.Series(dtype="datetime64[ns]")

    # Primeiro tenta dayfirst=True, mais provável nas bases brasileiras.
    dt = pd.to_datetime(s, errors="coerce", dayfirst=True)

    # Para valores ainda inválidos, tenta dayfirst=False.
    mask = dt.isna() & s.notna()
    if mask.any():
        dt2 = pd.to_datetime(s[mask], errors="coerce", dayfirst=False)
        dt.loc[mask] = dt2

    return dt


def resolver_coluna(df: pd.DataFrame, logical_name: str) -> Optional[str]:
    """Resolve coluna real da base a partir de alternativas."""
    if df is None or df.empty:
        return None

    col_map = {norm_col(c): c for c in df.columns}

    for alt in COL_ALTERNATIVAS.get(logical_name, []):
        key = norm_col(alt)
        if key in col_map:
            return col_map[key]

    return None


def normalizar_safra(value) -> str:
    txt = norm_key(value)
    if "13" in txt:
        return "13 MESES"
    if "4" in txt:
        return "4 MESES"
    if "1" in txt:
        return "1 MES"
    return str(value).strip() if value is not None else ""


def normalizar_tipo(value) -> str:
    txt = norm_key(value)
    if "INAD" in txt:
        return "Inadimplência"
    if "OPCAO" in txt or "OPÇÃO" in str(value).upper():
        return "Opção"
    return str(value).strip() if value is not None else ""


def normalizar_cidade(value) -> str:
    txt = norm_key(value)
    txt = txt.replace("SAO LUIZ", "SAO LUIS")
    return txt


def inferir_uf(cidade: str, uf_original: str = "") -> str:
    uf = norm_key(uf_original)
    if uf in {"PA", "AM", "AP", "MA"}:
        return uf
    return MAPA_CIDADE_UF.get(normalizar_cidade(cidade), "NI")


def status_recuperacao(row, col_pendencia: Optional[str], col_dt_acao: Optional[str]) -> str:
    """Define RECUPERADO/PENDENTE de forma robusta."""
    if col_pendencia and col_pendencia in row.index:
        raw = row[col_pendencia]
        txt = norm_key(raw)

        if "RECUP" in txt:
            return "RECUPERADO"
        if "PEND" in txt:
            return "PENDENTE"

        # Casos numéricos: não forçar interpretação se houver data de ação válida.
        # Em bases antigas pode aparecer 0/1; nesses casos a data de ação é fallback.

    if col_dt_acao and col_dt_acao in row.index:
        val = row[col_dt_acao]
        if pd.notna(val):
            return "RECUPERADO"

    return "PENDENTE"


def safe_int(value) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(value)
    except Exception:
        return 0


def pct(num: int, den: int) -> float:
    if not den:
        return 0.0
    return round((num / den) * 100, 4)


def meta_para(safra: str, tipo: str) -> float:
    safra_n = normalizar_safra(safra)
    tipo_n = normalizar_tipo(tipo)
    for item in METAS_PADRAO:
        if item["SAFRA"] == safra_n and item["DS_TIPO_DESCONEXAO"] == tipo_n:
            return float(item["META_PERCENTUAL"])
    return 0.0


def dias_restantes_mes(ano: int, mes: int, dia_ref: int) -> int:
    ultimo = monthrange(int(ano), int(mes))[1]
    return max(ultimo - int(dia_ref), 0)


# ============================================================
# BANCO DE DADOS
# ============================================================

def get_engine():
    return create_engine(DB_URL, pool_pre_ping=True)


def listar_tabelas(engine) -> List[str]:
    with engine.begin() as conn:
        rows = conn.execute(text("SHOW TABLES")).fetchall()
    return [str(r[0]) for r in rows]


def escolher_tabela_fonte(engine) -> str:
    tabelas = listar_tabelas(engine)
    mapa = {t.lower(): t for t in tabelas}

    for pref in SOURCE_TABLE_PRIORITY:
        if pref.lower() in mapa:
            return mapa[pref.lower()]

    raise RuntimeError(
        "Nenhuma tabela fonte encontrada. Esperado safra_enriquecida ou safra no banco safra."
    )


def criar_tabelas(engine):
    sqls = []

    sqls.append("""
    CREATE TABLE IF NOT EXISTS safra_metas (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ano INT NOT NULL,
        mes INT NOT NULL,
        safra VARCHAR(20) NOT NULL,
        ds_tipo_desconexao VARCHAR(50) NOT NULL,
        meta_percentual DECIMAL(10,4) NOT NULL,
        meta_qtd INT NULL,
        observacao VARCHAR(255) NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uk_safra_metas (ano, mes, safra, ds_tipo_desconexao)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    sqls.append("""
    CREATE TABLE IF NOT EXISTS safra_resumo_mensal (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        data_carga DATE NOT NULL,
        fonte_tabela VARCHAR(100) NOT NULL,
        ano INT NOT NULL,
        mes INT NOT NULL,
        nivel VARCHAR(20) NOT NULL,
        uf VARCHAR(5) NOT NULL,
        cidade VARCHAR(120) NOT NULL,
        safra VARCHAR(20) NOT NULL,
        ds_tipo_desconexao VARCHAR(50) NOT NULL,
        desc_total INT NOT NULL,
        rec_total INT NOT NULL,
        pend_total INT NOT NULL,
        perc_rec DECIMAL(10,4) NOT NULL,
        meta_percentual DECIMAL(10,4) NOT NULL,
        meta_qtd INT NOT NULL,
        gap_vol INT NOT NULL,
        gap_pp DECIMAL(10,4) NOT NULL,
        faltam_recuperar INT NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uk_safra_resumo_mensal (
            data_carga, ano, mes, nivel, uf, cidade, safra, ds_tipo_desconexao
        ),
        KEY idx_safra_resumo_mensal_filtros (ano, mes, uf, cidade, safra, ds_tipo_desconexao),
        KEY idx_safra_resumo_mensal_nivel (nivel)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    sqls.append("""
    CREATE TABLE IF NOT EXISTS safra_resumo_diario (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        data_carga DATE NOT NULL,
        fonte_tabela VARCHAR(100) NOT NULL,
        ano INT NOT NULL,
        mes INT NOT NULL,
        dia INT NOT NULL,
        data_ref DATE NOT NULL,
        nivel VARCHAR(20) NOT NULL,
        uf VARCHAR(5) NOT NULL,
        cidade VARCHAR(120) NOT NULL,
        safra VARCHAR(20) NOT NULL,
        ds_tipo_desconexao VARCHAR(50) NOT NULL,
        desc_total_mes INT NOT NULL,
        rec_dia INT NOT NULL,
        rec_acumulado INT NOT NULL,
        perc_rec_acumulado DECIMAL(10,4) NOT NULL,
        meta_percentual DECIMAL(10,4) NOT NULL,
        meta_qtd INT NOT NULL,
        gap_vol_acumulado INT NOT NULL,
        gap_pp_acumulado DECIMAL(10,4) NOT NULL,
        faltam_recuperar INT NOT NULL,
        dias_restantes INT NOT NULL,
        necessario_por_dia DECIMAL(12,4) NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uk_safra_resumo_diario (
            data_carga, ano, mes, dia, nivel, uf, cidade, safra, ds_tipo_desconexao
        ),
        KEY idx_safra_resumo_diario_filtros (ano, mes, dia, uf, cidade, safra, ds_tipo_desconexao),
        KEY idx_safra_resumo_diario_nivel (nivel)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    sqls.append("""
    CREATE TABLE IF NOT EXISTS safra_carga_controle (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        data_carga DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        fonte_tabela VARCHAR(100) NOT NULL,
        linhas_fonte INT NOT NULL,
        ano_mes_base VARCHAR(7) NULL,
        linhas_resumo_mensal INT NOT NULL,
        linhas_resumo_diario INT NOT NULL,
        status VARCHAR(30) NOT NULL,
        mensagem TEXT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    with engine.begin() as conn:
        for sql in sqls:
            conn.execute(text(sql))


def upsert_metas(engine, anos_meses: List[Tuple[int, int]]):
    rows = []
    for ano, mes in sorted(set(anos_meses)):
        for meta in METAS_PADRAO:
            rows.append({
                "ano": int(ano),
                "mes": int(mes),
                "safra": meta["SAFRA"],
                "ds_tipo_desconexao": meta["DS_TIPO_DESCONEXAO"],
                "meta_percentual": float(meta["META_PERCENTUAL"]),
                "observacao": "Meta padrão informada para Painel Safra",
            })

    if not rows:
        return 0

    sql = text("""
        INSERT INTO safra_metas
            (ano, mes, safra, ds_tipo_desconexao, meta_percentual, observacao)
        VALUES
            (:ano, :mes, :safra, :ds_tipo_desconexao, :meta_percentual, :observacao)
        ON DUPLICATE KEY UPDATE
            meta_percentual = VALUES(meta_percentual),
            observacao = VALUES(observacao),
            updated_at = CURRENT_TIMESTAMP
    """)

    with engine.begin() as conn:
        conn.execute(sql, rows)

    return len(rows)


def limpar_snapshot_do_dia(engine, data_carga: date):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM safra_resumo_mensal WHERE data_carga = :dc"), {"dc": data_carga})
        conn.execute(text("DELETE FROM safra_resumo_diario WHERE data_carga = :dc"), {"dc": data_carga})


def registrar_controle(engine, fonte_tabela: str, linhas_fonte: int, ano_mes_base: str, mensal: int, diario: int, status: str, mensagem: str):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO safra_carga_controle
                (fonte_tabela, linhas_fonte, ano_mes_base, linhas_resumo_mensal, linhas_resumo_diario, status, mensagem)
            VALUES
                (:fonte_tabela, :linhas_fonte, :ano_mes_base, :mensal, :diario, :status, :mensagem)
        """), {
            "fonte_tabela": fonte_tabela,
            "linhas_fonte": int(linhas_fonte),
            "ano_mes_base": ano_mes_base,
            "mensal": int(mensal),
            "diario": int(diario),
            "status": status,
            "mensagem": mensagem,
        })


# ============================================================
# PREPARAÇÃO DA BASE
# ============================================================

def carregar_fonte(engine, fonte_tabela: str) -> pd.DataFrame:
    return pd.read_sql(f"SELECT * FROM `{fonte_tabela}`", engine)


def preparar_base(df_raw: pd.DataFrame, report: List[str]) -> pd.DataFrame:
    if df_raw is None or df_raw.empty:
        raise RuntimeError("Tabela fonte está vazia.")

    df = df_raw.copy()

    col_dt_base = resolver_coluna(df, "DT_BASE")
    col_dt_acao = resolver_coluna(df, "DT_ACAO")
    col_data_pend = resolver_coluna(df, "DATA_PEND")
    col_cidade = resolver_coluna(df, "NM_CIDADE")
    col_uf = resolver_coluna(df, "UF")
    col_safra = resolver_coluna(df, "SAFRA")
    col_tipo = resolver_coluna(df, "DS_TIPO_DESCONEXAO")
    col_pendencia = resolver_coluna(df, "PENDENCIA")
    col_cd_net = resolver_coluna(df, "CD_NET")

    resolvidas = {
        "DT_BASE": col_dt_base,
        "DT_ACAO": col_dt_acao,
        "DATA_PEND": col_data_pend,
        "NM_CIDADE": col_cidade,
        "UF": col_uf,
        "SAFRA": col_safra,
        "DS_TIPO_DESCONEXAO": col_tipo,
        "PENDENCIA": col_pendencia,
        "CD_NET": col_cd_net,
    }

    report.append("## COLUNAS RESOLVIDAS")
    for k, v in resolvidas.items():
        report.append(f"- {k}: {v if v else 'NÃO ENCONTRADA'}")
    report.append("")

    obrigatorias = [
        ("DT_BASE", col_dt_base),
        ("NM_CIDADE", col_cidade),
        ("SAFRA", col_safra),
        ("DS_TIPO_DESCONEXAO", col_tipo),
    ]

    faltantes = [nome for nome, col in obrigatorias if not col]
    if faltantes:
        raise RuntimeError("Colunas obrigatórias não encontradas: " + ", ".join(faltantes))

    df["_DT_BASE"] = parse_date_series(df[col_dt_base])

    # Se DT_BASE vier muito incompleta, tenta DATA_PEND como fallback.
    if df["_DT_BASE"].isna().mean() > 0.50 and col_data_pend:
        dt_pend = parse_date_series(df[col_data_pend])
        df["_DT_BASE"] = df["_DT_BASE"].fillna(dt_pend)

    if col_dt_acao:
        df["_DT_ACAO"] = parse_date_series(df[col_dt_acao])
    else:
        df["_DT_ACAO"] = pd.NaT

    df = df[df["_DT_BASE"].notna()].copy()

    if df.empty:
        raise RuntimeError("Após parse de DT_BASE, não restaram linhas válidas.")

    df["ANO"] = df["_DT_BASE"].dt.year.astype(int)
    df["MES"] = df["_DT_BASE"].dt.month.astype(int)

    df["CIDADE"] = df[col_cidade].apply(normalizar_cidade)
    df["CIDADE"] = df["CIDADE"].replace("", "NI")

    if col_uf:
        df["UF"] = [inferir_uf(c, u) for c, u in zip(df["CIDADE"], df[col_uf])]
    else:
        df["UF"] = df["CIDADE"].apply(lambda c: inferir_uf(c))

    df["SAFRA_NORM"] = df[col_safra].apply(normalizar_safra)
    df["TIPO_NORM"] = df[col_tipo].apply(normalizar_tipo)

    df["STATUS_REC"] = df.apply(lambda row: status_recuperacao(row, col_pendencia, "_DT_ACAO"), axis=1)

    # Restrição conceitual dos painéis: somente os 3 horizontes e os 2 tipos do modelo.
    df = df[df["SAFRA_NORM"].isin(["1 MES", "4 MESES", "13 MESES"])].copy()
    df = df[df["TIPO_NORM"].isin(["Opção", "Inadimplência"])].copy()

    if COUNT_MODE == "distinct_cd_net" and col_cd_net:
        df["_COUNT_KEY"] = df[col_cd_net].astype(str).fillna("")
    else:
        df["_COUNT_KEY"] = range(1, len(df) + 1)

    return df


# ============================================================
# RESUMOS
# ============================================================

def agregar_base(df: pd.DataFrame, group_cols: List[str]) -> pd.DataFrame:
    if COUNT_MODE == "distinct_cd_net":
        total = df.groupby(group_cols, dropna=False)["_COUNT_KEY"].nunique().reset_index(name="desc_total")
        rec = df[df["STATUS_REC"] == "RECUPERADO"].groupby(group_cols, dropna=False)["_COUNT_KEY"].nunique().reset_index(name="rec_total")
    else:
        total = df.groupby(group_cols, dropna=False).size().reset_index(name="desc_total")
        rec = df[df["STATUS_REC"] == "RECUPERADO"].groupby(group_cols, dropna=False).size().reset_index(name="rec_total")

    out = total.merge(rec, on=group_cols, how="left")
    out["rec_total"] = out["rec_total"].fillna(0).astype(int)
    out["desc_total"] = out["desc_total"].astype(int)
    out["pend_total"] = out["desc_total"] - out["rec_total"]
    out["perc_rec"] = [pct(r, d) for r, d in zip(out["rec_total"], out["desc_total"])]
    return out


def aplicar_metas_mensal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["meta_percentual"] = [meta_para(s, t) for s, t in zip(df["safra"], df["ds_tipo_desconexao"])]
    df["meta_qtd"] = [int(math.ceil(d * (m / 100))) for d, m in zip(df["desc_total"], df["meta_percentual"])]
    df["gap_vol"] = df["rec_total"] - df["meta_qtd"]
    df["gap_pp"] = (df["perc_rec"] - df["meta_percentual"]).round(4)
    df["faltam_recuperar"] = (df["meta_qtd"] - df["rec_total"]).clip(lower=0).astype(int)
    return df


def montar_resumo_mensal(df: pd.DataFrame, fonte_tabela: str, data_carga: date) -> pd.DataFrame:
    # Cidade
    group_city = ["ANO", "MES", "UF", "CIDADE", "SAFRA_NORM", "TIPO_NORM"]
    cidade = agregar_base(df, group_city)
    cidade["nivel"] = "CIDADE"

    cidade = cidade.rename(columns={
        "ANO": "ano",
        "MES": "mes",
        "UF": "uf",
        "CIDADE": "cidade",
        "SAFRA_NORM": "safra",
        "TIPO_NORM": "ds_tipo_desconexao",
    })

    # RNO consolidado
    group_rno = ["ANO", "MES", "SAFRA_NORM", "TIPO_NORM"]
    rno = agregar_base(df, group_rno)
    rno["nivel"] = "RNO"
    rno["uf"] = "RNO"
    rno["cidade"] = "RNO"

    rno = rno.rename(columns={
        "ANO": "ano",
        "MES": "mes",
        "SAFRA_NORM": "safra",
        "TIPO_NORM": "ds_tipo_desconexao",
    })

    cols = ["ano", "mes", "nivel", "uf", "cidade", "safra", "ds_tipo_desconexao", "desc_total", "rec_total", "pend_total", "perc_rec"]
    mensal = pd.concat([rno[cols], cidade[cols]], ignore_index=True)
    mensal = aplicar_metas_mensal(mensal)
    mensal.insert(0, "fonte_tabela", fonte_tabela)
    mensal.insert(0, "data_carga", data_carga)

    final_cols = [
        "data_carga", "fonte_tabela", "ano", "mes", "nivel", "uf", "cidade", "safra", "ds_tipo_desconexao",
        "desc_total", "rec_total", "pend_total", "perc_rec", "meta_percentual", "meta_qtd", "gap_vol", "gap_pp", "faltam_recuperar",
    ]

    return mensal[final_cols].sort_values(["ano", "mes", "safra", "ds_tipo_desconexao", "nivel", "cidade"])


def montar_resumo_diario(df: pd.DataFrame, mensal: pd.DataFrame, fonte_tabela: str, data_carga: date) -> Tuple[pd.DataFrame, str]:
    if df.empty:
        return pd.DataFrame(), ""

    max_ano = int(df["ANO"].max())
    max_mes = int(df.loc[df["ANO"] == max_ano, "MES"].max())
    ano_mes_base = f"{max_ano:04d}-{max_mes:02d}"

    base_mes = df[(df["ANO"] == max_ano) & (df["MES"] == max_mes)].copy()
    if base_mes.empty:
        return pd.DataFrame(), ano_mes_base

    rec = base_mes[(base_mes["STATUS_REC"] == "RECUPERADO") & (base_mes["_DT_ACAO"].notna())].copy()

    # Mantém ações recuperadas do mesmo ano/mês da base atual.
    rec = rec[(rec["_DT_ACAO"].dt.year == max_ano) & (rec["_DT_ACAO"].dt.month == max_mes)].copy()
    if rec.empty:
        return pd.DataFrame(), ano_mes_base

    rec["DIA"] = rec["_DT_ACAO"].dt.day.astype(int)
    rec["DATA_REF"] = rec["_DT_ACAO"].dt.date

    def daily_group(dfx, group_cols):
        if COUNT_MODE == "distinct_cd_net":
            return dfx.groupby(group_cols, dropna=False)["_COUNT_KEY"].nunique().reset_index(name="rec_dia")
        return dfx.groupby(group_cols, dropna=False).size().reset_index(name="rec_dia")

    # Cidade
    group_city = ["ANO", "MES", "DIA", "DATA_REF", "UF", "CIDADE", "SAFRA_NORM", "TIPO_NORM"]
    cidade = daily_group(rec, group_city)
    cidade["nivel"] = "CIDADE"
    cidade = cidade.rename(columns={
        "ANO": "ano", "MES": "mes", "DIA": "dia", "DATA_REF": "data_ref", "UF": "uf", "CIDADE": "cidade",
        "SAFRA_NORM": "safra", "TIPO_NORM": "ds_tipo_desconexao",
    })

    # RNO
    group_rno = ["ANO", "MES", "DIA", "DATA_REF", "SAFRA_NORM", "TIPO_NORM"]
    rno = daily_group(rec, group_rno)
    rno["nivel"] = "RNO"
    rno["uf"] = "RNO"
    rno["cidade"] = "RNO"
    rno = rno.rename(columns={
        "ANO": "ano", "MES": "mes", "DIA": "dia", "DATA_REF": "data_ref",
        "SAFRA_NORM": "safra", "TIPO_NORM": "ds_tipo_desconexao",
    })

    daily = pd.concat([rno, cidade], ignore_index=True)

    # Junta totais mensais para o mesmo escopo.
    mensal_base = mensal[(mensal["ano"] == max_ano) & (mensal["mes"] == max_mes)].copy()
    mensal_key = mensal_base[[
        "ano", "mes", "nivel", "uf", "cidade", "safra", "ds_tipo_desconexao",
        "desc_total", "meta_percentual", "meta_qtd",
    ]].rename(columns={"desc_total": "desc_total_mes"})

    daily = daily.merge(
        mensal_key,
        on=["ano", "mes", "nivel", "uf", "cidade", "safra", "ds_tipo_desconexao"],
        how="left",
    )

    daily["desc_total_mes"] = daily["desc_total_mes"].fillna(0).astype(int)
    daily["meta_percentual"] = daily["meta_percentual"].fillna(0.0).astype(float)
    daily["meta_qtd"] = daily["meta_qtd"].fillna(0).astype(int)

    # Acumulado por escopo.
    sort_cols = ["ano", "mes", "nivel", "uf", "cidade", "safra", "ds_tipo_desconexao", "dia"]
    daily = daily.sort_values(sort_cols).copy()
    daily["rec_acumulado"] = daily.groupby([
        "ano", "mes", "nivel", "uf", "cidade", "safra", "ds_tipo_desconexao"
    ])["rec_dia"].cumsum().astype(int)

    daily["perc_rec_acumulado"] = [pct(r, d) for r, d in zip(daily["rec_acumulado"], daily["desc_total_mes"])]
    daily["gap_vol_acumulado"] = daily["rec_acumulado"] - daily["meta_qtd"]
    daily["gap_pp_acumulado"] = (daily["perc_rec_acumulado"] - daily["meta_percentual"]).round(4)
    daily["faltam_recuperar"] = (daily["meta_qtd"] - daily["rec_acumulado"]).clip(lower=0).astype(int)
    daily["dias_restantes"] = [dias_restantes_mes(a, m, d) for a, m, d in zip(daily["ano"], daily["mes"], daily["dia"])]

    def calc_necessario(faltam, dias_rest):
        if faltam <= 0:
            return 0.0
        if dias_rest <= 0:
            return float(faltam)
        return round(float(faltam) / float(dias_rest), 4)

    daily["necessario_por_dia"] = [calc_necessario(f, d) for f, d in zip(daily["faltam_recuperar"], daily["dias_restantes"])]
    daily.insert(0, "fonte_tabela", fonte_tabela)
    daily.insert(0, "data_carga", data_carga)

    final_cols = [
        "data_carga", "fonte_tabela", "ano", "mes", "dia", "data_ref", "nivel", "uf", "cidade", "safra", "ds_tipo_desconexao",
        "desc_total_mes", "rec_dia", "rec_acumulado", "perc_rec_acumulado", "meta_percentual", "meta_qtd",
        "gap_vol_acumulado", "gap_pp_acumulado", "faltam_recuperar", "dias_restantes", "necessario_por_dia",
    ]

    return daily[final_cols], ano_mes_base


# ============================================================
# MAIN
# ============================================================

def main():
    report: List[str] = []
    inicio = datetime.now()
    data_carga = date.today()

    report.append("# RELATÓRIO — CRIAR BASE PAINEL SAFRA")
    report.append(f"Data/hora: {inicio.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"ROOT: {ROOT}")
    report.append(f"DB_URL: {DB_URL}")
    report.append(f"COUNT_MODE: {COUNT_MODE}")
    report.append("")

    engine = None
    fonte_tabela = ""
    linhas_fonte = 0
    linhas_mensal = 0
    linhas_diario = 0
    ano_mes_base = ""

    try:
        engine = get_engine()
        criar_tabelas(engine)
        report.append("## TABELAS")
        report.append("- OK | Tabelas criadas/verificadas: safra_metas, safra_resumo_mensal, safra_resumo_diario, safra_carga_controle")
        report.append("")

        fonte_tabela = escolher_tabela_fonte(engine)
        report.append("## FONTE")
        report.append(f"- Tabela fonte selecionada: {fonte_tabela}")
        report.append("")

        df_raw = carregar_fonte(engine, fonte_tabela)
        linhas_fonte = len(df_raw)
        report.append("## CARGA DA FONTE")
        report.append(f"- Linhas carregadas da fonte: {linhas_fonte}")
        report.append("")

        df = preparar_base(df_raw, report)
        report.append("## BASE PREPARADA")
        report.append(f"- Linhas válidas após filtros Safra/Tipo/Data: {len(df)}")
        report.append(f"- Anos/Meses encontrados: {sorted([f'{a:04d}-{m:02d}' for a, m in set(zip(df['ANO'], df['MES']))])}")
        report.append(f"- Cidades encontradas: {df['CIDADE'].nunique()}")
        report.append(f"- UFs encontradas: {sorted(df['UF'].dropna().unique().tolist())}")
        report.append("")

        anos_meses = [(int(a), int(m)) for a, m in set(zip(df["ANO"], df["MES"]))]
        metas_processadas = upsert_metas(engine, anos_meses)
        report.append("## METAS")
        report.append(f"- Metas padrão processadas: {metas_processadas}")
        for meta in METAS_PADRAO:
            report.append(f"- {meta['SAFRA']} | {meta['DS_TIPO_DESCONEXAO']}: {meta['META_PERCENTUAL']}%")
        report.append("")

        mensal = montar_resumo_mensal(df, fonte_tabela, data_carga)
        diario, ano_mes_base = montar_resumo_diario(df, mensal, fonte_tabela, data_carga)

        linhas_mensal = len(mensal)
        linhas_diario = len(diario)

        limpar_snapshot_do_dia(engine, data_carga)

        if not mensal.empty:
            mensal.to_sql("safra_resumo_mensal", engine, if_exists="append", index=False, chunksize=5000, method="multi")

        if not diario.empty:
            diario.to_sql("safra_resumo_diario", engine, if_exists="append", index=False, chunksize=5000, method="multi")

        registrar_controle(
            engine,
            fonte_tabela=fonte_tabela,
            linhas_fonte=linhas_fonte,
            ano_mes_base=ano_mes_base,
            mensal=linhas_mensal,
            diario=linhas_diario,
            status="OK",
            mensagem="Base Painel Safra criada/atualizada com sucesso.",
        )

        report.append("## RESUMOS GERADOS")
        report.append(f"- safra_resumo_mensal: {linhas_mensal} linha(s) inserida(s) para data_carga={data_carga}")
        report.append(f"- safra_resumo_diario: {linhas_diario} linha(s) inserida(s) para mês-base={ano_mes_base} e data_carga={data_carga}")
        report.append("")

        if not mensal.empty:
            report.append("## AMOSTRA RNO MENSAL")
            amostra = mensal[mensal["nivel"] == "RNO"].head(12)
            for _, row in amostra.iterrows():
                report.append(
                    f"- {row['ano']}-{int(row['mes']):02d} | {row['safra']} | {row['ds_tipo_desconexao']} | "
                    f"DESC={row['desc_total']} | REC={row['rec_total']} | %={row['perc_rec']} | "
                    f"META={row['meta_percentual']} | GAP_VOL={row['gap_vol']} | GAP_PP={row['gap_pp']}"
                )
            report.append("")

        report.append("## STATUS FINAL")
        report.append("- Status: APROVADO")
        report.append("- Próximo passo recomendado: criar dash_safra.py e dash_safra.html consumindo safra_resumo_mensal, safra_resumo_diario e safra_metas.")

    except Exception as e:
        erro = traceback.format_exc()
        report.append("## ERRO")
        report.append(str(e))
        report.append("")
        report.append(erro)

        if engine is not None:
            try:
                registrar_controle(
                    engine,
                    fonte_tabela=fonte_tabela or "NÃO DEFINIDA",
                    linhas_fonte=linhas_fonte,
                    ano_mes_base=ano_mes_base,
                    mensal=linhas_mensal,
                    diario=linhas_diario,
                    status="ERRO",
                    mensagem=str(e),
                )
            except Exception:
                pass

    REPORT_FILE.write_text("\n".join(report), encoding="utf-8", newline="\n")
    print("\n".join(report))
    print("\n✅ Relatório gerado em:")
    print(REPORT_FILE)


if __name__ == "__main__":
    main()
