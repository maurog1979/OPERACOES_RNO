# -*- coding: utf-8 -*-
"""
dash_quebra.py
Portal Operações RNO — ADM / Desconexão — Quebra de Agenda
FASE 2B fix12
"""
from __future__ import annotations

import os
import threading
import traceback
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import create_engine, text

bp_quebra = Blueprint("bp_quebra", __name__, url_prefix="/dash/quebra", template_folder="templates")

COLS = [
    "NR_CONTRATO", "NM_CIDADE", "UF", "DT_AGENDA", "ANO", "MES", "DIA",
    "NM_TIPO_TRATAMENTO", "NM_MOTIVO_REAGENDA", "NM_QUEBRA_RESPONSAVEL",
    "NM_QUEBRA_CENARIO", "PARCEIRA", "PARCEIRA_NOME",
]

SQL = """
SELECT
    NR_CONTRATO, NM_CIDADE, UF, DT_AGENDA, ANO, MES, DIA,
    NM_TIPO_TRATAMENTO, NM_MOTIVO_REAGENDA, NM_QUEBRA_RESPONSAVEL,
    NM_QUEBRA_CENARIO, PARCEIRA, PARCEIRA_NOME
FROM quebra_total
"""

QUEBRA_VALUE = "COM QUEBRA DE AGENDA"
SEM_QUEBRA_VALUE = "SEM QUEBRA DE AGENDA"

_STATE: dict[str, Any] = {"df": None, "loading": False, "load_time": None, "load_error": None, "diag": {}}
_LOCK = threading.Lock()
_LOAD_EVENT = threading.Event()

EXCLUDE_MAP = {
    "g1": "dias",
    "g2": "meses",
    "g3": "cids",
    "g4": None,
    "g5": "parcs",
    "g6": None,
}


def _first_existing_attr(module: Any, names: list[str]) -> Any:
    for name in names:
        if hasattr(module, name):
            value = getattr(module, name)
            if value:
                return value
    return None


def _make_engine():
    try:
        import config  # type: ignore
        uri = _first_existing_attr(config, ["SQLALCHEMY_DATABASE_URI", "DATABASE_URI", "MYSQL_URI"])
        if uri:
            return create_engine(uri, pool_pre_ping=True)
        cfg = _first_existing_attr(config, ["DB_CONFIG", "MYSQL_CONFIG", "DATABASE_CONFIG"])
        if isinstance(cfg, dict):
            user = cfg.get("user") or cfg.get("username") or cfg.get("USER") or "root"
            password = cfg.get("password") or cfg.get("PASSWORD") or ""
            host = cfg.get("host") or cfg.get("HOST") or "localhost"
            port = cfg.get("port") or cfg.get("PORT") or 3306
            database = cfg.get("database") or cfg.get("db") or cfg.get("DATABASE") or "safra"
            return create_engine(f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4", pool_pre_ping=True)
    except Exception:
        pass

    uri = os.getenv("SQLALCHEMY_DATABASE_URI") or os.getenv("DATABASE_URI")
    if uri:
        return create_engine(uri, pool_pre_ping=True)
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    host = os.getenv("MYSQL_HOST", "localhost")
    port = os.getenv("MYSQL_PORT", "3306")
    database = os.getenv("MYSQL_DATABASE", "safra")
    return create_engine(f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4", pool_pre_ping=True)


def _norm_upper(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").str.strip().str.upper()


def _safe_int_str(series: pd.Series, width: int | None = None) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    out = numeric.astype("Int64").astype("string").fillna("")
    if width:
        out = out.str.zfill(width)
    return out


def _prepare_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in COLS:
        if col not in df.columns:
            df[col] = ""

    df["NR_CONTRATO"] = df["NR_CONTRATO"].astype("string").fillna("").str.strip()
    df["CIDADE"] = df["NM_CIDADE"].astype("string").fillna("").str.strip()
    df["UF"] = _norm_upper(df["UF"])
    df["TIPO"] = _norm_upper(df["NM_TIPO_TRATAMENTO"])
    df["MOTIVO"] = df["NM_MOTIVO_REAGENDA"].astype("string").fillna("NÃO INFORMADO").str.strip().replace("", "NÃO INFORMADO")
    df["RESPONSAVEL"] = df["NM_QUEBRA_RESPONSAVEL"].astype("string").fillna("NÃO INFORMADO").str.strip().replace("", "NÃO INFORMADO")
    df["CENARIO"] = df["NM_QUEBRA_CENARIO"].astype("string").fillna("NÃO INFORMADO").str.strip().replace("", "NÃO INFORMADO")

    df["ANO"] = _safe_int_str(df["ANO"])
    df["MES"] = _safe_int_str(df["MES"], 2)
    df["DIA"] = _safe_int_str(df["DIA"], 2)

    dt = pd.to_datetime(df["DT_AGENDA"], format="%d/%m/%Y %H:%M", errors="coerce")
    dt_alt = pd.to_datetime(df["DT_AGENDA"], dayfirst=True, errors="coerce")
    df["DATA"] = dt.fillna(dt_alt)

    missing_ano = df["ANO"].eq("") & df["DATA"].notna()
    missing_mes = df["MES"].eq("") & df["DATA"].notna()
    missing_dia = df["DIA"].eq("") & df["DATA"].notna()
    df.loc[missing_ano, "ANO"] = df.loc[missing_ano, "DATA"].dt.year.astype("string")
    df.loc[missing_mes, "MES"] = df.loc[missing_mes, "DATA"].dt.month.astype("Int64").astype("string").str.zfill(2)
    df.loc[missing_dia, "DIA"] = df.loc[missing_dia, "DATA"].dt.day.astype("Int64").astype("string").str.zfill(2)

    parceira_nome = df["PARCEIRA_NOME"].astype("string").fillna("").str.strip()
    parceira_cod = df["PARCEIRA"].astype("string").fillna("").str.strip()
    df["PARCEIRA_FINAL"] = parceira_nome.where(parceira_nome.ne(""), parceira_cod).replace("", "NÃO INFORMADA")

    df["IS_QUEBRA"] = df["TIPO"].eq(QUEBRA_VALUE)
    df["IS_SEM_QUEBRA"] = df["TIPO"].eq(SEM_QUEBRA_VALUE)

    for col in ["UF", "ANO", "MES", "DIA", "CIDADE", "PARCEIRA_FINAL", "MOTIVO", "RESPONSAVEL"]:
        df[col] = df[col].astype("string").fillna("").str.strip()
    return df


def _load_df(force: bool = False, wait: bool = True) -> pd.DataFrame:
    """Carrega quebra_total em cache com warmup e espera segura."""
    with _LOCK:
        if _STATE["df"] is not None and not force:
            return _STATE["df"]

        if _STATE["loading"]:
            if not wait:
                return _STATE["df"] if _STATE["df"] is not None else pd.DataFrame(columns=COLS)
            event = _LOAD_EVENT
        else:
            _STATE["loading"] = True
            _STATE["load_error"] = None
            _LOAD_EVENT.clear()
            event = None

    if event is not None:
        event.wait()
        with _LOCK:
            return _STATE["df"] if _STATE["df"] is not None else pd.DataFrame(columns=COLS)

    try:
        engine = _make_engine()
        start = datetime.now()

        with engine.connect() as conn:
            df = pd.read_sql(text(SQL), conn)

        df = _prepare_df(df)
        elapsed = (datetime.now() - start).total_seconds()

        diag = {
            "rows": int(len(df)),
            "load_seconds": round(elapsed, 2),
            "loaded_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "performance": "fix13 warmup igual Backlog + category + observed=True",
        }

        with _LOCK:
            _STATE["df"] = df
            _STATE["load_time"] = datetime.now()
            _STATE["diag"] = diag
            _STATE["loading"] = False
            _STATE["load_error"] = None

        return df

    except Exception as exc:
        with _LOCK:
            _STATE["loading"] = False
            _STATE["load_error"] = f"{type(exc).__name__}: {exc}"
            _STATE["diag"] = {"traceback": traceback.format_exc()}

        return pd.DataFrame(columns=COLS)

    finally:
        _LOAD_EVENT.set()


def preload_quebra_cache_async(force: bool = False) -> None:
    """Aquece o cache em background na subida do app."""
    with _LOCK:
        if _STATE["df"] is not None and not force:
            return
        if _STATE["loading"]:
            return

    def _runner() -> None:
        _load_df(force=force, wait=False)

    t = threading.Thread(
        target=_runner,
        name="dash_quebra_cache_warmup",
        daemon=True,
    )
    t.start()


@bp_quebra.record_once
def _warmup_when_blueprint_registered(state) -> None:
    """Aquece o cache quando o Blueprint é registrado pelo Flask."""
    preload_quebra_cache_async(force=False)

def _list_arg(name: str) -> list[str]:
    values = request.args.getlist(name)
    if not values:
        raw = request.args.get(name, "")
        values = raw.split(",") if raw else []
    return [str(v).strip() for v in values if str(v).strip() and str(v).strip().lower() not in {"todos", "todas", "all", "null", "none"}]


def _filters_from_request() -> dict[str, list[str]]:
    return {"anos": _list_arg("anos"), "meses": _list_arg("meses"), "dias": _list_arg("dias"), "ufs": _list_arg("ufs"), "cids": _list_arg("cids"), "parcs": _list_arg("parcs")}


def _apply_filters(df: pd.DataFrame, filters: dict[str, list[str]], exclude: str | None = None) -> pd.DataFrame:
    if df.empty:
        return df
    out = df
    mapping = {"anos": "ANO", "meses": "MES", "dias": "DIA", "ufs": "UF", "cids": "CIDADE", "parcs": "PARCEIRA_FINAL"}
    for key, col in mapping.items():
        if key == exclude:
            continue
        vals = filters.get(key) or []
        if vals:
            out = out[out[col].isin({str(v).strip() for v in vals if str(v).strip()})]
    return out


def _filter_options(df: pd.DataFrame, filters: dict[str, list[str]]) -> dict[str, list[str]]:
    specs = {"anos": "ANO", "meses": "MES", "dias": "DIA", "ufs": "UF", "cids": "CIDADE", "parcs": "PARCEIRA_FINAL"}
    opts = {}
    for key, col in specs.items():
        base = _apply_filters(df, filters, exclude=key)
        vals = base[col].dropna().astype(str).str.strip()
        opts[key] = sorted([v for v in vals.unique().tolist() if v])
    return opts


def _fmt_pct(value: float) -> str:
    return f"{value:.1f}%".replace(".", ",")


def _kpis(df: pd.DataFrame) -> dict[str, Any]:
    total = int(len(df))
    quebras = int(df["IS_QUEBRA"].sum()) if total else 0
    sem = int(df["IS_SEM_QUEBRA"].sum()) if total else 0
    taxa = (quebras / total * 100) if total else 0.0
    return {"total": total, "quebras": quebras, "sem_quebra": sem, "taxa_quebra": round(taxa, 2), "taxa_quebra_label": _fmt_pct(taxa)}


def _series_payload(df_axis: pd.DataFrame, df_kpi_base: pd.DataFrame, group_col: str, title: str, mode: str, top: int | None = None, sort_desc: bool = True) -> dict[str, Any]:
    if df_axis.empty:
        return {"title": title, "labels": [], "values": [], "customdata": [], "mode": mode}
    total_geral_filtrado = int(len(df_kpi_base))
    grp = df_axis.groupby(group_col, dropna=False).agg(total_os=("NR_CONTRATO", "size"), quebras=("IS_QUEBRA", "sum")).reset_index()
    grp[group_col] = grp[group_col].astype("string").fillna("NÃO INFORMADO").replace("", "NÃO INFORMADO")
    grp["total_os"] = grp["total_os"].astype(int)
    grp["quebras"] = grp["quebras"].astype(int)
    grp["taxa"] = np.where(grp["total_os"] > 0, grp["quebras"] / grp["total_os"] * 100, 0.0)
    grp["representatividade"] = np.where(total_geral_filtrado > 0, grp["quebras"] / total_geral_filtrado * 100, 0.0)
    if mode == "taxa":
        grp["valor"] = grp["taxa"]
    elif mode == "representatividade":
        grp["valor"] = grp["representatividade"]
    else:
        grp["valor"] = grp["quebras"]
    grp = grp.sort_values("valor", ascending=not sort_desc)
    if top:
        grp = grp.head(top)
    return {
        "title": title,
        "labels": grp[group_col].astype(str).tolist(),
        "values": [round(float(v), 2) for v in grp["valor"].tolist()],
        "customdata": [{"total_os": int(r["total_os"]), "quebras": int(r["quebras"]), "taxa": round(float(r["taxa"]), 2), "representatividade": round(float(r["representatividade"]), 2)} for _, r in grp.iterrows()],
        "mode": mode,
    }


def _chart_data(df: pd.DataFrame, filters: dict[str, list[str]], chart_id: str, group_col: str, title: str, mode: str, top: int | None = None, sort_desc: bool = True) -> dict[str, Any]:
    df_kpi = _apply_filters(df, filters, exclude=None)
    df_axis = _apply_filters(df, filters, exclude=EXCLUDE_MAP.get(chart_id))
    return _series_payload(df_axis, df_kpi, group_col, title, mode, top=top, sort_desc=sort_desc)




def _filters_without(filters: dict[str, list[str]], *keys: str) -> dict[str, list[str]]:
    out = {k: list(v) for k, v in (filters or {}).items()}
    for key in keys:
        out[key] = []
    return out

def _masks_without(df: pd.DataFrame, masks: dict[str, np.ndarray], *keys: str) -> dict[str, np.ndarray]:
    out = {k: v.copy() for k, v in (masks or {}).items()}
    for key in keys:
        out[key] = np.ones(len(df), dtype=bool)
    return out

@bp_quebra.route("/")
def index():
    return render_template("dash_quebra.html")


@bp_quebra.route("/api/status")
def api_status():
    df = _STATE.get("df")
    return jsonify({"ok": _STATE.get("load_error") is None, "loaded": df is not None, "loading": bool(_STATE.get("loading")), "rows": int(len(df)) if isinstance(df, pd.DataFrame) else 0, "load_error": _STATE.get("load_error"), "diag": _STATE.get("diag") or {}})


@bp_quebra.route("/api/debug")
def api_debug():
    force = request.args.get("force", "0") == "1"
    df = _load_df(force=force)
    return jsonify({"ok": _STATE.get("load_error") is None, "rows": int(len(df)), "loading": bool(_STATE.get("loading")), "load_error": _STATE.get("load_error"), "diag": _STATE.get("diag") or {}, "columns": list(df.columns), "sample": df.head(5).fillna("").to_dict(orient="records")})


@bp_quebra.route("/api/refresh")
def api_refresh():
    force = request.args.get("force", "0") == "1"
    mode = request.args.get("mode", "quantidade").strip().lower()
    if mode not in {"quantidade", "taxa", "representatividade"}:
        mode = "quantidade"
    df = _load_df(force=force)
    if df.empty and _STATE.get("load_error"):
        return jsonify({"ok": False, "error": _STATE.get("load_error"), "diag": _STATE.get("diag")}), 500
    filters = _filters_from_request()
    df_kpi = _apply_filters(df, filters, exclude=None)
    return jsonify({
        "ok": True,
        "mode": mode,
        "filters": filters,
        "options": _filter_options(df, filters),
        "kpis": _kpis(df_kpi),
        "charts": {
            "g1": _chart_data(df, filters, "g1", "DIA", "Evolução Diária de Quebras", mode, top=None, sort_desc=False),
            "g2": _chart_data(df, filters, "g2", "MES", "Quebras por Mês", mode, top=None, sort_desc=False),
            "g3": _chart_data(df, _filters_without(filters, "cids"), "g3", "CIDADE", "Top 10 Cidades com Quebra", mode, top=10, sort_desc=True),
            "g4": _chart_data(df, filters, "g4", "MOTIVO", "Top 10 Motivos de Quebra", mode, top=10, sort_desc=True),
            "g5": _chart_data(df, filters, "g5", "PARCEIRA_FINAL", "Parceiras", mode, top=None, sort_desc=True),
            "g6": _chart_data(df, filters, "g6", "RESPONSAVEL", "Responsável pela Quebra", mode, top=10, sort_desc=True),
        },
        "diag": _STATE.get("diag") or {},
    })
