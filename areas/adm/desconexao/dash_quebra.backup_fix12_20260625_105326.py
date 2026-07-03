# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, jsonify, request
import pandas as pd
import numpy as np
import traceback
import time
import threading
from sqlalchemy import create_engine

bp_quebra = Blueprint("quebra", __name__,
    url_prefix="/dash/quebra", template_folder="templates")

DB_URL = "mysql+pymysql://root:@localhost:3306/safra"
TABLE = "quebra_total"

PAL = {
    "white":"#FFFFFF","bg":"#F8F9FA","border":"#E9ECEF",
    "muted":"#6C757D","dark":"#343A40","gray":"#ADB5BD","grayD":"#495057",
    "red":"#E60000","redD":"#B71C1C",
    "green":"#2E7D32","yellow":"#F9A825","blue":"#1976D2",
}

COLS = ["NR_CONTRATO","NM_CIDADE","UF","DT_AGENDA",
        "ANO","MES","DIA",
        "NM_TIPO_TRATAMENTO","NM_MOTIVO_REAGENDA",
        "NM_QUEBRA_RESPONSAVEL","PARCEIRA_NOME"]

FILTER_COLS = {
    "anos":"ANO","meses":"MES","dias":"DIA",
    "ufs":"UF","cids":"NM_CIDADE","parcs":"PARCEIRA_NOME",
}

# Mapeamento grafico -> filtro a EXCLUIR (eixo livre)
EXCLUDE_MAP = {
    "g1":"dias","g2":"meses","g3":"cids",
    "g4":None,"g5":"parcs","g6":None,
}

_LOCK = threading.Lock()
_STATE = {"df":None,"loading":False,"load_time":None,
          "load_error":None,"diag":{}}

def _load_df_sync():
    with _LOCK:
        if _STATE["df"] is not None: return _STATE["df"]
        if _STATE["loading"]: return None
        _STATE["loading"] = True
    try:
        t0 = time.time()
        engine = create_engine(DB_URL)
        sql = f"SELECT {', '.join(COLS)} FROM {TABLE}"
        df = pd.read_sql(sql, engine, dtype="string")
        engine.dispose()
        for c in df.columns:
            df[c] = df[c].fillna("").str.strip()
        df["IS_QUEBRA"] = df["NM_TIPO_TRATAMENTO"].str.contains(
            "COM QUEBRA", case=False, na=False)
        df["DT_LIMPO"] = df["DT_AGENDA"].str[:10]
        df["DT_SORT"] = pd.to_datetime(df["DT_LIMPO"],
            format="%d/%m/%Y", errors="coerce")
        total = time.time() - t0
        mem_mb = round(df.memory_usage(deep=True).sum()/1024**2, 1)
        _STATE["df"] = df
        _STATE["load_time"] = total
        _STATE["diag"] = {"linhas":int(len(df)),"mem_mb":mem_mb,
            "tempo_s":round(total,2)}
        print(f"[QUEBRA] Cache OK: {len(df):,} linhas, {mem_mb}MB, {total:.1f}s")
        return df
    except Exception as e:
        _STATE["load_error"] = str(e); raise
    finally:
        _STATE["loading"] = False

def _warmup_async():
    threading.Thread(target=_load_df_sync, daemon=True).start()

@bp_quebra.before_request
def _ensure_warm():
    if _STATE["df"] is None and not _STATE["loading"]:
        _warmup_async()

def _fmt(n):
    try: return f"{int(n):,}".replace(",", ".")
    except: return str(n)

def _fmt_pct(p):
    return f"{p:.1f}%".replace(".", ",")

def _opts(s):
    if s is None or len(s) == 0: return []
    vals = sorted({v for v in s.astype(str)
                   if v and v.strip() and v.lower() != "nan"})
    return [{"v": v, "l": v} for v in vals]

def _filter_df(df, filters, exclude_key=None):
    out = df
    for key, col in FILTER_COLS.items():
        if key == exclude_key: continue
        vals = filters.get(key) or []
        if vals:
            out = out[out[col].isin(vals)]
    return out

def _build_options(df, filters):
    options = {}
    for key, col in FILTER_COLS.items():
        d = _filter_df(df, filters, exclude_key=key)
        options[key] = _opts(d[col])
    return options

def _layout(t, h=380, **kw):
    return {
        "title":{"text":f"<b>{t}</b>",
                 "font":{"size":14,"color":PAL["dark"],"family":"Segoe UI"},
                 "x":0.01,"xanchor":"left"},
        "template":"plotly_white","height":h,
        "margin":{"l":kw.get("l",60),"r":kw.get("r",30),
                  "t":kw.get("t",55),"b":kw.get("b",50)},
        "plot_bgcolor":PAL["white"],"paper_bgcolor":PAL["white"],
        "font":{"family":"Segoe UI","size":11,"color":PAL["grayD"]},
        "showlegend":False,
        "hoverlabel":{"bgcolor":PAL["dark"],"font":{"color":"#fff",
            "family":"Segoe UI","size":12},"bordercolor":PAL["dark"]},
    }

def _empty(msg="Sem dados"):
    return {"data":[],"layout":{**_layout("",350),
        "annotations":[{"text":msg,"showarrow":False,
            "font":{"size":15,"color":PAL["gray"],"family":"Segoe UI"},
            "xref":"paper","yref":"paper","x":0.5,"y":0.5}]}}

def _trunc(s, n=28):
    s = str(s)
    return (s[:n-1] + "...") if len(s) > n else s

def _agrega(df, group_col, only_quebra=False):
    """Retorna DataFrame com TOTAL, QTD, TAXA (quebras/total cat), REP (quebras/total geral)."""
    total_geral = max(int(df.shape[0]), 1)
    if only_quebra:
        d = df[df["IS_QUEBRA"]]
        d = d[d[group_col] != ""]
        if d.empty:
            return pd.DataFrame(columns=[group_col,"TOTAL","QTD","TAXA","REP"])
        g = d.groupby(group_col, as_index=False).size().rename(
            columns={"size":"QTD"})
        total_quebras_grupo = max(int(g["QTD"].sum()), 1)
        g["TOTAL"] = g["QTD"]
        g["TAXA"] = (g["QTD"]/total_quebras_grupo*100).round(1)
        g["REP"] = (g["QTD"]/total_geral*100).round(1)
        return g
    d = df[df[group_col] != ""] if group_col != "DT_LIMPO" else df.dropna(
        subset=["DT_SORT"])
    if d.empty:
        return pd.DataFrame(columns=[group_col,"TOTAL","QTD","TAXA","REP"])
    g = d.groupby(group_col, as_index=False).agg(
        TOTAL=(group_col,"size"),
        QTD=("IS_QUEBRA","sum"))
    g["QTD"] = g["QTD"].astype(int)
    g["TAXA"] = np.where(g["TOTAL"]>0,
        (g["QTD"]/g["TOTAL"]*100).round(1), 0.0)
    g["REP"] = (g["QTD"]/total_geral*100).round(1)
    return g

def _vals(g, mode):
    """Retorna (valores_x_ou_y, textos, suffix)."""
    if mode == "taxa":
        return g["TAXA"].tolist(), [_fmt_pct(p) for p in g["TAXA"]], "%"
    if mode == "rep":
        return g["REP"].tolist(), [_fmt_pct(p) for p in g["REP"]], "%"
    return g["QTD"].tolist(), [_fmt(v) for v in g["QTD"]], ""

# ===== Hover universal =====
HOVER = ("<b>%{customdata}</b><br>"
    "Total OS: <b>%{customdata,}</b><br>"
    "Quebras: <b>%{customdata,}</b><br>"
    "Taxa: <b>%{customdata:.1f}%%</b><br>"
    "Representatividade: <b>%{customdata:.1f}%%</b>"
    "<extra></extra>")

# ===== G1: Evolucao diaria =====
def _g1(df, mode="qtd"):
    g = _agrega(df, "DT_LIMPO", only_quebra=False)
    if g.empty: return _empty()
    # ordena por data
    g["DT_SORT"] = pd.to_datetime(g["DT_LIMPO"], format="%d/%m/%Y",
        errors="coerce")
    g = g.dropna(subset=["DT_SORT"]).sort_values("DT_SORT")
    n = len(g)
    cores = [PAL["grayD"]] * (n-1) + [PAL["red"]] if n > 0 else []
    y, texto, suffix = _vals(g, mode)
    custom = list(zip(g["DT_LIMPO"].tolist(), g["TOTAL"].tolist(),
                      g["QTD"].tolist(), g["TAXA"].tolist(),
                      g["REP"].tolist()))
    ytitle = {"qtd":"Quebras","taxa":"Taxa de quebra","rep":"Representatividade"}[mode]
    return {"data":[{"type":"bar","x":g["DT_LIMPO"].tolist(),"y":y,
        "text":texto,"textposition":"outside",
        "textfont":{"size":9,"color":PAL["dark"]},
        "marker":{"color":cores,"line":{"width":0}},
        "customdata":custom,"hovertemplate":HOVER}],
        "layout":{**_layout("Evolucao Diaria de Quebras",420,b=80),
            "xaxis":{"gridcolor":PAL["border"],"linecolor":PAL["border"],
                "tickfont":{"color":PAL["muted"],"size":9},
                "tickangle":-45,"nticks":min(n,15),
                "showgrid":False,"zeroline":False},
            "yaxis":{"gridcolor":PAL["border"],"linecolor":"rgba(0,0,0,0)",
                "tickfont":{"color":PAL["muted"],"size":10},
                "showgrid":True,"zeroline":False,"ticksuffix":suffix,
                "title":{"text":ytitle,
                    "font":{"size":10,"color":PAL["muted"]}}}}}

# ===== G2: por mes =====
def _g2(df, mode="qtd"):
    g = _agrega(df, "MES", only_quebra=False).sort_values("MES")
    if g.empty: return _empty()
    n = len(g)
    max_idx = (g["QTD"] if mode=="qtd" else g["TAXA"]
        if mode=="taxa" else g["REP"]).idxmax()
    cores = [PAL["red"] if i == max_idx else PAL["grayD"] for i in g.index]
    y, texto, suffix = _vals(g, mode)
    custom = list(zip(g["MES"].tolist(), g["TOTAL"].tolist(),
                      g["QTD"].tolist(), g["TAXA"].tolist(),
                      g["REP"].tolist()))
    return {"data":[{"type":"bar","x":g["MES"].tolist(),"y":y,
        "text":texto,"textposition":"outside",
        "textfont":{"size":11,"color":PAL["dark"]},
        "marker":{"color":cores,"line":{"width":0}},
        "customdata":custom,"hovertemplate":HOVER.replace("%{customdata}","Mes %{customdata}")}],
        "layout":{**_layout("Quebras por Mes",420),
            "xaxis":{"type":"category","tickangle":0,
                "gridcolor":PAL["border"],"linecolor":PAL["border"],
                "tickfont":{"color":PAL["muted"],"size":11},
                "showgrid":False,"zeroline":False},
            "yaxis":{"gridcolor":PAL["border"],"linecolor":"rgba(0,0,0,0)",
                "tickfont":{"color":PAL["muted"],"size":10},
                "showgrid":True,"zeroline":False,"ticksuffix":suffix}}}

# ===== G3: top cidades =====
def _g3(df, mode="qtd"):
    g = _agrega(df, "NM_CIDADE", only_quebra=False)
    if g.empty: return _empty()
    if mode == "taxa":
        # filtra para evitar distorcao (cidade com 1 OS = 100%)
        g_f = g[g["TOTAL"] >= 30]
        g = (g_f if not g_f.empty else g).nlargest(10,"TAXA").sort_values("TAXA")
    elif mode == "rep":
        g = g.nlargest(10,"REP").sort_values("REP")
    else:
        g = g.nlargest(10,"QTD").sort_values("QTD")
    if g.empty: return _empty()
    n = len(g)
    cores = []
    for i in range(n):
        rank = n - 1 - i
        if rank == 0:   cores.append(PAL["red"])
        elif rank <= 2: cores.append(PAL["redD"])
        else:           cores.append(PAL["grayD"])
    labels = [_trunc(c, 22) for c in g["NM_CIDADE"].tolist()]
    x, texto, suffix = _vals(g, mode)
    custom = list(zip(g["NM_CIDADE"].tolist(), g["TOTAL"].tolist(),
                      g["QTD"].tolist(), g["TAXA"].tolist(),
                      g["REP"].tolist()))
    return {"data":[{"type":"bar","orientation":"h",
        "x":x,"y":labels,"text":texto,"textposition":"outside",
        "textfont":{"size":11,"color":PAL["dark"]},
        "marker":{"color":cores,"line":{"width":0}},
        "customdata":custom,"hovertemplate":HOVER}],
        "layout":{**_layout("Top 10 Cidades com Quebra",420,l=160,r=60),
            "xaxis":{"gridcolor":PAL["border"],"linecolor":PAL["border"],
                "tickfont":{"color":PAL["muted"],"size":10},
                "showgrid":True,"zeroline":False,"ticksuffix":suffix}}}

# ===== G4: top motivos (so quebra) =====
def _g4(df, mode="qtd"):
    d = df[df["IS_QUEBRA"]]
    m = (d["NM_MOTIVO_REAGENDA"]!="") & (
        ~d["NM_MOTIVO_REAGENDA"].str.lower().str.contains(
            "nao informado|n.o informado",na=False,regex=True))
    d_filt = d[m]
    if d_filt.empty: return _empty("Sem motivos informados")
    # Para G4: TAXA = distribuicao interna nos motivos; REP = sobre total geral
    g = d_filt.groupby("NM_MOTIVO_REAGENDA",as_index=False).size().rename(
        columns={"size":"QTD"})
    total_motivos = max(int(g["QTD"].sum()), 1)
    total_geral = max(int(df.shape[0]), 1)
    g["TOTAL"] = g["QTD"]
    g["TAXA"] = (g["QTD"]/total_motivos*100).round(1)
    g["REP"] = (g["QTD"]/total_geral*100).round(1)
    g = g.nlargest(10,"QTD").sort_values("QTD")
    if g.empty: return _empty("Sem motivos informados")
    n = len(g)
    cores = []
    for i in range(n):
        rank = n - 1 - i
        if rank == 0:   cores.append(PAL["yellow"])
        elif rank <= 2: cores.append(PAL["grayD"])
        else:           cores.append(PAL["gray"])
    labels = [_trunc(mt, 30) for mt in g["NM_MOTIVO_REAGENDA"].tolist()]
    x, texto, suffix = _vals(g, mode)
    custom = list(zip(g["NM_MOTIVO_REAGENDA"].tolist(), g["QTD"].tolist(),
                      g["TAXA"].tolist(), g["REP"].tolist()))
    return {"data":[{"type":"bar","orientation":"h",
        "x":x,"y":labels,"text":texto,"textposition":"outside",
        "textfont":{"size":11,"color":PAL["dark"]},
        "marker":{"color":cores,"line":{"width":0}},
        "customdata":custom,
        "hovertemplate":("<b>%{customdata}</b><br>"
            "Ocorrencias: <b>%{customdata,}</b><br>"
            "%% dos motivos: <b>%{customdata:.1f}%%</b><br>"
            "Representatividade: <b>%{customdata:.1f}%%</b><extra></extra>")}],
        "layout":{**_layout("Top 10 Motivos de Quebra",420,l=200,r=60),
            "xaxis":{"gridcolor":PAL["border"],"linecolor":PAL["border"],
                "tickfont":{"color":PAL["muted"],"size":10},
                "showgrid":True,"zeroline":False,"ticksuffix":suffix}}}

# ===== G5: parceira =====
def _g5(df, mode="qtd"):
    g = _agrega(df, "PARCEIRA_NOME", only_quebra=False)
    if g.empty: return _empty("Sem parceira informada")
    if mode == "qtd":
        g = g.sort_values("QTD")
        n = len(g)
        cores = []
        for i in range(n):
            rank = n - 1 - i
            if rank == 0:   cores.append(PAL["red"])
            elif rank <= 2: cores.append(PAL["redD"])
            else:           cores.append(PAL["grayD"])
        titulo = "Parceira (Quantidade de Quebras)"
    elif mode == "taxa":
        g = g.sort_values("TAXA")
        def c(p):
            if p < 50:  return PAL["green"]
            if p < 70:  return PAL["yellow"]
            return PAL["red"]
        cores = [c(p) for p in g["TAXA"]]
        titulo = "Taxa de Quebra por Parceira"
    else:  # rep
        g = g.sort_values("REP")
        n = len(g)
        cores = []
        for i in range(n):
            rank = n - 1 - i
            if rank == 0:   cores.append(PAL["red"])
            elif rank <= 2: cores.append(PAL["redD"])
            else:           cores.append(PAL["grayD"])
        titulo = "Representatividade por Parceira"
    x, texto, suffix = _vals(g, mode)
    custom = list(zip(g["PARCEIRA_NOME"].tolist(), g["TOTAL"].tolist(),
                      g["QTD"].tolist(), g["TAXA"].tolist(),
                      g["REP"].tolist()))
    return {"data":[{"type":"bar","orientation":"h",
        "x":x,"y":g["PARCEIRA_NOME"].tolist(),
        "text":texto,"textposition":"outside",
        "textfont":{"size":11,"color":PAL["dark"]},
        "marker":{"color":cores,"line":{"width":0}},
        "customdata":custom,"hovertemplate":HOVER}],
        "layout":{**_layout(titulo,420,l=120,r=80),
            "xaxis":{"gridcolor":PAL["border"],"linecolor":PAL["border"],
                "tickfont":{"color":PAL["muted"],"size":10},
                "showgrid":True,"zeroline":False,"ticksuffix":suffix}}}

# ===== G6: responsavel =====
def _g6(df, mode="qtd"):
    d = df[df["IS_QUEBRA"]]
    m = (d["NM_QUEBRA_RESPONSAVEL"]!="") & (
        ~d["NM_QUEBRA_RESPONSAVEL"].str.lower().str.contains(
            "nao informado|n.o informado",na=False,regex=True))
    d_filt = d[m]
    if d_filt.empty: return _empty("Sem responsavel informado")
    g = d_filt.groupby("NM_QUEBRA_RESPONSAVEL",as_index=False).size().rename(
        columns={"size":"QTD"})
    total_resp = max(int(g["QTD"].sum()), 1)
    total_geral = max(int(df.shape[0]), 1)
    g["TOTAL"] = g["QTD"]
    g["TAXA"] = (g["QTD"]/total_resp*100).round(1)
    g["REP"] = (g["QTD"]/total_geral*100).round(1)
    g = g.nlargest(15,"QTD").sort_values("QTD")
    if g.empty: return _empty("Sem responsavel informado")
    n = len(g)
    cores = []
    for i in range(n):
        rank = n - 1 - i
        if rank == 0:   cores.append(PAL["red"])
        elif rank <= 2: cores.append(PAL["redD"])
        else:           cores.append(PAL["grayD"])
    labels = [_trunc(r, 28) for r in g["NM_QUEBRA_RESPONSAVEL"].tolist()]
    x, texto, suffix = _vals(g, mode)
    custom = list(zip(g["NM_QUEBRA_RESPONSAVEL"].tolist(), g["QTD"].tolist(),
                      g["TAXA"].tolist(), g["REP"].tolist()))
    return {"data":[{"type":"bar","orientation":"h",
        "x":x,"y":labels,"text":texto,"textposition":"outside",
        "textfont":{"size":11,"color":PAL["dark"]},
        "marker":{"color":cores,"line":{"width":0}},
        "customdata":custom,
        "hovertemplate":("<b>%{customdata}</b><br>"
            "Quebras: <b>%{customdata,}</b><br>"
            "%% dos responsaveis: <b>%{customdata:.1f}%%</b><br>"
            "Representatividade: <b>%{customdata:.1f}%%</b><extra></extra>")}],
        "layout":{**_layout("Responsavel pela Quebra",420,l=180,r=60),
            "xaxis":{"gridcolor":PAL["border"],"linecolor":PAL["border"],
                "tickfont":{"color":PAL["muted"],"size":10},
                "showgrid":True,"zeroline":False,"ticksuffix":suffix}}}

@bp_quebra.route("/")
def index():
    return render_template("dash_quebra.html")

@bp_quebra.route("/api/status")
def api_status():
    return jsonify({"ready":_STATE["df"] is not None,
        "loading":_STATE["loading"],"error":_STATE["load_error"],
        "load_time_s":_STATE["load_time"]})

@bp_quebra.route("/api/refresh", methods=["GET","POST"])
def api_refresh():
    try:
        if _STATE["df"] is None:
            if not _STATE["loading"]: _warmup_async()
            return jsonify({"ok":False,"loading":True}), 202
        filters = request.get_json(silent=True) or {}
        mode = filters.get("mode", "qtd")
        if mode not in ("qtd","taxa","rep"): mode = "qtd"
        df_all = _STATE["df"]
        t0 = time.time()
        options = _build_options(df_all, filters)
        # KPIs: TODOS os filtros aplicados
        df_kpi = _filter_df(df_all, filters)
        t = int(len(df_kpi))
        cq = int(df_kpi["IS_QUEBRA"].sum()) if t else 0
        sq = t - cq
        p = round(cq/t*100, 1) if t > 0 else 0.0
        kpis = {"total":_fmt(t),"com_q":_fmt(cq),
                "sem_q":_fmt(sq),"pct":f"{p}%"}
        # Cada grafico: aplica filtros EXCETO o do seu eixo
        figs = {}
        for gid, fn in [("g1",_g1),("g2",_g2),("g3",_g3),
                        ("g4",_g4),("g5",_g5),("g6",_g6)]:
            df_g = _filter_df(df_all, filters, exclude_key=EXCLUDE_MAP[gid])
            figs[gid] = fn(df_g, mode)
        elapsed = round(time.time()-t0, 3)
        return jsonify({"ok":True,"options":options,"kpis":kpis,
                        "figs":figs,"elapsed_s":elapsed,"mode":mode})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e),
            "trace":traceback.format_exc()}), 500

@bp_quebra.route("/api/debug")
def api_debug():
    if _STATE["df"] is None:
        return jsonify({"ok":False,"loading":_STATE["loading"]}), 202
    return jsonify({"ok":True,"info":{"df_quebra":_STATE["diag"]}})
