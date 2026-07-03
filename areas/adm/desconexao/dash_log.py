# -*- coding: utf-8 -*-
"""
Dashboard LOG & Reincidência — Portal Operações RNO

Correção definitiva:
- API retorna payload simples.
- O frontend renderiza os gráficos com Plotly.js.
- Evita problemas de JSON Plotly complexo, template, bdata/dtype e gráficos vazios quebrados.

Rotas:
- /dash/log/
- /dash/log/api/options
- /dash/log/api/data
"""

import pandas as pd
from flask import Blueprint, render_template, jsonify, request

from data.db import load_table


bp = Blueprint(
    "dash_log",
    __name__,
    url_prefix="/dash/log",
    template_folder="templates",
)

TABLE = "safra_enriquecida"

FILTROS_CASCATA = [
    "SAFRA",
    "DS_TIPO_DESCONEXAO",
    "NM_CIDADE",
    "PENDENCIA",
]

CATEGORICAL_COLS = [
    "SAFRA",
    "DS_TIPO_DESCONEXAO",
    "NM_CIDADE",
    "PENDENCIA",
    "FAIXA_LOG",
    "ANL_MOTIVO_REAGENDA",
    "ANL_QUEBRA_RESPONSAVEL",
    "ANL_QUEBRA_CENARIO",
    "ANL_TIPO_TRATAMENTO",
    "LOG_ULT_TIPO_OS",
]

FAIXA_SEM_LOG = "SEM LOG"
FAIXA_CRITICA = "6x+"
ORDEM_FAIXA_LOG = ["SEM LOG", "1x", "2-3x", "4-5x", "6x+"]


def prepare_df():
    try:
        df = load_table(TABLE, categorical_cols=CATEGORICAL_COLS)
    except TypeError:
        df = load_table(TABLE)

    if df is None:
        df = pd.DataFrame()

    for col in CATEGORICAL_COLS:
        if col not in df.columns:
            df[col] = ""

    for col in CATEGORICAL_COLS:
        df[col] = df[col].fillna("").astype(str).str.strip()

    return df


def limpar_valores(vals):
    saida = []

    for v in vals or []:
        s = str(v).strip()
        if s and s.lower() != "nan":
            saida.append(s)

    return saida


def apply_filters(df, filters):
    if df is None or df.empty:
        return df

    dff = df.copy()

    for col, vals in filters.items():
        vals = limpar_valores(vals)
        if col in dff.columns and vals:
            dff = dff[dff[col].fillna("").astype(str).isin(vals)]

    return dff


def get_options(df, col):
    if df is None or df.empty or col not in df.columns:
        return []

    s = df[col].dropna().astype(str).str.strip()
    s = s[(s != "") & (s.str.lower() != "nan")]

    return sorted(s.unique().tolist())


def count_col(df, col, top=None, keep_order=None):
    if df is None or df.empty or col not in df.columns:
        return {
            "labels": [],
            "values": [],
        }

    s = df[col].fillna("").astype(str).str.strip()
    s = s[(s != "") & (s.str.lower() != "nan")]

    if s.empty:
        return {
            "labels": [],
            "values": [],
        }

    vc = s.value_counts()

    if keep_order:
        labels = [x for x in keep_order if x in vc.index]
        values = [int(vc.get(x, 0)) for x in labels]
    else:
        if top:
            vc = vc.head(top)
        labels = vc.index.astype(str).tolist()
        values = [int(x) for x in vc.values.tolist()]

    return {
        "labels": labels,
        "values": values,
    }


def montar_kpis(df):
    total = int(len(df)) if df is not None else 0

    if df is None or df.empty or "FAIXA_LOG" not in df.columns:
        return {
            "total": total,
            "com_log": 0,
            "sem_log": 0,
            "criticos": 0,
            "pct_log": 0,
        }

    faixa = df["FAIXA_LOG"].fillna("").astype(str).str.strip()

    sem_log = int((faixa == FAIXA_SEM_LOG).sum())
    com_log = int(((faixa != "") & (faixa != FAIXA_SEM_LOG)).sum())
    criticos = int((faixa == FAIXA_CRITICA).sum())
    pct_log = round((com_log / total) * 100, 1) if total else 0

    return {
        "total": total,
        "com_log": com_log,
        "sem_log": sem_log,
        "criticos": criticos,
        "pct_log": pct_log,
    }


def chart_com_sem_log(df):
    if df is None or df.empty or "FAIXA_LOG" not in df.columns:
        return {
            "labels": [],
            "values": [],
        }

    faixa = df["FAIXA_LOG"].fillna("").astype(str).str.strip()

    sem_log = int((faixa == FAIXA_SEM_LOG).sum())
    com_log = int(((faixa != "") & (faixa != FAIXA_SEM_LOG)).sum())

    return {
        "labels": ["COM LOG", "SEM LOG"],
        "values": [com_log, sem_log],
    }


def chart_tipo_log(df):
    if df is None or df.empty:
        return {
            "labels": [],
            "series": {
                "COM LOG": [],
                "SEM LOG": [],
            },
            "totals": [],
        }

    if "DS_TIPO_DESCONEXAO" not in df.columns or "FAIXA_LOG" not in df.columns:
        return {
            "labels": [],
            "series": {
                "COM LOG": [],
                "SEM LOG": [],
            },
            "totals": [],
        }

    dff = df.copy()
    dff["STATUS_LOG"] = dff["FAIXA_LOG"].apply(
        lambda x: "SEM LOG" if str(x).strip() == FAIXA_SEM_LOG else "COM LOG"
    )

    base = (
        dff.groupby(["DS_TIPO_DESCONEXAO", "STATUS_LOG"], observed=False)
        .size()
        .reset_index(name="QTDE")
    )

    base = base[
        (base["DS_TIPO_DESCONEXAO"].astype(str).str.strip() != "")
        & (base["QTDE"] > 0)
    ]

    if base.empty:
        return {
            "labels": [],
            "series": {
                "COM LOG": [],
                "SEM LOG": [],
            },
            "totals": [],
        }

    totais = (
        base.groupby("DS_TIPO_DESCONEXAO", observed=False)["QTDE"]
        .sum()
        .sort_values(ascending=True)
    )

    labels = totais.index.astype(str).tolist()

    series = {
        "COM LOG": [],
        "SEM LOG": [],
    }

    for label in labels:
        rec = base[base["DS_TIPO_DESCONEXAO"] == label]
        for status in ["COM LOG", "SEM LOG"]:
            valor = rec.loc[rec["STATUS_LOG"] == status, "QTDE"]
            series[status].append(int(valor.iloc[0]) if len(valor) else 0)

    return {
        "labels": labels,
        "series": series,
        "totals": [int(x) for x in totais.values.tolist()],
    }


def chart_cidades_com_log(df, top=15):
    if df is None or df.empty:
        return {
            "labels": [],
            "values": [],
        }

    if "NM_CIDADE" not in df.columns or "FAIXA_LOG" not in df.columns:
        return {
            "labels": [],
            "values": [],
        }

    dff = df.copy()
    dff["COM_LOG_FLAG"] = dff["FAIXA_LOG"].apply(
        lambda x: 1 if str(x).strip() not in ["", FAIXA_SEM_LOG] else 0
    )

    base = (
        dff.groupby("NM_CIDADE", observed=False)["COM_LOG_FLAG"]
        .sum()
        .sort_values(ascending=False)
        .head(top)
    )

    base = base[base > 0]

    if base.empty:
        return {
            "labels": [],
            "values": [],
        }

    # horizontal: menor em cima ou maior em cima? Plotly horizontal exibe na ordem.
    base = base.sort_values(ascending=True)

    return {
        "labels": base.index.astype(str).tolist(),
        "values": [int(x) for x in base.values.tolist()],
    }




def count_col_fallback(df, candidatos, top=12, empty_title="Sem preenchimento no analítico"):
    """
    Tenta montar um gráfico usando a primeira coluna candidata com dados reais.

    Importante:
    - Esta função NÃO deve receber colunas genéricas como FAIXA_LOG ou NM_CIDADE
      quando estiver alimentando a seção MOTIVOS E RESPONSÁVEIS.
    - Se nenhuma coluna candidata tiver dados, retorna uma barra cinza informativa,
      em vez de duplicar gráficos de outras seções.

    Retorno:
    {
      "title": "...",
      "source_col": "...",
      "labels": [...],
      "values": [...],
      "is_fallback_empty": true/false
    }
    """
    valores_invalidos = {
        "",
        "nan",
        "none",
        "null",
        "na",
        "n/a",
        "não informado",
        "nao informado",
        "sem informação",
        "sem informacao",
        "sem dados",
        "sem analitico",
        "sem analítico",
    }

    for col, titulo in candidatos:
        if df is None or df.empty or col not in df.columns:
            continue

        s = df[col].fillna("").astype(str).str.strip()
        s_valid = s[~s.str.lower().isin(valores_invalidos)]

        if s_valid.empty:
            continue

        vc = s_valid.value_counts().head(top)

        labels = vc.index.astype(str).tolist()
        values = [int(x) for x in vc.values.tolist()]

        if labels and values:
            return {
                "title": titulo,
                "source_col": col,
                "labels": labels,
                "values": values,
                "is_fallback_empty": False,
            }

    total = int(len(df)) if df is not None else 0

    return {
        "title": empty_title,
        "source_col": "",
        "labels": ["Sem preenchimento no analítico"],
        "values": [total],
        "is_fallback_empty": True,
    }

def montar_charts(df):
    return {
        "g1_faixa_log": count_col(
            df,
            "FAIXA_LOG",
            keep_order=ORDEM_FAIXA_LOG,
        ),
        "g2_com_sem_log": chart_com_sem_log(df),

        # G3 — Motivos/Cenários/Tratamento.
        # Não usar FAIXA_LOG aqui para não duplicar a seção Distribuição do LOG.
        "g3_motivos": count_col_fallback(
            df,
            [
                ("ANL_MOTIVO_REAGENDA", "Motivos de Reagenda"),
                ("ANL_QUEBRA_CENARIO", "Cenários de Quebra"),
                ("ANL_TIPO_TRATAMENTO", "Tipos de Tratamento"),
                ("LOG_ULT_TIPO_OS", "Último Tipo de OS LOG"),
            ],
            top=12,
            empty_title="Motivos — sem preenchimento no analítico",
        ),

        # G4 — Responsáveis.
        # Não usar NM_CIDADE aqui para não duplicar a seção de Cidades.
        "g4_responsaveis": count_col_fallback(
            df,
            [
                ("ANL_QUEBRA_RESPONSAVEL", "Responsáveis pela Quebra"),
            ],
            top=12,
            empty_title="Responsáveis — sem preenchimento no analítico",
        ),

        "g5_tipo_log": chart_tipo_log(df),
        "g6_cidades_log": chart_cidades_com_log(df, top=15),
    }


@bp.route("/")
def index():
    return render_template("dash_log.html")


@bp.route("/api/options")
def api_options():
    try:
        df = prepare_df()
        selected = {col: request.args.getlist(col) for col in FILTROS_CASCATA}

        payload = {}

        for alvo in FILTROS_CASCATA:
            dfx = df.copy()

            for col, vals in selected.items():
                if col == alvo:
                    continue

                vals = limpar_valores(vals)
                if col in dfx.columns and vals:
                    dfx = dfx[dfx[col].fillna("").astype(str).isin(vals)]

            payload[alvo] = get_options(dfx, alvo)

        return jsonify(payload)

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": True,
            "endpoint": "/dash/log/api/options",
            "message": str(e),
        }), 500


@bp.route("/api/data")
def api_data():
    try:
        df = prepare_df()
        filters = {col: request.args.getlist(col) for col in FILTROS_CASCATA}
        dff = apply_filters(df, filters)

        payload = {
            "ok": True,
            "kpis": montar_kpis(dff),
            "charts": montar_charts(dff),
            "total_linhas_cache": int(len(df)) if df is not None else 0,
            "total_linhas_filtrado": int(len(dff)) if dff is not None else 0,
        }

        return jsonify(payload)

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": True,
            "endpoint": "/dash/log/api/data",
            "message": str(e),
        }), 500
