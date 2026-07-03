# -*- coding: utf-8 -*-
"""
dash_parceiras.py v4 - cache-safe + UF idempotente
"""
import json
import traceback
import pandas as pd
import plotly.express as px
import plotly.io as pio
from sqlalchemy import create_engine, text
from flask import Blueprint, render_template, request, jsonify

from data.db import load_table

bp = Blueprint(
    "dash_parceiras",
    __name__,
    url_prefix="/dash/parceiras",
    template_folder="templates",
)

CORES = {
    "red": "#E60000", "green": "#2E7D32",
    "blue": "#1565C0", "orange": "#F57C00",
    "yellow": "#F9A825", "gray": "#9E9E9E",
}

CATEGORICAL_COLS = [
    "SAFRA", "DS_TIPO_DESCONEXAO", "NM_CIDADE", "PENDENCIA",
    "TEM_TOA", "TEM_ANALITICO",
]

FILTER_FIELDS = ["UF", "SAFRA", "DS_TIPO_DESCONEXAO", "NM_CIDADE", "PENDENCIA"]

_DF_CACHE = {"df": None, "diag": {}}  # forcado reload v6


def get_engine():
    return create_engine("mysql+pymysql://root:@localhost:3306/safra")


def _load_cidades_uf_sql():
    try:
        eng = get_engine()
        df = pd.read_sql(text("SELECT CIDADE, UF FROM cidades_uf"), eng)
        eng.dispose()
        return df
    except Exception as e:
        print(f"[PARCEIRAS] SQL direto cidades_uf falhou: {e}")
        return pd.DataFrame(columns=["CIDADE", "UF"])


def get_df():
    if _DF_CACHE["df"] is not None:
        return _DF_CACHE["df"]

    diag = {}
    try:
        # COPY para nao mutar o cache compartilhado do load_table
        base = load_table("safra_enriquecida", categorical_cols=CATEGORICAL_COLS)
        df = base.copy() if base is not None and not base.empty else pd.DataFrame()
        diag["safra_rows"] = len(df)
        diag["safra_has_NM_CIDADE"] = "NM_CIDADE" in df.columns
        diag["safra_already_has_UF"] = "UF" in df.columns

        if df.empty:
            _DF_CACHE["df"] = df
            _DF_CACHE["diag"] = diag
            return df

        # Se ja tem UF (do v2 anterior cacheado), nao mexe
        if "UF" in df.columns:
            print("[PARCEIRAS] UF ja presente em safra_enriquecida - reutilizando.")
            df["UF"] = df["UF"].fillna("DESCONHECIDO").astype(str)
            diag["uf_source"] = "ja_existia"
        else:
            cid = _load_cidades_uf_sql()
            diag["cidades_uf_rows"] = len(cid)
            diag["cidades_uf_cols"] = list(cid.columns)

            if (not cid.empty
                and "CIDADE" in cid.columns
                and "UF" in cid.columns
                and "NM_CIDADE" in df.columns):

                cid = cid[["CIDADE", "UF"]].copy()
                cid["CIDADE"] = cid["CIDADE"].astype(str).str.strip().str.upper()
                cid["UF"]     = cid["UF"].astype(str).str.strip().str.upper()
                cid = cid.drop_duplicates(subset=["CIDADE"])

                df["_KEY_CID"] = df["NM_CIDADE"].astype(str).str.strip().str.upper()
                cid = cid.rename(columns={"CIDADE": "_KEY_CID"})

                df = df.merge(cid, how="left", on="_KEY_CID")
                df = df.drop(columns=["_KEY_CID"])
                df["UF"] = df["UF"].fillna("DESCONHECIDO").astype(str)
                diag["uf_source"] = "merge_ok"
            else:
                df["UF"] = "DESCONHECIDO"
                diag["uf_source"] = "fallback_desconhecido"

        diag["uf_unicos"] = sorted(df["UF"].astype(str).unique().tolist())
        diag["uf_value_counts"] = df["UF"].astype(str).value_counts().head(10).to_dict()

        _DF_CACHE["df"] = df
        _DF_CACHE["diag"] = diag
        print(f"[PARCEIRAS] OK | linhas={len(df)} | UF unicos={diag['uf_unicos']}")
        return df

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[PARCEIRAS] ERRO em get_df:\n{tb}")
        _DF_CACHE["diag"] = {"error": str(e), "traceback": tb}
        return pd.DataFrame()


def parse_multi(val):
    if not val:
        return []
    return [v for v in val.split("||") if v]


def estilo(fig, titulo="", height=350):
    fig.update_layout(
        title=dict(text=titulo, font=dict(size=14, color="#333"), x=0.01),
        template="plotly_white", height=height,
        margin=dict(l=20, r=20, t=50, b=20),
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family="Segoe UI", size=11),
        legend=dict(font_size=10, orientation="h",
                    yanchor="bottom", y=-0.25, x=0.5, xanchor="center"),
    )
    return fig


def fig_to_json(fig):
    return json.loads(pio.to_json(fig))


def safe_unique(series):
    """Retorna valores unicos como lista de strings, sem NaN/vazios."""
    try:
        vals = series.dropna().astype(str).unique().tolist()
        return sorted([v for v in vals if v and v.lower() not in ("nan", "none")])
    except Exception:
        return []


# -------------------------------------------------------------
@bp.route("/")
def index():
    return render_template("dash_parceiras.html")


@bp.route("/api/debug")
def api_debug():
    """Devolve diagnostico SEM crashar mesmo se get_df() falhar."""
    try:
        df = get_df()
        info = dict(_DF_CACHE.get("diag", {}))
        info["total_rows"] = len(df)
        info["all_cols"]   = list(df.columns) if not df.empty else []
        if not df.empty and "TOA_STATUS" in df.columns:
            s = df["TOA_STATUS"].astype(str).str.strip()
            info["toa_status_counts"] = s.value_counts().head(15).to_dict()
            info["toa_status_vazio"]  = int(((s == "") |
                                             (s.str.lower() == "nan") |
                                             (s.str.lower() == "none")).sum())
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/refresh")
def api_refresh():
    try:
        df_full = get_df()
        if df_full is None or df_full.empty:
            return jsonify({
                "empty": True,
                "options": {f: [] for f in FILTER_FIELDS},
                "error": _DF_CACHE.get("diag", {}).get("error"),
            })

        filters = {f: parse_multi(request.args.get(f, "")) for f in FILTER_FIELDS}

        options = {}
        df_cascade = df_full
        for f in FILTER_FIELDS:
            if f in df_cascade.columns:
                options[f] = safe_unique(df_cascade[f])
            else:
                options[f] = []
            if filters.get(f) and f in df_cascade.columns:
                df_cascade = df_cascade[
                    df_cascade[f].astype(str).isin(filters[f])
                ]

        df = df_cascade
        if df.empty:
            return jsonify({"empty": True, "options": options})

        # ---------------- KPIs ----------------
        total = len(df)
        tem_anl  = int((df["TEM_ANALITICO"].astype(str) == "SIM").sum())   if "TEM_ANALITICO" in df.columns else 0
        n_parc   = int(df["PARCEIRA_NOME"].dropna().nunique())             if "PARCEIRA_NOME"  in df.columns else 0
        recup    = int((df["PENDENCIA"].astype(str) == "RECUPERADO").sum()) if "PENDENCIA"     in df.columns else 0
        pct_rec  = round(recup / total * 100, 1) if total > 0 else 0
        pend_toa = int(len(df[(df["PENDENCIA"].astype(str) == "PENDENTE") &
                              (df["TEM_TOA"].astype(str) == "SIM")])) \
                   if all(c in df.columns for c in ["PENDENCIA", "TEM_TOA"]) else 0

        kpis = {
            "tem_analitico": tem_anl, "parceiras": n_parc,
            "pct_recuperacao": pct_rec, "pend_toa": pend_toa,
        }

        figs = {}
        df_p = df[df["PARCEIRA_NOME"].notna()].copy() if "PARCEIRA_NOME" in df.columns else df.head(0)
        if not df_p.empty and "PARCEIRA_NOME" in df_p.columns:
            df_p["PARCEIRA_NOME"] = df_p["PARCEIRA_NOME"].astype(str)
        print(f"[PARCEIRAS] df_p shape={df_p.shape}, parceiras unicas={df_p['PARCEIRA_NOME'].nunique() if not df_p.empty else 0}")

        # G1
        if not df_p.empty and "PENDENCIA" in df_p.columns:
            d1t = df_p.groupby("PARCEIRA_NOME", observed=False).size().reset_index(name="TOT")
            d1r = df_p[df_p["PENDENCIA"].astype(str) == "RECUPERADO"] \
                    .groupby("PARCEIRA_NOME", observed=False).size().reset_index(name="REC")
            d1 = d1t.merge(d1r, on="PARCEIRA_NOME", how="left").fillna(0)
            d1["PCT"] = (d1["REC"] / d1["TOT"] * 100).round(1)
            d1 = d1.sort_values("PCT", ascending=True)
            fig = px.bar(d1, x="PCT", y="PARCEIRA_NOME", orientation="h",
                         color="PCT",
                         color_continuous_scale=["#E60000", "#F9A825", "#2E7D32"])
            fig.update_traces(texttemplate="%{x:.1f}%",
                              textposition="outside", textfont_size=11)
            fig.update_layout(coloraxis_showscale=False,
                              xaxis_title="% Recuperacao", yaxis_title="")
            figs["g1"] = fig_to_json(estilo(fig, "% Recuperacao por Parceira", 400))

        # G2
        if not df_p.empty:
            d2 = df_p.groupby("PARCEIRA_NOME", observed=False).size().reset_index(name="QTD")
            d2 = d2.sort_values("QTD", ascending=True)
            fig = px.bar(d2, x="QTD", y="PARCEIRA_NOME", orientation="h",
                         color_discrete_sequence=[CORES["blue"]])
            fig.update_traces(texttemplate="%{x:,}",
                              textposition="outside", textfont_size=11)
            fig.update_layout(xaxis_title="Volume", yaxis_title="")
            figs["g2"] = fig_to_json(estilo(fig, "Volume de Contratos por Parceira", 400))

        # G3
        if not df_p.empty and "SAFRA" in df_p.columns and "PENDENCIA" in df_p.columns:
            d3r = df_p[df_p["PENDENCIA"].astype(str) == "RECUPERADO"] \
                    .groupby(["PARCEIRA_NOME", "SAFRA"], observed=False).size().reset_index(name="REC")
            d3t = df_p.groupby(["PARCEIRA_NOME", "SAFRA"], observed=False).size().reset_index(name="TOT")
            d3 = d3t.merge(d3r, on=["PARCEIRA_NOME", "SAFRA"], how="left").fillna(0)
            d3["PCT"] = (d3["REC"] / d3["TOT"] * 100).round(1)
            fig = px.bar(d3, x="PARCEIRA_NOME", y="PCT", color="SAFRA",
                         barmode="group",
                         color_discrete_sequence=[CORES["blue"], CORES["orange"],
                                                  CORES["red"], CORES["green"]])
            fig.update_traces(texttemplate="%{y:.1f}%",
                              textposition="outside", textfont_size=9)
            fig.update_layout(xaxis_title="", yaxis_title="% Recuperacao")
            figs["g3"] = fig_to_json(estilo(fig, "% Recuperacao: Parceira x SAFRA", 400))

        # G4
        if not df_p.empty and "DS_TIPO_DESCONEXAO" in df_p.columns and "PENDENCIA" in df_p.columns:
            d4r = df_p[df_p["PENDENCIA"].astype(str) == "RECUPERADO"] \
                    .groupby(["PARCEIRA_NOME", "DS_TIPO_DESCONEXAO"], observed=False).size().reset_index(name="REC")
            d4t = df_p.groupby(["PARCEIRA_NOME", "DS_TIPO_DESCONEXAO"], observed=False).size().reset_index(name="TOT")
            d4 = d4t.merge(d4r, on=["PARCEIRA_NOME", "DS_TIPO_DESCONEXAO"], how="left").fillna(0)
            d4["PCT"] = (d4["REC"] / d4["TOT"] * 100).round(1)
            cm4 = {v: (CORES["blue"] if "OP" in str(v).upper() else CORES["orange"])
                   for v in d4["DS_TIPO_DESCONEXAO"].unique()}
            fig = px.bar(d4, x="PARCEIRA_NOME", y="PCT",
                         color="DS_TIPO_DESCONEXAO", barmode="group",
                         color_discrete_map=cm4)
            fig.update_traces(texttemplate="%{y:.1f}%",
                              textposition="outside", textfont_size=9)
            fig.update_layout(xaxis_title="", yaxis_title="% Recuperacao")
            figs["g4"] = fig_to_json(estilo(fig, "% Recuperacao: Parceira x Tipo Desconexao", 400))

        # G5
        if not df_p.empty and "PENDENCIA" in df_p.columns:
            d5src = df_p[df_p["PENDENCIA"].astype(str) == "PENDENTE"]
            if not d5src.empty:
                d5 = d5src.groupby("PARCEIRA_NOME", observed=False).size().reset_index(name="QTD")
                d5 = d5.sort_values("QTD", ascending=True)
                fig = px.bar(d5, x="QTD", y="PARCEIRA_NOME", orientation="h",
                             color_discrete_sequence=[CORES["red"]])
                fig.update_traces(texttemplate="%{x:,}",
                                  textposition="outside", textfont_size=11)
                fig.update_layout(xaxis_title="Pendentes", yaxis_title="")
                figs["g5"] = fig_to_json(estilo(fig, "Parceiras com mais Pendentes", 400))

        # G6 - Status TOA (filtra vazios)
        if not df_p.empty and "TOA_STATUS" in df_p.columns:
            s = df_p["TOA_STATUS"].astype(str).str.strip()
            mask = s.notna() & (s != "") & (s.str.lower() != "nan") & (s.str.lower() != "none")
            d6src = df_p[mask]
            if not d6src.empty:
                d6 = d6src.groupby(["PARCEIRA_NOME", "TOA_STATUS"],
                                   observed=True).size().reset_index(name="QTD")
                fig = px.bar(d6, x="PARCEIRA_NOME", y="QTD",
                             color="TOA_STATUS", barmode="stack")
                fig.update_traces(texttemplate="%{y:,}",
                                  textposition="inside", textfont_size=10,
                                  textfont_color="white")
                fig.update_layout(xaxis_title="", legend_title="",
                                  yaxis_title="Volume")
                figs["g6"] = fig_to_json(estilo(fig, "Status TOA por Parceira", 400))

        return jsonify({"empty": False, "options": options, "kpis": kpis, "figs": figs})

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[PARCEIRAS] ERRO em api_refresh:\n{tb}")
        return jsonify({"empty": True, "error": str(e), "traceback": tb,
                        "options": {f: [] for f in FILTER_FIELDS}}), 500
