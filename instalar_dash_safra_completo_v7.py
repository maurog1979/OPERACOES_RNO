# instalar_dash_safra_completo_v7.py
# FASE 2C — Painel Safra completo e corrigido
# Gera arquivos completos, sem adaptação manual:
# - areas\adm\desconexao\dash_safra.py
# - areas\adm\desconexao\templates\dash_safra.html
#
# Correções incluídas:
# - Banco correto: safra / localhost / root / porta 3306
# - Conexão robusta: tenta PyMySQL e depois mysql.connector
# - API diagnóstico: /dash/safra/api/diagnostico
# - API debug de colunas: /dash/safra/api/debug_colunas
# - Detecção inteligente das colunas de volume DESC/REC
# - Matriz RNO + Cidades, sem PARCEIRA nos painéis principais
#
# Execute na raiz do projeto:
# cd "C:\Users\n5996917\OneDrive - Claro SA\INTRANET\OPERACOES_RNO"
# python instalar_dash_safra_completo_v7.py

from pathlib import Path
from datetime import datetime
import re

ROOT = Path.cwd()
PADRAO = Path(r"C:\Users\n5996917\OneDrive - Claro SA\INTRANET\OPERACOES_RNO")
if not (ROOT / "areas" / "adm" / "desconexao").exists() and PADRAO.exists():
    ROOT = PADRAO

BASE = ROOT / "areas" / "adm" / "desconexao"
TPL = BASE / "templates"
DASH = BASE / "dash_safra.py"
HTML = TPL / "dash_safra.html"
REL = ROOT / "relatorio_instalar_dash_safra_completo_v7.txt"

BASE.mkdir(parents=True, exist_ok=True)
TPL.mkdir(parents=True, exist_ok=True)


def backup(p: Path):
    if p.exists():
        b = p.with_suffix(p.suffix + ".bak_v7_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        b.write_text(p.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
        return str(b)
    return None


DASH_CODE = r"""
from flask import Blueprint, render_template, jsonify, request
import pandas as pd
import math

bp = Blueprint("dash_safra", __name__, template_folder="templates")
dash_safra_bp = bp

TBL_MENSAL = "safra_resumo_mensal"
TBL_DIARIO = "safra_resumo_diario"
TBL_METAS = "safra_metas"

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "safra",
    "port": 3306,
}

SAFRAS_ORDEM = ["1 MES", "4 MESES", "13 MESES"]
TIPOS_ORDEM = ["INADIMPLENCIA", "OPCAO"]

METAS_PADRAO = {
    ("1 MES", "OPCAO"): 85.0,
    ("1 MES", "INADIMPLENCIA"): 45.0,
    ("4 MESES", "OPCAO"): 92.0,
    ("4 MESES", "INADIMPLENCIA"): 56.0,
    ("13 MESES", "OPCAO"): 98.0,
    ("13 MESES", "INADIMPLENCIA"): 67.0,
}

ULTIMO_ERRO_CONEXAO = ""


def _conn():
    global ULTIMO_ERRO_CONEXAO
    erros = []
    try:
        import pymysql
        return pymysql.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            port=int(DB_CONFIG["port"]),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.Cursor,
        )
    except Exception as e:
        erros.append(f"PyMySQL: {type(e).__name__}: {e}")
    try:
        import mysql.connector
        return mysql.connector.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            port=int(DB_CONFIG["port"]),
        )
    except Exception as e:
        erros.append(f"mysql.connector: {type(e).__name__}: {e}")
    ULTIMO_ERRO_CONEXAO = " | ".join(erros)
    raise RuntimeError("Falha de conexão MySQL. " + ULTIMO_ERRO_CONEXAO)


def _read_sql(sql, params=None):
    c = _conn()
    try:
        return pd.read_sql(sql, c, params=params or [])
    finally:
        try:
            c.close()
        except Exception:
            pass


def _cols(table):
    try:
        df = _read_sql(f"SHOW COLUMNS FROM {table}")
        return [str(x) for x in df["Field"].tolist()]
    except Exception:
        return []


def _norm(s):
    s = str(s or "").upper().strip()
    trocas = {
        "Á": "A", "À": "A", "Â": "A", "Ã": "A",
        "É": "E", "Ê": "E",
        "Í": "I",
        "Ó": "O", "Ô": "O", "Õ": "O",
        "Ú": "U",
        "Ç": "C",
        "º": "", "°": "",
    }
    for a, b in trocas.items():
        s = s.replace(a, b)
    return s


def _pick(cols, nomes):
    mapa = {_norm(c): c for c in cols}
    for n in nomes:
        nn = _norm(n)
        if nn in mapa:
            return mapa[nn]
    return None


def _canon_safra(v):
    s = _norm(v)
    if "13" in s:
        return "13 MESES"
    if "4" in s:
        return "4 MESES"
    if "1" in s or "01" in s:
        return "1 MES"
    return s


def _canon_tipo(v):
    s = _norm(v)
    if "OP" in s:
        return "OPCAO"
    if "INAD" in s:
        return "INADIMPLENCIA"
    return s


def _to_float(v):
    if pd.isna(v):
        return 0.0
    try:
        return float(v)
    except Exception:
        try:
            s = str(v).strip().replace("%", "")
            if "," in s:
                s = s.replace(".", "").replace(",", ".")
            return float(s)
        except Exception:
            return 0.0


def _is_bad_volume_col(name):
    n = _norm(name)
    ruins = [
        "PCT", "PERC", "PERCENT", "TAXA", "%", "META", "GAP", "MEDIA",
        "ANO", "MES", "DIA", "DATA", "DT_", "UF", "CIDADE", "SAFRA", "TIPO",
        "ID", "COD", "CD_", "NET", "PEND", "FAIXA", "RANK"
    ]
    return any(x in n for x in ruins)


def _pick_volume_col(df, kind):
    if df is None or df.empty:
        return None
    cols = list(df.columns)
    if kind == "desc":
        exact = [
            "DESC", "DESCONECTADOS", "DESCONECTADO", "TOTAL_DESC", "QTD_DESC", "VOLUME_DESC",
            "TOTAL_DESCONECTADO", "TOTAL_DESCONECTADOS", "QTD_DESCONECTADO", "QTD_DESCONECTADOS",
            "QTDE_DESC", "QTDE_DESCONECTADO", "QTDE_DESCONECTADOS", "VOLUME_DESCONECTADO",
            "VOLUME_DESCONECTADOS", "TOTAL_DESCON", "QTD_DESCON", "DESCON",
            "DESCONECTADOS_TOTAL", "DESCONECTADO_TOTAL", "DESCONEXAO", "TOTAL_DESCONEXAO",
            "QTD_DESCONEXAO", "BASE_DESC", "VOL_DESC", "VOLUME_DESCONEXAO"
        ]
        tokens = ["DESCONECT", "DESCON", "DESC"]
    else:
        exact = [
            "REC", "RECUPERADOS", "RECUPERADO", "TOTAL_REC", "QTD_REC", "VOLUME_REC",
            "TOTAL_RECUPERADO", "TOTAL_RECUPERADOS", "QTD_RECUPERADO", "QTD_RECUPERADOS",
            "QTDE_REC", "QTDE_RECUPERADO", "QTDE_RECUPERADOS", "VOLUME_RECUPERADO",
            "VOLUME_RECUPERADOS", "TOTAL_RECUP", "QTD_RECUP", "RECUP",
            "RECUPERADOS_TOTAL", "RECUPERADO_TOTAL", "BASE_REC", "VOL_REC", "VOLUME_RECUP"
        ]
        tokens = ["RECUPER", "RECUP", "REC"]
    c = _pick(cols, exact)
    if c:
        return c
    candidatos = []
    for col in cols:
        n = _norm(col)
        if _is_bad_volume_col(col):
            continue
        if any(tok in n for tok in tokens):
            try:
                soma = pd.to_numeric(df[col], errors="coerce").fillna(0).sum()
            except Exception:
                soma = 0
            candidatos.append((float(soma), len(n), col))
    positivos = [x for x in candidatos if x[0] > 0]
    if positivos:
        positivos.sort(reverse=True, key=lambda x: x[0])
        return positivos[0][2]
    if candidatos:
        candidatos.sort(key=lambda x: x[1])
        return candidatos[0][2]
    return None


def _where(cols, args, diario=False):
    mapa = {
        "ano": ["ANO", "ANO_BASE", "YEAR"],
        "mes": ["MES", "MES_BASE", "MONTH"],
        "dia": ["DIA", "DIA_BASE", "DAY"],
        "uf": ["UF"],
        "cidade": ["CIDADE", "NM_CIDADE", "OPERACAO", "OPERAÇÃO", "OPERACAO_RNO"],
        "safra": ["SAFRA"],
        "tipo": ["TIPO", "DS_TIPO_DESCONEXAO", "TIPO_DESCONEXAO", "DESCONEXAO", "TIPO_DESC"],
    }
    wh = []
    params = []
    for key, aliases in mapa.items():
        if key == "dia" and not diario:
            continue
        col = _pick(cols, aliases)
        raw = str(args.get(key, "") or "").strip()
        if not col or not raw:
            continue
        vals = [x.strip() for x in raw.split(",") if x.strip() and x.strip().upper() not in ("TODOS", "TODAS", "ALL")]
        if vals:
            wh.append(f"{col} IN ({','.join(['%s'] * len(vals))})")
            params.extend(vals)
    return (" WHERE " + " AND ".join(wh)) if wh else "", params


def _load(table, args, diario=False):
    cols = _cols(table)
    if not cols:
        return pd.DataFrame()
    wh, params = _where(cols, args, diario=diario)
    df = _read_sql(f"SELECT * FROM {table}{wh}", params)
    if df.empty:
        return df
    def col(nomes):
        return _pick(df.columns, nomes)
    c_ano = col(["ANO", "ANO_BASE", "YEAR"])
    c_mes = col(["MES", "MES_BASE", "MONTH"])
    c_dia = col(["DIA", "DIA_BASE", "DAY"])
    c_uf = col(["UF"])
    c_cidade = col(["CIDADE", "NM_CIDADE", "OPERACAO", "OPERAÇÃO", "OPERACAO_RNO"])
    c_safra = col(["SAFRA"])
    c_tipo = col(["TIPO", "DS_TIPO_DESCONEXAO", "TIPO_DESCONEXAO", "DESCONEXAO", "TIPO_DESC"])
    c_desc = _pick_volume_col(df, "desc")
    c_rec = _pick_volume_col(df, "rec")
    out = pd.DataFrame()
    out["ANO"] = df[c_ano] if c_ano else ""
    out["MES"] = df[c_mes] if c_mes else ""
    out["DIA"] = df[c_dia] if c_dia else ""
    out["UF"] = df[c_uf] if c_uf else "RNO"
    out["CIDADE"] = df[c_cidade] if c_cidade else "RNO"
    out["SAFRA"] = df[c_safra].map(_canon_safra) if c_safra else ""
    out["TIPO"] = df[c_tipo].map(_canon_tipo) if c_tipo else ""
    out["DESC"] = df[c_desc].map(_to_float) if c_desc else 0.0
    out["REC"] = df[c_rec].map(_to_float) if c_rec else 0.0
    return out


def _metas():
    metas = dict(METAS_PADRAO)
    try:
        df = _read_sql(f"SELECT * FROM {TBL_METAS}")
        if df.empty:
            return metas
        c_safra = _pick(df.columns, ["SAFRA"])
        c_tipo = _pick(df.columns, ["TIPO", "DS_TIPO_DESCONEXAO", "TIPO_DESCONEXAO", "DESCONEXAO", "TIPO_DESC"])
        c_meta = _pick(df.columns, ["META", "META_PCT", "PERCENTUAL_META", "META_PERCENTUAL"])
        if c_safra and c_tipo and c_meta:
            for _, r in df.iterrows():
                metas[(_canon_safra(r[c_safra]), _canon_tipo(r[c_tipo]))] = _to_float(r[c_meta])
    except Exception:
        pass
    return metas


def _pct(v):
    return round(float(v or 0), 2)


def _payload(df):
    metas = _metas()
    if df.empty:
        return {"ok": False, "erro": "Nenhum dado retornado para os filtros selecionados."}
    df = df[df["SAFRA"].isin(SAFRAS_ORDEM) & df["TIPO"].isin(TIPOS_ORDEM)].copy()
    if df.empty:
        return {"ok": False, "erro": "Sem dados válidos para SAFRA/TIPO após normalização."}
    total_desc = float(df["DESC"].sum())
    total_rec = float(df["REC"].sum())
    perc = (total_rec / total_desc * 100) if total_desc else 0.0
    meta_num = 0.0
    for _, r in df.iterrows():
        meta_num += float(r["DESC"] or 0.0) * float(metas.get((r["SAFRA"], r["TIPO"]), 0.0))
    meta_pond = (meta_num / total_desc) if total_desc else 0.0
    meta_vol = total_desc * meta_pond / 100
    gap_vol = total_rec - meta_vol
    gap_pct = perc - meta_pond
    faltam = max(meta_vol - total_rec, 0.0)
    escopos = [("RNO", df)]
    cidades = sorted([str(x) for x in df["CIDADE"].dropna().unique().tolist() if str(x).strip() and str(x).upper() != "RNO"])
    for cidade in cidades:
        escopos.append((cidade, df[df["CIDADE"].astype(str) == cidade]))
    matriz = []
    for safra in SAFRAS_ORDEM:
        for operacao, d0 in escopos:
            d = d0[d0["SAFRA"] == safra]
            linha = {"safra": safra, "operacao": operacao}
            for tipo, pre in [("INADIMPLENCIA", "inad"), ("OPCAO", "opcao")]:
                t = d[d["TIPO"] == tipo]
                desc = float(t["DESC"].sum())
                rec = float(t["REC"].sum())
                pr = (rec / desc * 100) if desc else 0.0
                meta = float(metas.get((safra, tipo), 0.0))
                linha[f"{pre}_pct"] = _pct(pr)
                linha[f"{pre}_desc"] = int(round(desc))
                linha[f"{pre}_rec"] = int(round(rec))
                linha[f"{pre}_gap_vol"] = int(round(rec - (desc * meta / 100)))
                linha[f"{pre}_gap_pct"] = _pct(pr - meta)
                linha[f"{pre}_meta"] = meta
            matriz.append(linha)
    ranking = []
    for cidade, g in df.groupby("CIDADE", dropna=True):
        desc = float(g["DESC"].sum())
        rec = float(g["REC"].sum())
        ranking.append({"cidade": str(cidade), "desc": int(round(desc)), "rec": int(round(rec)), "pct": _pct((rec / desc * 100) if desc else 0.0)})
    ranking = sorted(ranking, key=lambda x: x["pct"], reverse=True)
    comparativo = []
    for safra, g in df.groupby("SAFRA"):
        desc = float(g["DESC"].sum())
        rec = float(g["REC"].sum())
        comparativo.append({"safra": safra, "desc": int(round(desc)), "rec": int(round(rec)), "pct": _pct((rec / desc * 100) if desc else 0.0)})
    comparativo = sorted(comparativo, key=lambda x: SAFRAS_ORDEM.index(x["safra"]) if x["safra"] in SAFRAS_ORDEM else 99)
    tipos = []
    for tipo, g in df.groupby("TIPO"):
        desc = float(g["DESC"].sum())
        rec = float(g["REC"].sum())
        tipos.append({"tipo": "Inadimplência" if tipo == "INADIMPLENCIA" else "Opção", "desc": int(round(desc)), "rec": int(round(rec)), "pct": _pct((rec / desc * 100) if desc else 0.0)})
    return {
        "ok": True,
        "kpis": {
            "desc": int(round(total_desc)),
            "rec": int(round(total_rec)),
            "pct": _pct(perc),
            "meta": _pct(meta_pond),
            "gap_vol": int(round(gap_vol)),
            "gap_pct": _pct(gap_pct),
            "faltam": int(math.ceil(faltam)),
            "necessario_dia": int(math.ceil(faltam)),
            "tendencia": "ACIMA DA META" if gap_pct >= 0 else "ABAIXO DA META",
        },
        "matriz": matriz,
        "ranking": ranking,
        "comparativo": comparativo,
        "tipos": tipos,
    }


@bp.route("/dash/safra/")
def index():
    return render_template("dash_safra.html")


@bp.route("/dash/safra/api/diagnostico")
def diagnostico():
    try:
        c = _conn()
        try:
            db = pd.read_sql("SELECT DATABASE() AS banco", c).iloc[0]["banco"]
            tabelas = {}
            for t in [TBL_MENSAL, TBL_DIARIO, TBL_METAS]:
                try:
                    tabelas[t] = int(pd.read_sql(f"SELECT COUNT(*) AS total FROM {t}", c).iloc[0]["total"])
                except Exception as e:
                    tabelas[t] = f"ERRO: {type(e).__name__}: {e}"
            return jsonify({"ok": True, "banco": db, "tabelas": tabelas, "config": {"host": DB_CONFIG["host"], "database": DB_CONFIG["database"], "port": DB_CONFIG["port"]}})
        finally:
            try:
                c.close()
            except Exception:
                pass
    except Exception as e:
        return jsonify({"ok": False, "erro": f"{type(e).__name__}: {e}", "ultimo_erro_conexao": ULTIMO_ERRO_CONEXAO, "config": {"host": DB_CONFIG["host"], "database": DB_CONFIG["database"], "port": DB_CONFIG["port"]}})


@bp.route("/dash/safra/api/debug_colunas")
def debug_colunas():
    try:
        saida = {"ok": True, "tabelas": {}}
        for tabela in [TBL_MENSAL, TBL_DIARIO]:
            try:
                df = _read_sql(f"SELECT * FROM {tabela} LIMIT 5000")
                c_desc = _pick_volume_col(df, "desc") if not df.empty else None
                c_rec = _pick_volume_col(df, "rec") if not df.empty else None
                soma_desc = float(df[c_desc].map(_to_float).sum()) if c_desc else 0.0
                soma_rec = float(df[c_rec].map(_to_float).sum()) if c_rec else 0.0
                saida["tabelas"][tabela] = {
                    "linhas_lidas": int(len(df)),
                    "colunas": [str(c) for c in df.columns.tolist()],
                    "coluna_desc_escolhida": str(c_desc) if c_desc else None,
                    "coluna_rec_escolhida": str(c_rec) if c_rec else None,
                    "soma_desc": soma_desc,
                    "soma_rec": soma_rec,
                    "amostra": df.head(3).astype(str).to_dict(orient="records"),
                }
            except Exception as e:
                saida["tabelas"][tabela] = {"erro": f"{type(e).__name__}: {e}"}
        return jsonify(saida)
    except Exception as e:
        return jsonify({"ok": False, "erro": f"{type(e).__name__}: {e}"})


@bp.route("/dash/safra/api/options")
def options():
    try:
        dfm = _load(TBL_MENSAL, request.args, diario=False)
        try:
            dfd = _load(TBL_DIARIO, request.args, diario=True)
        except Exception:
            dfd = pd.DataFrame()
        df = pd.concat([dfm, dfd], ignore_index=True) if not dfd.empty else dfm
        if df.empty:
            return jsonify({"ok": False, "erro": "Sem dados nas tabelas safra_resumo_mensal/safra_resumo_diario."})
        def vals(c):
            return sorted([str(x) for x in df[c].dropna().unique().tolist() if str(x).strip() and str(x).lower() != "nan"])
        return jsonify({"ok": True, "options": {"ano": vals("ANO"), "mes": vals("MES"), "dia": vals("DIA"), "uf": vals("UF"), "cidade": vals("CIDADE"), "safra": SAFRAS_ORDEM, "tipo": TIPOS_ORDEM}})
    except Exception as e:
        return jsonify({"ok": False, "erro": f"{type(e).__name__}: {e}", "ultimo_erro_conexao": ULTIMO_ERRO_CONEXAO})


@bp.route("/dash/safra/api/data")
def data():
    try:
        usar_diario = bool(str(request.args.get("dia", "") or "").strip())
        df = _load(TBL_DIARIO if usar_diario else TBL_MENSAL, request.args, diario=usar_diario)
        return jsonify(_payload(df))
    except Exception as e:
        return jsonify({"ok": False, "erro": f"{type(e).__name__}: {e}", "ultimo_erro_conexao": ULTIMO_ERRO_CONEXAO})
"""

HTML_CODE = r"""
{% extends "base.html" %}
{% block content %}
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/choices.js/public/assets/styles/choices.min.css">
<script src="https://cdn.jsdelivr.net/npm/choices.js/public/assets/scripts/choices.min.js"></script>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root{--claro:#e60000;--dark:#15151a;--muted:#6b7280;--bg:#f4f5f7;--line:#e5e7eb;--ok:#10893e;--bad:#b91c1c}.safra-page{font-family:Inter,Segoe UI,Arial,sans-serif;background:var(--bg);min-height:100vh;margin:-24px;padding:24px;color:var(--dark)}.safra-hero{border-radius:28px;padding:30px 34px;color:#fff;background:radial-gradient(circle at 12% 22%,rgba(255,255,255,.26) 0,transparent 24%),linear-gradient(135deg,#ff3636 0%,#e60000 38%,#8b0000 100%);box-shadow:0 20px 60px rgba(120,0,0,.28);display:flex;align-items:flex-end;justify-content:space-between;gap:20px}.safra-hero h1{margin:0 0 8px;font-size:34px;font-weight:950;letter-spacing:-.8px}.safra-hero p{margin:0;opacity:.93;font-size:15px}.safra-pill{border:1px solid rgba(255,255,255,.38);background:rgba(255,255,255,.16);border-radius:999px;padding:10px 15px;font-weight:900;white-space:nowrap}.safra-filters{margin-top:18px;background:#fff;border-radius:22px;padding:18px;box-shadow:0 12px 36px rgba(15,23,42,.08);display:grid;grid-template-columns:repeat(7,minmax(118px,1fr));gap:12px}.filtro label{display:block;font-size:11px;font-weight:950;color:#444;letter-spacing:.08em;margin-bottom:5px}.kpis{display:grid;grid-template-columns:repeat(8,1fr);gap:14px;margin-top:18px}.kpi{background:#fff;border-radius:20px;padding:16px;box-shadow:0 10px 28px rgba(15,23,42,.07);border:1px solid #fff}.kpi small{color:var(--muted);font-size:10px;font-weight:950;text-transform:uppercase;letter-spacing:.07em}.kpi strong{display:block;margin-top:8px;font-size:22px;font-weight:950}.pos{color:var(--ok)}.neg{color:var(--bad)}.grid{display:grid;grid-template-columns:1.1fr .9fr;gap:18px;margin-top:18px}.card,.matrix{background:#fff;border-radius:24px;padding:18px;box-shadow:0 12px 36px rgba(15,23,42,.08)}.card h2,.matrix h2{margin:0 0 12px;font-size:17px;font-weight:950}.chart{height:335px}.matrix{margin-top:18px;overflow:auto}.safra-title{margin:22px 0 10px;font-size:18px;font-weight:950;color:#970000}table{width:100%;min-width:1120px;border-collapse:separate;border-spacing:0;font-size:12px}th{background:#1f2937;color:#fff;padding:10px;text-align:center;border-right:1px solid rgba(255,255,255,.16)}td{padding:9px 10px;text-align:right;border-bottom:1px solid var(--line)}td:first-child,th:first-child{text-align:left;font-weight:950}tr.rno td{background:#fff2f2;font-weight:950}.loading{padding:24px;text-align:center;font-weight:900;color:#666}@media(max-width:1300px){.safra-filters{grid-template-columns:repeat(4,1fr)}.kpis{grid-template-columns:repeat(4,1fr)}.grid{grid-template-columns:1fr}}@media(max-width:760px){.safra-page{margin:0;padding:14px}.safra-hero{display:block}.safra-filters,.kpis{grid-template-columns:1fr}}
</style>
<div class="safra-page"><section class="safra-hero"><div><h1>Painel Safra — Recuperação, Meta e Evolução</h1><p>Visão executiva RNO + Cidades · Opção x Inadimplência · GAP volumétrico e percentual vs metas oficiais</p></div><div class="safra-pill">ADM · Desconexão · RNO</div></section><section class="safra-filters"><div class="filtro"><label>ANO</label><select id="ano" multiple></select></div><div class="filtro"><label>MÊS</label><select id="mes" multiple></select></div><div class="filtro"><label>DIA</label><select id="dia" multiple></select></div><div class="filtro"><label>UF</label><select id="uf" multiple></select></div><div class="filtro"><label>CIDADE</label><select id="cidade" multiple></select></div><div class="filtro"><label>SAFRA</label><select id="safra" multiple></select></div><div class="filtro"><label>TIPO</label><select id="tipo" multiple></select></div></section><section class="kpis" id="kpis"></section><section class="grid"><div class="card"><h2>Recuperado x Meta</h2><div id="g_meta" class="chart"></div></div><div class="card"><h2>Ranking de Cidades</h2><div id="g_rank" class="chart"></div></div><div class="card"><h2>Comparativo Safra 1M x 4M x 13M</h2><div id="g_safra" class="chart"></div></div><div class="card"><h2>Opção x Inadimplência</h2><div id="g_tipo" class="chart"></div></div></section><section class="matrix"><h2>Matriz Principal — RNO + Cidades</h2><div id="matriz" class="loading">Carregando matriz...</div></section></div>
<script>
const ids=['ano','mes','dia','uf','cidade','safra','tipo'];const choices={};let updating=false;function fmt(n){return(Number(n)||0).toLocaleString('pt-BR')}function pct(n){return(Number(n)||0).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})+'%'}function qs(){const p=new URLSearchParams();ids.forEach(id=>{const v=choices[id]?.getValue(true)||[];if(v.length)p.set(id,v.join(','));});return p.toString()}function setOptions(id,arr){choices[id].clearStore();choices[id].setChoices((arr||[]).map(v=>({value:String(v),label:String(v)})),'value','label',true)}async function loadOptions(){const r=await fetch('/dash/safra/api/options');const j=await r.json();if(!j.ok){document.getElementById('matriz').innerHTML='<div class="loading">'+(j.erro||'Sem opções')+'</div>';return}updating=true;ids.forEach(id=>setOptions(id,j.options[id]||[]));updating=false}function renderKpis(k){const item=(t,v,c='')=>`<div class="kpi"><small>${t}</small><strong class="${c}">${v}</strong></div>`;document.getElementById('kpis').innerHTML=[item('Total Desconectado',fmt(k.desc)),item('Total Recuperado',fmt(k.rec)),item('% Recuperação',pct(k.pct),k.gap_pct>=0?'pos':'neg'),item('Meta',pct(k.meta)),item('GAP vs Meta',`${fmt(k.gap_vol)} · ${pct(k.gap_pct)}`,k.gap_pct>=0?'pos':'neg'),item('Faltam Recuperar',fmt(k.faltam),k.faltam>0?'neg':'pos'),item('Necessário por Dia',fmt(k.necessario_dia)),item('Tendência',k.tendencia,k.gap_pct>=0?'pos':'neg')].join('')}function plotAll(j){Plotly.newPlot('g_meta',[{type:'bar',x:['Recuperado','Meta'],y:[j.kpis.rec,Math.round(j.kpis.desc*j.kpis.meta/100)],marker:{color:['#e60000','#111827']}}],{margin:{t:10,l:45,r:15,b:40}},{displayModeBar:false});const rank=(j.ranking||[]).slice(0,12).reverse();Plotly.newPlot('g_rank',[{type:'bar',orientation:'h',y:rank.map(x=>x.cidade),x:rank.map(x=>x.pct),marker:{color:'#e60000'}}],{margin:{t:10,l:130,r:15,b:35},xaxis:{ticksuffix:'%'}},{displayModeBar:false});Plotly.newPlot('g_safra',[{type:'bar',x:(j.comparativo||[]).map(x=>x.safra),y:(j.comparativo||[]).map(x=>x.pct),marker:{color:'#b91c1c'}}],{margin:{t:10,l:45,r:15,b:40},yaxis:{ticksuffix:'%'}},{displayModeBar:false});Plotly.newPlot('g_tipo',[{type:'bar',x:(j.tipos||[]).map(x=>x.tipo),y:(j.tipos||[]).map(x=>x.pct),marker:{color:['#991b1b','#ef4444']}}],{margin:{t:10,l:45,r:15,b:40},yaxis:{ticksuffix:'%'}},{displayModeBar:false})}function td(v,isPct=false,cls=''){return`<td class="${cls}">${isPct?pct(v):fmt(v)}</td>`}function renderMatrix(rows){let html='';['1 MES','4 MESES','13 MESES'].forEach(safra=>{const rs=(rows||[]).filter(r=>r.safra===safra);html+=`<div class="safra-title">SAFRA ${safra}</div><table><thead><tr><th rowspan="2">Operação</th><th colspan="3">INAD</th><th colspan="3">OPÇÃO</th><th colspan="2">GAP INAD</th><th colspan="2">GAP OPÇÃO</th></tr><tr><th>%</th><th>DESC</th><th>REC</th><th>%</th><th>DESC</th><th>REC</th><th>GAP Vol</th><th>GAP %</th><th>GAP Vol</th><th>GAP %</th></tr></thead><tbody>`;rs.forEach(r=>{html+=`<tr class="${r.operacao==='RNO'?'rno':''}"><td>${r.operacao}</td>${td(r.inad_pct,true)}${td(r.inad_desc)}${td(r.inad_rec)}${td(r.opcao_pct,true)}${td(r.opcao_desc)}${td(r.opcao_rec)}${td(r.inad_gap_vol,false,r.inad_gap_vol>=0?'pos':'neg')}${td(r.inad_gap_pct,true,r.inad_gap_pct>=0?'pos':'neg')}${td(r.opcao_gap_vol,false,r.opcao_gap_vol>=0?'pos':'neg')}${td(r.opcao_gap_pct,true,r.opcao_gap_pct>=0?'pos':'neg')}</tr>`});html+='</tbody></table>'});document.getElementById('matriz').innerHTML=html}async function loadData(){const r=await fetch('/dash/safra/api/data?'+qs());const j=await r.json();if(!j.ok){document.getElementById('matriz').innerHTML='<div class="loading">'+(j.erro||'Sem dados')+'</div>';return}renderKpis(j.kpis);plotAll(j);renderMatrix(j.matriz)}async function init(){ids.forEach(id=>{choices[id]=new Choices('#'+id,{removeItemButton:true,searchEnabled:true,shouldSort:false,itemSelectText:''});document.getElementById(id).addEventListener('change',()=>{if(!updating)loadData()})});await loadOptions();await loadData()}init();
</script>
{% endblock %}
"""


def main():
    backups = []
    for p in [DASH, HTML]:
        b = backup(p)
        if b:
            backups.append(b)
    DASH.write_text(DASH_CODE, encoding="utf-8")
    HTML.write_text(HTML_CODE, encoding="utf-8")
    REL.write_text("\n".join([
        "RELATÓRIO — INSTALAR DASH SAFRA COMPLETO V7",
        f"Data/hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Raiz: {ROOT}",
        f"dash_safra.py: {DASH}",
        f"dash_safra.html: {HTML}",
        "Banco: safra | host localhost | porta 3306 | usuário root",
        "APIs: /dash/safra/api/diagnostico, /dash/safra/api/debug_colunas, /dash/safra/api/options, /dash/safra/api/data",
        "Backups: " + (", ".join(backups) if backups else "nenhum"),
        "Após executar: reiniciar Flask e testar /dash/safra/api/debug_colunas e /dash/safra/api/data",
    ]), encoding="utf-8")
    print("OK — dash_safra.py e dash_safra.html gerados completos e corrigidos.")
    print("dash_safra.py:", DASH)
    print("dash_safra.html:", HTML)
    print("Relatório:", REL)
    print("Reinicie o Flask e teste /dash/safra/api/debug_colunas")


if __name__ == "__main__":
    main()
