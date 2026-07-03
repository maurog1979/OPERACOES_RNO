
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
