# -*- coding: utf-8 -*-
# fix12.py - Eixo nao filtra a si mesmo + 3 modos (Qtd/Taxa/Rep)
from pathlib import Path
import shutil, py_compile, sys

BASE = Path(__file__).parent
print("="*70); print("FIX12 - Eixo livre + Toggle 3 modos"); print("="*70)

DASH_PY = '''# -*- coding: utf-8 -*-
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
'''
target = BASE / "areas/area/area/adm/desconexao//dash_quebra.py"
target.write_text(DASH_PY, encoding="utf-8")
py_compile.compile(str(target), doraise=True)
print(f"  [OK] dash_quebra.py ({len(DASH_PY)} bytes)")

# ===== Template com 3 botoes no toggle =====
TPL = '''__O__% extends "base.html" %__C__
__O__% block title %__C__Quebra de Agenda__O__% endblock %__C__
__O__% block content %__C__
__LT__link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/choices.js/public/assets/styles/choices.min.css"__GT__
__LT__script src="https://cdn.plot.ly/plotly-2.35.2.min.js"__GT____LT__/script__GT__
__LT__script src="https://cdn.jsdelivr.net/npm/choices.js/public/assets/scripts/choices.min.js"__GT____LT__/script__GT__
__LT__style__GT__
:root{
  --red:#E60000; --redD:#B71C1C;
  --green:#2E7D32; --yellow:#F9A825; --blue:#1976D2;
  --white:#FFFFFF; --bg:#F8F9FA; --border:#E9ECEF;
  --muted:#6C757D; --dark:#343A40; --gray:#ADB5BD;
}
.qbr-wrap{padding:0 1rem;background:var(--bg);min-height:100vh;}
.qbr-header{background:var(--white);color:var(--dark);
  padding:1.2rem 1.5rem;border-radius:.6rem;margin:1rem 0;
  box-shadow:0 1px 3px rgba(0,0,0,.06);border-left:5px solid var(--red);
  display:flex;align-items:center;justify-content:space-between;}
.qbr-header h2{margin:0;font-size:1.35rem;font-weight:600;color:var(--dark);}
.qbr-header h2 .icon{color:var(--red);margin-right:.4rem;}
.qbr-header .sub{color:var(--muted);font-size:.85rem;margin-top:.2rem;}
.qbr-back{color:var(--red);text-decoration:none;font-size:.85rem;
  border:1px solid var(--red);padding:.4rem 1rem;border-radius:.3rem;
  font-weight:600;transition:.2s;}
.qbr-back:hover{background:var(--red);color:#fff;}
.qbr-section{color:var(--dark);padding:.6rem 1rem;border-radius:.3rem;
  margin:1.5rem 0 .8rem;font-weight:600;font-size:.9rem;
  background:var(--white);border-left:4px solid var(--red);
  text-transform:uppercase;letter-spacing:.05em;
  box-shadow:0 1px 2px rgba(0,0,0,.04);}
.qbr-section .icon{color:var(--red);margin-right:.4rem;}
.qbr-filters{background:var(--white);border-radius:.6rem;padding:1.2rem;
  margin-bottom:1rem;box-shadow:0 1px 3px rgba(0,0,0,.06);}
.qbr-filters-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:.8rem;}
.qbr-filters label{font-size:.7rem;font-weight:700;color:var(--muted);
  text-transform:uppercase;margin-bottom:.3rem;display:block;letter-spacing:.05em;}
@media (max-width:1100px){.qbr-filters-grid{grid-template-columns:repeat(3,1fr);}}
@media (max-width:700px){.qbr-filters-grid{grid-template-columns:repeat(2,1fr);}}
.qbr-actions-row{display:flex;justify-content:space-between;
  align-items:center;margin-top:.8rem;flex-wrap:wrap;gap:.8rem;}
.qbr-clear-btn{border:1px solid var(--red);color:var(--red);background:#fff;
  padding:.4rem 1rem;border-radius:.3rem;font-size:.78rem;cursor:pointer;
  font-weight:600;transition:.2s;}
.qbr-clear-btn:hover{background:var(--red);color:#fff;}
.qbr-toggle-wrap{display:flex;align-items:center;gap:.7rem;flex-wrap:wrap;}
.qbr-toggle-lbl{font-size:.75rem;color:var(--muted);font-weight:700;
  text-transform:uppercase;letter-spacing:.05em;}
.qbr-toggle{display:inline-flex;background:var(--bg);border-radius:30px;
  padding:3px;border:1px solid var(--border);}
.qbr-toggle button{background:transparent;border:0;color:var(--muted);
  padding:.4rem 1rem;border-radius:30px;font-size:.78rem;font-weight:700;
  cursor:pointer;transition:.2s;letter-spacing:.03em;}
.qbr-toggle button.active{background:var(--red);color:#fff;
  box-shadow:0 1px 3px rgba(230,0,0,.3);}
.qbr-toggle button:hover:not(.active){color:var(--dark);}
.qbr-toggle-help{font-size:.7rem;color:var(--muted);margin-top:.3rem;
  width:100%;font-style:italic;}
.qbr-kpis-grid{display:grid;grid-template-columns:repeat(4,1fr);
  gap:1rem;margin-bottom:.5rem;}
@media (max-width:900px){.qbr-kpis-grid{grid-template-columns:repeat(2,1fr);}}
.qbr-kpi{background:var(--white);border-radius:.6rem;padding:1.1rem 1.2rem;
  box-shadow:0 1px 3px rgba(0,0,0,.06);position:relative;
  border-top:3px solid var(--red);transition:.2s;}
.qbr-kpi:hover{transform:translateY(-2px);box-shadow:0 4px 10px rgba(0,0,0,.08);}
.qbr-kpi.b-blue{border-top-color:var(--blue);}
.qbr-kpi.b-red{border-top-color:var(--red);}
.qbr-kpi.b-green{border-top-color:var(--green);}
.qbr-kpi.b-orange{border-top-color:var(--yellow);}
.qbr-kpi .ico{position:absolute;top:1rem;right:1.2rem;font-size:1.3rem;opacity:.25;}
.qbr-kpi.b-blue .ico{color:var(--blue);}
.qbr-kpi.b-red .ico{color:var(--red);}
.qbr-kpi.b-green .ico{color:var(--green);}
.qbr-kpi.b-orange .ico{color:var(--yellow);}
.qbr-kpi .lbl{font-size:.7rem;color:var(--muted);text-transform:uppercase;
  font-weight:700;margin-bottom:.5rem;letter-spacing:.05em;}
.qbr-kpi .val{font-size:1.85rem;font-weight:700;color:var(--dark);line-height:1;}
.qbr-graphs-row{display:grid;grid-template-columns:1fr 1fr;
  gap:1rem;margin-bottom:.5rem;}
@media (max-width:992px){.qbr-graphs-row{grid-template-columns:1fr;}}
.qbr-graph-card{background:var(--white);border-radius:.6rem;padding:.4rem;
  box-shadow:0 1px 3px rgba(0,0,0,.06);transition:.2s;}
.qbr-graph-card:hover{box-shadow:0 3px 10px rgba(0,0,0,.08);}
.qbr-graph-card .gbox{height:420px;}
.choices__inner{min-height:40px;padding:5px 8px;font-size:.85rem;
  border:1px solid var(--border);border-radius:.3rem;background:#fff;}
.choices__inner:focus-within{border-color:var(--red);}
.choices__list--multiple .choices__item{background:var(--red);
  border-color:var(--red);font-size:.75rem;border-radius:3px;}
#qbr-loader{position:fixed;top:1rem;right:1rem;background:var(--red);
  color:#fff;padding:.5rem 1rem;border-radius:.3rem;font-size:.85rem;
  z-index:9999;display:none;box-shadow:0 2px 8px rgba(0,0,0,.2);font-weight:600;}
#qbr-warmup{position:fixed;top:0;left:0;width:100%;height:100%;
  background:rgba(255,255,255,.96);display:flex;align-items:center;
  justify-content:center;z-index:10000;}
#qbr-warmup .box{background:#fff;padding:2rem 3rem;border-radius:.5rem;
  box-shadow:0 4px 20px rgba(0,0,0,.15);text-align:center;
  border-top:5px solid var(--red);}
#qbr-warmup h3{color:var(--red);margin:0 0 .5rem;}
#qbr-warmup .spin{margin:1rem auto;width:40px;height:40px;
  border:4px solid #eee;border-top-color:var(--red);border-radius:50%;
  animation:spin 1s linear infinite;}
@keyframes spin{to{transform:rotate(360deg);}}
__LT__/style__GT__

__LT__div id="qbr-warmup"__GT__
  __LT__div class="box"__GT__
    __LT__h3__GT__⏳ Carregando dados...__LT__/h3__GT__
    __LT__div__GT__1a vez aquece o cache. Proximos acessos serao instantaneos.__LT__/div__GT__
    __LT__div class="spin"__GT____LT__/div__GT__
    __LT__div id="qbr-warmup-msg" style="font-size:.85rem;color:#666;"__GT__Aguarde...__LT__/div__GT__
  __LT__/div__GT__
__LT__/div__GT__
__LT__div id="qbr-loader"__GT__⏳ Atualizando...__LT__/div__GT__

__LT__div class="qbr-wrap"__GT__
  __LT__div class="qbr-header"__GT__
    __LT__div__GT__
      __LT__h2__GT____LT__span class="icon"__GT__📅__LT__/span__GT__Desconexao RNO — Quebra de Agenda__LT__/h2__GT__
      __LT__div class="sub"__GT__Analise das ordens agendadas e quebras por parceira__LT__/div__GT__
    __LT__/div__GT__
    __LT__a class="qbr-back" href="/area/area/area/adm/desconexao//"__GT__← Menu__LT__/a__GT__
  __LT__/div__GT__

  __LT__div class="qbr-filters"__GT__
    __LT__div class="qbr-filters-grid"__GT__
      __LT__div__GT____LT__label__GT__Ano__LT__/label__GT____LT__select id="f-anos" multiple__GT____LT__/select__GT____LT__/div__GT__
      __LT__div__GT____LT__label__GT__Mes__LT__/label__GT____LT__select id="f-meses" multiple__GT____LT__/select__GT____LT__/div__GT__
      __LT__div__GT____LT__label__GT__Dia__LT__/label__GT____LT__select id="f-dias" multiple__GT____LT__/select__GT____LT__/div__GT__
      __LT__div__GT____LT__label__GT__UF__LT__/label__GT____LT__select id="f-ufs" multiple__GT____LT__/select__GT____LT__/div__GT__
      __LT__div__GT____LT__label__GT__Cidade__LT__/label__GT____LT__select id="f-cids" multiple__GT____LT__/select__GT____LT__/div__GT__
      __LT__div__GT____LT__label__GT__Parceira__LT__/label__GT____LT__select id="f-parcs" multiple__GT____LT__/select__GT____LT__/div__GT__
    __LT__/div__GT__
    __LT__div class="qbr-actions-row"__GT__
      __LT__div class="qbr-toggle-wrap"__GT__
        __LT__span class="qbr-toggle-lbl"__GT__Visualizar:__LT__/span__GT__
        __LT__div class="qbr-toggle"__GT__
          __LT__button type="button" id="btnQtd"  class="active"__GT__📊 Quantidade__LT__/button__GT__
          __LT__button type="button" id="btnTaxa"__GT__📈 Taxa__LT__/button__GT__
          __LT__button type="button" id="btnRep"__GT__🎯 Representatividade__LT__/button__GT__
        __LT__/div__GT__
        __LT__div class="qbr-toggle-help" id="modeHelp"__GT____LT__/div__GT__
      __LT__/div__GT__
      __LT__button class="qbr-clear-btn" id="btnClear"__GT__🗑️ Limpar filtros__LT__/button__GT__
    __LT__/div__GT__
  __LT__/div__GT__

  __LT__div class="qbr-kpis-grid"__GT__
    __LT__div class="qbr-kpi b-blue"__GT____LT__div class="ico"__GT__📊__LT__/div__GT____LT__div class="lbl"__GT__Total Registros__LT__/div__GT____LT__div class="val" id="kpi-total"__GT__-__LT__/div__GT____LT__/div__GT__
    __LT__div class="qbr-kpi b-red"__GT____LT__div class="ico"__GT__⚠️__LT__/div__GT____LT__div class="lbl"__GT__Com Quebra__LT__/div__GT____LT__div class="val" id="kpi-comq"__GT__-__LT__/div__GT____LT__/div__GT__
    __LT__div class="qbr-kpi b-green"__GT____LT__div class="ico"__GT__✅__LT__/div__GT____LT__div class="lbl"__GT__Sem Quebra__LT__/div__GT____LT__div class="val" id="kpi-semq"__GT__-__LT__/div__GT____LT__/div__GT__
    __LT__div class="qbr-kpi b-orange"__GT____LT__div class="ico"__GT__📉__LT__/div__GT____LT__div class="lbl"__GT__% Quebra__LT__/div__GT____LT__div class="val" id="kpi-pct"__GT__-__LT__/div__GT____LT__/div__GT__
  __LT__/div__GT__

  __LT__div class="qbr-section"__GT____LT__span class="icon"__GT__📈__LT__/span__GT__Evolucao Temporal__LT__/div__GT__
  __LT__div class="qbr-graphs-row"__GT__
    __LT__div class="qbr-graph-card"__GT____LT__div id="g1" class="gbox"__GT____LT__/div__GT____LT__/div__GT__
    __LT__div class="qbr-graph-card"__GT____LT__div id="g2" class="gbox"__GT____LT__/div__GT____LT__/div__GT__
  __LT__/div__GT__
  __LT__div class="qbr-section"__GT____LT__span class="icon"__GT__🌎__LT__/span__GT__Cidades e Motivos__LT__/div__GT__
  __LT__div class="qbr-graphs-row"__GT__
    __LT__div class="qbr-graph-card"__GT____LT__div id="g3" class="gbox"__GT____LT__/div__GT____LT__/div__GT__
    __LT__div class="qbr-graph-card"__GT____LT__div id="g4" class="gbox"__GT____LT__/div__GT____LT__/div__GT__
  __LT__/div__GT__
  __LT__div class="qbr-section"__GT____LT__span class="icon"__GT__🏢__LT__/span__GT__Parceiras e Responsaveis__LT__/div__GT__
  __LT__div class="qbr-graphs-row" style="margin-bottom:2rem;"__GT__
    __LT__div class="qbr-graph-card"__GT____LT__div id="g5" class="gbox"__GT____LT__/div__GT____LT__/div__GT__
    __LT__div class="qbr-graph-card"__GT____LT__div id="g6" class="gbox"__GT____LT__/div__GT____LT__/div__GT__
  __LT__/div__GT__
__LT__/div__GT__

__LT__script__GT__
(function(){
  const F={anos:null,meses:null,dias:null,ufs:null,cids:null,parcs:null};
  const _up={}; let inflight=null;
  let MODE = localStorage.getItem("qbr_mode") || "qtd";
  if(["qtd","taxa","rep"].indexOf(MODE)__LT__0) MODE="qtd";

  const HELP = {
    qtd:  "Numero absoluto de quebras por categoria.",
    taxa: "Taxa de quebra de cada categoria (quebras / total da categoria).",
    rep:  "Contribuicao para a taxa total: quebras da categoria / total geral. Soma = taxa total de quebra.",
  };

  function loader(on){document.getElementById("qbr-loader").style.display=on?"block":"none";}
  function hideWarmup(){document.getElementById("qbr-warmup").style.display="none";}
  function setWarmupMsg(s){document.getElementById("qbr-warmup-msg").innerText=s;}

  function updateToggleUI(){
    document.getElementById("btnQtd").classList.toggle("active", MODE==="qtd");
    document.getElementById("btnTaxa").classList.toggle("active", MODE==="taxa");
    document.getElementById("btnRep").classList.toggle("active", MODE==="rep");
    document.getElementById("modeHelp").innerText = HELP[MODE] || "";
  }

  function mk(id,key){
    const el=document.getElementById(id);
    const c=new Choices(el,{removeItemButton:true,shouldSort:false,
      placeholderValue:"Todos...",searchPlaceholderValue:"Buscar...",
      noResultsText:"Nenhum",noChoicesText:"Sem opcoes",itemSelectText:""});
    el.addEventListener("addItem",function(){if(!_up[key])refresh();});
    el.addEventListener("removeItem",function(){if(!_up[key])refresh();});
    return c;
  }
  function setO(c,key,opts){
    const sel=c.getValue(true)||[];
    _up[key]=true; c.clearStore();
    const ch=(opts||[]).map(function(o){return {value:o.v,label:o.l,selected:sel.indexOf(o.v)__GE__0};});
    c.setChoices(ch,"value","label",true);
    _up[key]=false;
  }
  function vals(c){return c.getValue(true)||[];}
  async function waitWarm(){
    let tries=0;
    while(tries__LT__120){
      try{
        const r=await fetch("/dash/quebra/api/status");
        const j=await r.json();
        if(j.ready){hideWarmup();return true;}
        setWarmupMsg("Carregando... ("+tries+"s)");
      }catch(e){}
      await new Promise(r=>setTimeout(r,1000));
      tries++;
    }
    return false;
  }
  async function refresh(){
    if(inflight)inflight.abort();
    inflight=new AbortController(); loader(true);
    const body={anos:vals(F.anos),meses:vals(F.meses),dias:vals(F.dias),
      ufs:vals(F.ufs),cids:vals(F.cids),parcs:vals(F.parcs),mode:MODE};
    try{
      const r=await fetch("/dash/quebra/api/refresh",{method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(body),signal:inflight.signal});
      if(r.status===202){loader(false);await waitWarm();return refresh();}
      const j=await r.json();
      if(!j.ok){console.error(j);loader(false);return;}
      setO(F.anos,"anos",j.options.anos);
      setO(F.meses,"meses",j.options.meses);
      setO(F.dias,"dias",j.options.dias);
      setO(F.ufs,"ufs",j.options.ufs);
      setO(F.cids,"cids",j.options.cids);
      setO(F.parcs,"parcs",j.options.parcs);
      document.getElementById("kpi-total").innerText=j.kpis.total;
      document.getElementById("kpi-comq").innerText=j.kpis.com_q;
      document.getElementById("kpi-semq").innerText=j.kpis.sem_q;
      document.getElementById("kpi-pct").innerText=j.kpis.pct;
      const cfg={displayModeBar:false,responsive:true};
      ["g1","g2","g3","g4","g5","g6"].forEach(function(k){
        Plotly.react(k,j.figs[k].data,j.figs[k].layout,cfg);
      });
      console.log("refresh em "+j.elapsed_s+"s (mode="+MODE+")");
    }catch(e){if(e.name!=="AbortError")console.error(e);}
    finally{loader(false);}
  }

  function setMode(m){
    if(MODE===m)return;
    MODE=m; localStorage.setItem("qbr_mode",MODE);
    updateToggleUI(); refresh();
  }

  document.addEventListener("DOMContentLoaded",async function(){
    F.anos=mk("f-anos","anos"); F.meses=mk("f-meses","meses");
    F.dias=mk("f-dias","dias"); F.ufs=mk("f-ufs","ufs");
    F.cids=mk("f-cids","cids"); F.parcs=mk("f-parcs","parcs");
    document.getElementById("btnClear").addEventListener("click",function(){
      ["anos","meses","dias","ufs","cids","parcs"].forEach(function(k){
        _up[k]=true; F[k].removeActiveItems(); _up[k]=false;
      });
      refresh();
    });
    document.getElementById("btnQtd").addEventListener("click",function(){setMode("qtd");});
    document.getElementById("btnTaxa").addEventListener("click",function(){setMode("taxa");});
    document.getElementById("btnRep").addEventListener("click",function(){setMode("rep");});
    document.addEventListener("keydown",function(e){
      if(e.target.tagName==="INPUT" || e.target.tagName==="SELECT")return;
      if(e.key==="q"||e.key==="Q")setMode("qtd");
      else if(e.key==="t"||e.key==="T")setMode("taxa");
      else if(e.key==="r"||e.key==="R")setMode("rep");
    });
    updateToggleUI();
    const r=await fetch("/dash/quebra/api/status");
    const j=await r.json();
    if(j.ready){hideWarmup();refresh();}
    else{const ok=await waitWarm();if(ok)refresh();}
  });
})();
__LT__/script__GT__
__O__% endblock %__C__
'''

HTML = (TPL.replace("__LT__","<").replace("__GT__",">")
           .replace("__O__","{").replace("__C__","}")
           .replace("__GE__",">="))
(BASE/"areas/area/area/adm/desconexao//templates/dash_quebra.html").write_text(
    HTML, encoding="utf-8")
print(f"  [OK] dash_quebra.html ({len(HTML)} bytes)")

n=0
for p in BASE.rglob("__pycache__"):
    if p.is_dir(): shutil.rmtree(p,ignore_errors=True); n+=1
print(f"  [OK] {n} __pycache__ removidos")

sys.path.insert(0,str(BASE))
for m in list(sys.modules.keys()):
    if m.startswith(("areas","app","data")): del sys.modules[m]
try:
    from areas.adm.desconexao import bp_quebra
    print(f"  [OK] bp_quebra: {bp_quebra.name} {bp_quebra.url_prefix}")
except Exception as e:
    print(f"  [ERRO] {e}")

print("\n" + "="*70)
print("MUDANCAS:")
print("  1. EIXO LIVRE: gráfico ignora SEU PROPRIO filtro")
print("     Filtra MES=05  -> G2 mostra todos os meses (mas com outros filtros)")
print("     Filtra DIA=15  -> G1 mostra todos os dias")
print("     Filtra Cidade  -> G3 mostra todas as cidades")
print("     Filtra Parceira-> G5 mostra todas as parceiras")
print("  2. TOGGLE 3 MODOS:")
print("     [QTD]  Quantidade absoluta de quebras")
print("     [TAXA] Taxa de quebra da categoria (quebras/total)")
print("     [REP]  Representatividade (quebras/total geral) - SOMA = taxa total")
print("  3. ATALHOS: Q=Qtd | T=Taxa | R=Rep")
print("  4. HOVER triplo: Total OS + Quebras + Taxa + Representatividade")
print("")
print("Ctrl+C + python run.py + Ctrl+F5")
print("="*70)