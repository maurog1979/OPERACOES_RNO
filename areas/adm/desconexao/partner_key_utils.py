# -*- coding: utf-8 -*-
"""Regra corporativa do fig6 do Dashboard Executivo.

Fonte: safra_enriquecida.
Parceira: PARCEIRA_NOME > TOA_PARCEIRA > TOA_AREA.
EPO nunca e utilizado.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Mapping, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go

INVALID = {
    "", "N/A", "NA", "NAN", "NONE", "NULL", "NI", "N.I.", "-",
    "NAO INFORMADO", "NAO INFORMADA", "NAO INFORMADOS", "NAO INFORMADAS",
    "SEM INFORMACAO", "SEM INFORMACAO DE PARCEIRA", "SEM PARCEIRA", "EPO",
}

DE_PARA = {
    "AFLINE INSTALACAO E MANUT ELETRICA": "AFLINE INSTALAÇÃO E MANUTENÇÃO ELÉTRICA",
    "AFLINE INSTALACAO E MANUTENCAO ELET": "AFLINE INSTALAÇÃO E MANUTENÇÃO ELÉTRICA",
    "AFLINE INSTALACAO E MANUTENCAO ELETRICA": "AFLINE INSTALAÇÃO E MANUTENÇÃO ELÉTRICA",
    "VIA REPRESENTACOES": "VIA REPRESENTAÇÕES",
    "HU SERVICOS": "HU SERVIÇOS",
    "FUKUSHIMA SERV DE TELEC E SOLUCOES": "FUKUSHIMA SERV. DE TELEC. E SOLUÇÕES",
    "TECNOLOGIA DA INFORMACAO E LOGISTICA": "TECNOLOGIA DA INFORMAÇÃO E LOGÍSTICA",
}

FILTER_COLUMNS = {
    "safra": ("SAFRA",),
    "tipo": ("DS_TIPO_DESCONEXAO",),
    "cidade": ("NM_CIDADE", "ANL_CIDADE_NORM", "ANL_CIDADE", "TOA_CIDADE"),
    "status": ("STATUS_OPERACIONAL", "SITUACAO_AGENDA", "ANL_STATUS_OS", "TOA_STATUS"),
    "uf": ("UF", "TOA_UF"),
}


def _key(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = " ".join(str(value).strip().split())
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).upper()


def _col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    cols = {_key(c): c for c in df.columns}
    for candidate in candidates:
        if _key(candidate) in cols:
            return cols[_key(candidate)]
    return None


def _id(value) -> str:
    value = _key(value)
    if value in INVALID:
        return ""
    return value[:-2] if re.fullmatch(r"\d+\.0", value) else value


def _partner(value) -> Optional[str]:
    key = _key(value)
    if key in INVALID:
        return None
    return DE_PARA.get(key, " ".join(str(value).strip().split()))


def _partner_series(df: pd.DataFrame) -> pd.Series:
    result = pd.Series(pd.NA, index=df.index, dtype="object")
    for candidate in ("PARCEIRA_NOME", "TOA_PARCEIRA", "TOA_AREA"):
        col = _col(df, (candidate,))
        if col is None:
            continue
        valid = ~df[col].map(_key).isin(INVALID)
        mask = result.isna() & valid
        result.loc[mask] = df.loc[mask, col]
    return result.map(_partner)


def _date(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", dayfirst=True)
    raw = series.astype("string").fillna("").str.strip()
    return parsed.dt.strftime("%Y-%m-%d").fillna(raw).replace("", "SEM_DATA")


def apply_filters(df: pd.DataFrame, filters: Optional[Mapping[str, Iterable[str]]]) -> pd.DataFrame:
    result = df.copy()
    for name, selected in (filters or {}).items():
        values = [str(v).strip() for v in (selected or []) if str(v).strip()]
        if not values:
            continue
        col = _col(result, FILTER_COLUMNS.get(name, (name,)))
        if col is not None:
            wanted = {_key(v) for v in values}
            result = result[result[col].map(_key).isin(wanted)]
    return result


def build_partner_ranking(df: pd.DataFrame, top_n: int = 10) -> Tuple[pd.DataFrame, dict]:
    cd_net = _col(df, ("CD_NET",))
    cd_os = _col(df, ("CD_OS",))
    anl_os = _col(df, ("ANL_NR_OS",))
    toa_date = _col(df, ("TOA_ULT_DATA",))
    pendencia = _col(df, ("PENDENCIA", "PENDÊNCIA"))
    missing = []
    if cd_net is None: missing.append("CD_NET")
    if cd_os is None and anl_os is None: missing.append("CD_OS/ANL_NR_OS")
    if toa_date is None: missing.append("TOA_ULT_DATA")
    if pendencia is None: missing.append("PENDENCIA")
    if missing:
        return pd.DataFrame(columns=["parceira", "total", "recup", "taxa"]), {
            "status": "colunas_ausentes", "missing": missing,
            "source": "safra_enriquecida", "uses_epo": False,
        }

    work = df.copy()
    work["parceira"] = _partner_series(work)
    work = work[work["parceira"].notna()].copy()
    work["_CD_NET"] = work[cd_net].map(_id)
    work["_OS"] = work[cd_os].map(_id) if cd_os else ""
    if anl_os:
        fallback = work["_OS"].eq("")
        work.loc[fallback, "_OS"] = work.loc[fallback, anl_os].map(_id)
    work["_DATA"] = _date(work[toa_date])
    work = work[(work["_CD_NET"] != "") & (work["_OS"] != "")].copy()
    work["_CHAVE"] = (work["_CD_NET"] + "|" + work["_OS"] + "|" +
                      work["_DATA"] + "|" + work["parceira"].map(_key))
    pend_raw = work[pendencia]
    pend_num = pd.to_numeric(pend_raw, errors="coerce")
    pend_text = pend_raw.astype("string").fillna("").map(_key)
    work["_RECUP"] = pend_num.eq(0) | pend_text.isin({
        "RECUPERADO", "RECUPERADA", "SIM", "S", "YES", "TRUE"
    })

    unique = work.groupby(["parceira", "_CHAVE"], as_index=False)["_RECUP"].max()
    ranking = unique.groupby("parceira", as_index=False).agg(
        total=("_CHAVE", "nunique"), recup=("_RECUP", "sum"))
    ranking["recup"] = ranking["recup"].astype(int)
    ranking["taxa"] = (ranking["recup"] / ranking["total"] * 100).round(1)
    ranking = ranking.sort_values(["total", "recup", "parceira"], ascending=[False, False, True])
    ranking = ranking.head(int(top_n)).reset_index(drop=True)
    return ranking, {
        "status": "ok", "source": "safra_enriquecida", "uses_epo": False,
        "valid_unique_keys": int(unique["_CHAVE"].nunique()),
        "partners_shown": int(len(ranking)),
    }


def _filtered_partner_ranking(
    df_enriquecida: pd.DataFrame, filters=None, allowed_cd_net=None, top_n: int = 10
):
    """Retorna um unico ranking filtrado, compartilhado por fig6 e fig7."""
    safe_filters = dict(filters or {})
    safe_filters.pop("status", None)
    filtered = apply_filters(df_enriquecida, safe_filters)

    if allowed_cd_net is not None:
        cd_net_col = _col(filtered, ("CD_NET",))
        allowed = {_id(v) for v in allowed_cd_net if _id(v)}
        if cd_net_col is not None:
            filtered = filtered[filtered[cd_net_col].map(_id).isin(allowed)]
        else:
            filtered = filtered.iloc[0:0].copy()

    ranking, meta = build_partner_ranking(filtered, top_n=top_n)
    meta["executive_filter_bridge"] = "CD_NET"
    meta["allowed_cd_net"] = len({_id(v) for v in (allowed_cd_net or []) if _id(v)})
    return ranking, meta


def _empty_partner_fig(message):
    fig = go.Figure()
    fig.add_annotation(
        text=message, showarrow=False, font=dict(size=14, color="#999999")
    )
    fig.update_layout(
        template="plotly_white", height=350,
        margin=dict(t=48, b=48, l=40, r=40),
    )
    return fig


def build_fig6(
    df_enriquecida: pd.DataFrame, filters=None, allowed_cd_net=None, top_n: int = 10
):
    """Fig6: volume de Total e Recuperados por parceira."""
    ranking, meta = _filtered_partner_ranking(
        df_enriquecida, filters, allowed_cd_net, top_n
    )
    meta["metrics"] = ["total", "recovered"]
    if ranking.empty:
        return _empty_partner_fig(
            "Sem chaves válidas de parceiras para os filtros selecionados"
        ), meta

    chart = ranking.sort_values(
        ["total", "recup", "parceira"], ascending=[False, False, True]
    ).reset_index(drop=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=chart["total"], y=chart["parceira"], orientation="h",
        name="Total", marker_color="#64748B", text=chart["total"],
        textposition="outside", cliponaxis=False,
        customdata=chart[["recup", "taxa"]],
        hovertemplate=(
            "<b>%{y}</b><br>Total: %{x}<br>Recuperados: %{customdata[0]}"
            "<br>Taxa: %{customdata[1]:.1f}%<extra></extra>"
        ),
    ))
    fig.add_trace(go.Bar(
        x=chart["recup"], y=chart["parceira"], orientation="h",
        name="Recuperados", marker_color="#22A35A", text=chart["recup"],
        textposition="outside", cliponaxis=False,
        customdata=chart[["total", "taxa"]],
        hovertemplate=(
            "<b>%{y}</b><br>Recuperados: %{x}<br>Total: %{customdata[0]}"
            "<br>Taxa: %{customdata[1]:.1f}%<extra></extra>"
        ),
    ))
    fig.update_layout(
        title="Top Parceiras - Total vs Recuperados", barmode="group",
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=48, b=48, l=235, r=70),
        xaxis=dict(title="Chaves distintas", automargin=True,
                   tickfont=dict(size=9, color="#344054"), gridcolor="#E5EAF2"),
        yaxis=dict(title="", autorange="reversed", automargin=True,
                   tickfont=dict(size=8, color="#344054")),
        legend=dict(orientation="h", x=0, y=-0.18,
                    font=dict(size=9, color="#344054")),
        font=dict(family="Arial", size=10, color="#344054"),
        title_font=dict(size=14, color="#243B64", family="Arial"), title_x=0.04,
    )
    return fig, meta


def build_fig7(
    df_enriquecida: pd.DataFrame, filters=None, allowed_cd_net=None, top_n: int = 10
):
    """Fig7: percentual de Recuperados para as mesmas Top parceiras do fig6."""
    ranking, meta = _filtered_partner_ranking(
        df_enriquecida, filters, allowed_cd_net, top_n
    )
    meta["metrics"] = ["recovery_percentage"]
    if ranking.empty:
        return _empty_partner_fig(
            "Sem percentuais de parceiras para os filtros selecionados"
        ), meta

    # Mesmo universo Top N do fig6. Dentro dele, ordena por eficiencia.
    chart = ranking.sort_values(
        ["taxa", "recup", "total", "parceira"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)

    fig = go.Figure(go.Bar(
        x=chart["taxa"], y=chart["parceira"], orientation="h",
        name="Recuperados %", marker_color="#E31937",
        text=[
            f"{taxa:.1f}%  |  Base: {int(total):,}".replace(",", ".")
            for taxa, total in zip(chart["taxa"], chart["total"])
        ],
        textposition="outside", cliponaxis=False,
        customdata=chart[["total", "recup"]],
        hovertemplate=(
            "<b>%{y}</b><br>Taxa recuperada: %{x:.1f}%"
            "<br>Total: %{customdata[0]}<br>Chaves recuperadas: %{customdata[1]}"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        title="Top Parceiras - Percentual de Recuperados",
        plot_bgcolor="white", paper_bgcolor="white", showlegend=False,
        margin=dict(t=48, b=48, l=235, r=70),
        xaxis=dict(title="Recuperados (%)", range=[0, 105], ticksuffix="%",
                   dtick=20, automargin=True,
                   tickfont=dict(size=9, color="#344054"), gridcolor="#E5EAF2"),
        yaxis=dict(title="", autorange="reversed", automargin=True,
                   tickfont=dict(size=8, color="#344054")),
        font=dict(family="Arial", size=10, color="#344054"),
        title_font=dict(size=14, color="#243B64", family="Arial"), title_x=0.04,
    )
    return fig, meta
