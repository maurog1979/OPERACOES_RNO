# -*- coding: utf-8 -*-
"""
============================================================
dash_executivo.py - Visao Executiva (Flask + Plotly.js)
============================================================
FIX 3:
- Categorical dtypes + cascata + sort natural + logs
- Pre-format text labels (evita literal %{text})
- Forca SAFRA/TIPO como string antes do plot
- Eixo Y do fig1 fixo em 0-105% com ticksuffix
- Eixo X do fig3 fixo em 0-105% com ticksuffix
============================================================
"""
import json
import re
import traceback

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from flask import Blueprint, jsonify, render_template, request

from data.db import load_table
from .partner_key_utils import build_fig6, build_fig7

COLORS_BAR = [
    "#E31937", "#0077B6", "#2ECC71", "#F4A300", "#9B59B6",
    "#E67E22", "#1ABC9C", "#34495E", "#C0392B", "#3498DB",
]
COLOR_RED = "#E31937"
COLOR_DARK = "#2C2C2C"
COLOR_GREEN = "#2ECC71"
COLOR_BLUE = "#0077B6"
COLOR_ORANGE = "#F4A300"

CATEGORICAL_COLS = [
    "SAFRA",
    "DS_TIPO_DESCONEXAO",
    "NM_CIDADE",
    "UF",
    "STATUS_OPERACIONAL",
    "ULT_PARCEIRA",
]


def find_col(df, keyword, exclude=None):
    exclude = exclude or []
    for c in df.columns:
        if keyword in c.upper() and all(ex not in c.upper() for ex in exclude):
            return c
    return None


def find_status_order(df):
    if "STATUS_OPERACIONAL" not in df.columns:
        return [], {}
    vals = df["STATUS_OPERACIONAL"].dropna().unique().tolist()
    color_map, order = {}, []
    keywords = [
        ("EM ANDAMENTO", "#2ECC71"),
        ("ATEN", "#F4A300"),
        ("ALTO", "#E67E22"),
        ("CRIT", "#E31937"),
    ]
    for v in vals:
        for kw, cor in keywords:
            if kw in str(v).upper():
                color_map[v] = cor
                order.append(v)
                break
        if v not in color_map:
            color_map[v] = "#999999"
            order.append(v)
    return order, color_map


def natural_sort_safras(values):
    def keyfn(v):
        m = re.search(r"\d+", str(v))
        return (int(m.group()) if m else 999, str(v))
    return sorted(values, key=keyfn)


def prepare_df(df):
    col_pend = find_col(df, "PEND", exclude=["DATA", "MES", "ANO"])
    print("[EXECUTIVO] Coluna PENDENCIA encontrada: {!r}".format(col_pend))
    if col_pend:
        df["_RECUP"] = (
            df[col_pend].fillna("1").astype(str).str.strip().eq("0").astype(int)
        )
    else:
        print("[EXECUTIVO] AVISO: Coluna PENDENCIA nao encontrada! Usando 0.")
        df["_RECUP"] = 0
    if len(df) > 0:
        recup_total = int(df["_RECUP"].sum())
        pct = recup_total / len(df) * 100
        print("[EXECUTIVO] Recuperados: {} / {} ({:.1f}%)".format(recup_total, len(df), pct))
    return df


def empty_fig(msg="Sem dados"):
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font=dict(size=14, color="#999"))
    fig.update_layout(
        template="plotly_white",
        height=350,
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(t=40, b=20, l=20, r=20),
    )
    return fig



# DE-PARA PARCEIRAS/EPO - INICIO
# Chaves normalizadas: maiúsculas, sem acento e com espaços simples.
DE_PARA_PARCEIRAS = {
    "NAO INFORMADO": "NÃO INFORMADO",
    "NAO INFORMADA": "NÃO INFORMADO",
    "SEM INFORMACAO": "NÃO INFORMADO",
    "SEM INFORMACAO DE PARCEIRA": "NÃO INFORMADO",
    "AFLINE INSTALACAO E MANUT ELETRICA": "AFLINE INSTALAÇÃO E MANUTENÇÃO ELÉTRICA",
    "AFLINE INSTALACAO E MANUTENCAO ELET": "AFLINE INSTALAÇÃO E MANUTENÇÃO ELÉTRICA",
    "AFLINE INSTALACAO E MANUTENCAO ELETRICA": "AFLINE INSTALAÇÃO E MANUTENÇÃO ELÉTRICA",
    "VIA REPRESENTACOES": "VIA REPRESENTAÇÕES",
    "HU SERVICOS / VIA REPRESENTACOES": "HU SERVIÇOS / VIA REPRESENTAÇÕES",
    "FUKUSHIMA SERV DE TELEC E SOLUCOES": "FUKUSHIMA SERV. DE TELEC. E SOLUÇÕES",
    "TECNOLOGIA DA INFORMACAO E LOGISTICA": "TECNOLOGIA DA INFORMAÇÃO E LOGÍSTICA",
    "ADUARTE ALBUQUERQUE ME / FUKUSHIMA SERV DE TELEC E SOLUCOES / H U SERVICOS DE TELECOMUNICACO ES L / TECNOLOGIA DA INFORMACAO E LOGISTICA": "PARCEIRAS ASSOCIADAS",
}


def _chave_parceira(valor):
    """Gera chave comparável sem alterar o valor original da base."""
    import unicodedata
    texto = " ".join(str(valor or "").strip().split())
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return texto.upper()


def normalizar_parceira(valor):
    """Aplica o DE-PARA; valores não mapeados permanecem legíveis."""
    texto = " ".join(str(valor or "").strip().split())
    if not texto:
        return "NÃO INFORMADO"
    chave = _chave_parceira(texto)
    return DE_PARA_PARCEIRAS.get(chave, texto)
# DE-PARA PARCEIRAS/EPO - FIM

def get_df():
    df = load_table("safra_final", categorical_cols=CATEGORICAL_COLS)
    if df.empty:
        return df
    if "_RECUP" not in df.columns:
        df = prepare_df(df.copy())
        from data.db import _DF_CACHE
        _DF_CACHE["safra_final"] = df
        for col in CATEGORICAL_COLS:
            if col in df.columns and df[col].dtype.name != "category":
                df[col] = df[col].astype("category")
    return df


def get_cascading_options(safras=None, tipos=None, cidades=None):
    df = get_df()
    if df.empty:
        return {"safras": [], "tipos": [], "cidades": [], "statuses": []}

    safras_opts = natural_sort_safras(
        [str(x) for x in df["SAFRA"].dropna().unique()]
    ) if "SAFRA" in df.columns else []

    dff = df
    if safras and "SAFRA" in dff.columns:
        dff = dff[dff["SAFRA"].astype(str).isin(safras)]
    tipos_opts = sorted([str(x) for x in dff["DS_TIPO_DESCONEXAO"].dropna().unique()]) \
        if "DS_TIPO_DESCONEXAO" in dff.columns else []

    if tipos and "DS_TIPO_DESCONEXAO" in dff.columns:
        dff = dff[dff["DS_TIPO_DESCONEXAO"].isin(tipos)]
    cidades_opts = sorted([str(x) for x in dff["NM_CIDADE"].dropna().unique()]) \
        if "NM_CIDADE" in dff.columns else []

    if cidades and "NM_CIDADE" in dff.columns:
        dff = dff[dff["NM_CIDADE"].isin(cidades)]
    statuses_opts = sorted([str(x) for x in dff["STATUS_OPERACIONAL"].dropna().unique()]) \
        if "STATUS_OPERACIONAL" in dff.columns else []

    return {
        "safras": safras_opts,
        "tipos": tipos_opts,
        "cidades": cidades_opts,
        "statuses": statuses_opts,
    }


def get_options():
    return get_cascading_options()


bp = Blueprint(
    "dash_executivo",
    __name__,
    url_prefix="/dash/executivo",
    template_folder="templates",
)


@bp.route("/")
def index():
    opts = get_options()
    return render_template("dash_executivo.html", opts=opts)


@bp.route("/api/options")
def api_options():
    try:
        safras = request.args.getlist("safra")
        tipos = request.args.getlist("tipo")
        cidades = request.args.getlist("cidade")
        opts = get_cascading_options(safras=safras, tipos=tipos, cidades=cidades)
        return jsonify(opts)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@bp.route("/api/data")
def api_data():
    try:
        df = get_df()
        if df.empty:
            return jsonify({
                "error": "Dados nao disponiveis. Verifique a tabela safra_final."
            }), 500

        safras = request.args.getlist("safra")
        tipos = request.args.getlist("tipo")
        cidades = request.args.getlist("cidade")
        statuses = request.args.getlist("status")

        dff = df.copy()
        if safras and "SAFRA" in dff.columns:
            dff = dff[dff["SAFRA"].astype(str).isin(safras)]
        if tipos and "DS_TIPO_DESCONEXAO" in dff.columns:
            dff = dff[dff["DS_TIPO_DESCONEXAO"].isin(tipos)]
        if cidades and "NM_CIDADE" in dff.columns:
            dff = dff[dff["NM_CIDADE"].isin(cidades)]
        if statuses and "STATUS_OPERACIONAL" in dff.columns:
            dff = dff[dff["STATUS_OPERACIONAL"].isin(statuses)]

        total = len(dff)
        recuperado = int(dff["_RECUP"].sum()) if "_RECUP" in dff.columns else 0
        pendente = total - recuperado
        taxa = (recuperado / total * 100) if total else 0

        print("[EXECUTIVO CB] Total: {} | Recup: {} | Taxa: {:.1f}%".format(total, recuperado, taxa))

        status_ordem, status_colors = find_status_order(dff)

        # FIG 1: Recuperacao por SAFRA e Tipo
        if (
            "SAFRA" in dff.columns
            and "DS_TIPO_DESCONEXAO" in dff.columns
            and total > 0
        ):
            grp = (
                dff.groupby(["SAFRA", "DS_TIPO_DESCONEXAO"], observed=True)
                .agg(total=("_RECUP", "count"), recup=("_RECUP", "sum"))
                .reset_index()
            )
            grp["taxa"] = (grp["recup"] / grp["total"] * 100).round(1)
            grp["taxa"] = grp["taxa"].astype(float)
            grp["taxa_fmt"] = grp["taxa"].apply(lambda v: "{:.1f}%".format(v))
            grp["SAFRA"] = grp["SAFRA"].astype(str)
            grp["DS_TIPO_DESCONEXAO"] = grp["DS_TIPO_DESCONEXAO"].astype(str)

            print("[EXECUTIVO FIG1] Agregacao SAFRA x TIPO:")
            print(grp[["SAFRA", "DS_TIPO_DESCONEXAO", "total", "recup", "taxa"]].to_string(index=False))

            safra_order = natural_sort_safras(grp["SAFRA"].unique().tolist())

            # Garante numerico explicito (evita Plotly ler como categorical)
            grp["taxa"] = pd.to_numeric(grp["taxa"], errors="coerce").fillna(0)
            fig1 = go.Figure()
            tipos_unicos = sorted(grp["DS_TIPO_DESCONEXAO"].unique().tolist())
            for i, tipo in enumerate(tipos_unicos):
                sub = grp[grp["DS_TIPO_DESCONEXAO"] == tipo]
                # Reordena conforme safra_order
                sub = sub.set_index("SAFRA").reindex(safra_order).reset_index()
                sub = sub.dropna(subset=["taxa"])
                cor = COLORS_BAR[i % len(COLORS_BAR)]
                fig1.add_trace(go.Bar(
                    name=tipo,
                    x=sub["SAFRA"].tolist(),
                    y=sub["taxa"].tolist(),
                    text=sub["taxa_fmt"].tolist(),
                    textposition="outside",
                    marker_color=cor,
                    cliponaxis=False,
                ))
            fig1.update_layout(
                title="Taxa de Recuperacao por SAFRA e Tipo",
                barmode="group",
                yaxis=dict(title="%", range=[0, 110], ticksuffix="%"),
                xaxis=dict(title="", type="category", categoryorder="array", categoryarray=safra_order),
                plot_bgcolor="white",
                margin=dict(t=50, b=40),
                legend=dict(orientation="h", y=-0.25, title=""),
            )
        else:
            fig1 = empty_fig("Dados insuficientes")

        # FIG 2: Donut Tipo
        if "DS_TIPO_DESCONEXAO" in dff.columns and total > 0:
            tipo_grp = dff["DS_TIPO_DESCONEXAO"].value_counts().reset_index()
            tipo_grp.columns = ["tipo", "qtd"]
            fig2 = px.pie(
                tipo_grp, names="tipo", values="qtd", hole=0.45,
                color_discrete_sequence=COLORS_BAR,
            )
            fig2.update_traces(textinfo="percent+label")
            fig2.update_layout(
                title="Distribuicao por Tipo de Desconexao",
                margin=dict(t=50), showlegend=False,
            )
        else:
            fig2 = empty_fig("Dados insuficientes")

        # FIG 3: Top 15 Cidades
        if "NM_CIDADE" in dff.columns and total > 0:
            cid_grp = (
                dff.groupby("NM_CIDADE", observed=True)
                .agg(total=("_RECUP", "count"), recup=("_RECUP", "sum"))
                .reset_index()
            )
            cid_grp["taxa"] = (cid_grp["recup"] / cid_grp["total"] * 100).round(1)
            cid_grp = cid_grp.sort_values("taxa", ascending=True).tail(15)
            cid_grp["taxa_fmt"] = cid_grp["taxa"].apply(lambda v: "{:.1f}%".format(v))
            cid_grp["NM_CIDADE"] = cid_grp["NM_CIDADE"].astype(str)

            cid_grp["taxa"] = pd.to_numeric(cid_grp["taxa"], errors="coerce").fillna(0)
            fig3 = go.Figure()
            fig3.add_trace(go.Bar(
                y=cid_grp["NM_CIDADE"].tolist(),
                x=cid_grp["taxa"].tolist(),
                text=cid_grp["taxa_fmt"].tolist(),
                textposition="outside",
                orientation="h",
                marker_color=COLOR_BLUE,
                cliponaxis=False,
            ))
            fig3.update_layout(
                title="Top 15 Cidades - Taxa de Recuperacao",
                xaxis=dict(title="%", range=[0, 110], ticksuffix="%"),
                yaxis=dict(title="", type="category"),
                plot_bgcolor="white",
                margin=dict(t=50, l=140),
            )
        else:
            fig3 = empty_fig("Dados insuficientes")

        # FIG 4: Evolucao Mensal
        if "SAFRA" in dff.columns and total > 0:
            evo = (
                dff.groupby("SAFRA", observed=True)
                .agg(total=("_RECUP", "count"), recup=("_RECUP", "sum"))
                .reset_index()
            )
            evo["taxa"] = (evo["recup"] / evo["total"] * 100).round(1)
            safra_order_evo = natural_sort_safras(evo["SAFRA"].astype(str).unique().tolist())
            evo["SAFRA"] = evo["SAFRA"].astype(str)
            evo["__ord"] = evo["SAFRA"].apply(lambda s: safra_order_evo.index(s))
            evo = evo.sort_values("__ord").drop(columns="__ord")

            fig4 = go.Figure()
            fig4.add_trace(go.Bar(
                x=evo["SAFRA"], y=evo["total"],
                name="Total Contratos",
                marker_color=COLOR_DARK, opacity=0.7,
                text=evo["total"].apply(lambda v: "{:,}".format(int(v)).replace(",", ".")),
                textposition="outside",
            ))
            fig4.add_trace(go.Scatter(
                x=evo["SAFRA"], y=evo["taxa"],
                name="Taxa Recuperacao %",
                mode="lines+markers+text",
                text=evo["taxa"].apply(lambda v: "{:.1f}%".format(v)),
                textposition="top center",
                line=dict(color=COLOR_RED, width=3),
                marker=dict(size=8),
                yaxis="y2",
            ))
            fig4.update_layout(
                title="Evolucao Mensal - Contratos vs Taxa",
                xaxis=dict(categoryorder="array", categoryarray=safra_order_evo),
                yaxis=dict(title="Contratos", side="left"),
                yaxis2=dict(title="Taxa %", side="right",
                            overlaying="y", showgrid=False, range=[0, 105]),
                legend=dict(orientation="h", y=-0.25),
                plot_bgcolor="white",
                margin=dict(t=50),
                barmode="overlay",
            )
        else:
            fig4 = empty_fig("Dados insuficientes")

        # FIG 5: Status Operacional
        if "STATUS_OPERACIONAL" in dff.columns and total > 0:
            st_grp_raw = (
                dff["STATUS_OPERACIONAL"].fillna("SEM INFO").value_counts()
            )
            if status_ordem:
                st_grp_raw = st_grp_raw.reindex(status_ordem).fillna(0)
            st_grp = st_grp_raw.reset_index()
            st_grp.columns = ["status", "qtd"]
            st_grp["status"] = st_grp["status"].astype(str)
            st_grp["cor"] = st_grp["status"].map(status_colors).fillna("#999")
            fig5 = go.Figure()
            fig5.add_trace(go.Bar(
                y=st_grp["status"], x=st_grp["qtd"],
                orientation="h",
                text=st_grp["qtd"].apply(
                    lambda v: "{:,}".format(int(v)).replace(",", ".")
                ),
                textposition="outside",
                marker_color=st_grp["cor"].tolist(),
                cliponaxis=False,
            ))
            fig5.update_layout(
                title="Distribuicao por Status Operacional",
                xaxis_title="Contratos",
                yaxis_title="",
                plot_bgcolor="white",
                margin=dict(t=50, l=130),
                yaxis=dict(autorange="reversed"),
            )
        else:
            fig5 = empty_fig("Dados insuficientes")

        # FIG 6: Top 10 Parceiras
        col_parc = "ULT_PARCEIRA"
        if col_parc in dff.columns and total > 0:
            par_grp = (
                dff.groupby(col_parc, observed=True)
                .agg(total=("_RECUP", "count"), recup=("_RECUP", "sum"))
                .reset_index()
            )
            par_grp["taxa"] = (par_grp["recup"] / par_grp["total"] * 100).round(1)
            par_grp = par_grp.sort_values("total", ascending=False).head(10)
            fig6 = go.Figure()
            fig6.add_trace(go.Bar(
                x=par_grp[col_parc].astype(str), y=par_grp["total"],
                name="Total", marker_color=COLOR_DARK, opacity=0.7,
            ))
            fig6.add_trace(go.Bar(
                x=par_grp[col_parc].astype(str), y=par_grp["recup"],
                name="Recuperados", marker_color=COLOR_GREEN,
            ))
            fig6.update_layout(
                title="Top 10 Parceiras - Total vs Recuperados",
                barmode="group",
                plot_bgcolor="white",
                margin=dict(t=50, b=100),
                xaxis_tickangle=-45,
                legend=dict(orientation="h", y=-0.35),
            )
        else:
            fig6 = empty_fig("Parceiras - coluna ULT_PARCEIRA nao encontrada")

        # ETAPA A V2: espessura visual das barras do Top 15 Cidades
        # bargap menor ocupa mais da faixa destinada a cada cidade.
        fig3.update_layout(bargap=0.08)

        # CORRECAO VISUAL: rotulos completos de cidades e folga da evolucao
        # FIG 3: o Plotly estava ocultando automaticamente parte das 15 categorias.
        # Tickmode=array obriga a exibicao de todos os nomes existentes no trace.
        if fig3.data and hasattr(fig3.data[0], "y"):
            cidades_tick = [str(v) if str(v).strip() else "NAO INFORMADA" for v in fig3.data[0].y]
            fig3.update_yaxes(
                tickmode="array",
                tickvals=list(fig3.data[0].y),
                ticktext=cidades_tick,
                automargin=True,
                tickfont=dict(size=9),
            )
            fig3.update_layout(margin=dict(t=48, l=145, r=52, b=42), bargap=0.08)

        # FIG 4: adiciona 18% de folga no eixo primario para os valores sobre as barras.
        # cliponaxis=False impede que os textos sejam recortados pelo limite do grafico.
        if fig4.data:
            valores_barras = []
            for trace in fig4.data:
                if getattr(trace, "type", "") == "bar":
                    trace.update(cliponaxis=False, textposition="outside")
                    valores_trace = getattr(trace, "y", None)
                    if valores_trace is not None:
                        for valor in valores_trace:
                            try:
                                valores_barras.append(float(valor))
                            except (TypeError, ValueError):
                                pass
            if valores_barras:
                limite_superior = max(valores_barras) * 1.18
                fig4.layout.yaxis.range = [0, limite_superior]
            fig4.update_layout(margin=dict(t=58, l=58, r=58, b=58))

        # AJUSTE EXECUTIVO: contraste dos percentuais e fallback de parceiras
        # Preserva integralmente a linha vermelha. Ajusta somente os textos da Taxa.
        # O ponto central (62,7%) fica sobre a barra cinza e recebe texto branco;
        # os pontos laterais permanecem em vermelho escuro sobre fundo branco.
        for trace in fig4.data:
            if getattr(trace, "type", "") == "scatter":
                qtd_pontos = len(trace.y) if getattr(trace, "y", None) is not None else 0
                cores_percentuais = ["#A60814"] * qtd_pontos
                if qtd_pontos >= 3:
                    cores_percentuais[qtd_pontos // 2] = "#FFFFFF"
                trace.update(
                    textfont=dict(
                        color=cores_percentuais,
                        size=10,
                        family="Arial Black, Arial, sans-serif",
                    )
                )

        # ULT_PARCEIRA está prevista como fonte principal. Quando não há valores
        # utilizáveis, EPO é empregada para que o comparativo não fique vazio.
        fonte_parceira = None
        if "ULT_PARCEIRA" in dff.columns:
            serie_ult = dff["ULT_PARCEIRA"].astype("string").str.strip()
            if serie_ult.notna().any() and serie_ult.fillna("").ne("").any():
                fonte_parceira = "ULT_PARCEIRA"
        if fonte_parceira is None and "EPO" in dff.columns:
            serie_epo = dff["EPO"].astype("string").str.strip()
            if serie_epo.notna().any() and serie_epo.fillna("").ne("").any():
                fonte_parceira = "EPO"

        if fonte_parceira:
            base_parceira = dff[[fonte_parceira, "_RECUP"]].copy()
            base_parceira[fonte_parceira] = (
                base_parceira[fonte_parceira].astype("string").str.strip()
            )
            # APLICA DE-PARA PARCEIRAS/EPO
            base_parceira[fonte_parceira] = (
                base_parceira[fonte_parceira].map(normalizar_parceira)
            )
            base_parceira = base_parceira[
                base_parceira[fonte_parceira].notna()
                & base_parceira[fonte_parceira].ne("")
            ]
            if not base_parceira.empty:
                par_grp_v2 = (
                    base_parceira.groupby(fonte_parceira, observed=True)
                    .agg(total=("_RECUP", "count"), recup=("_RECUP", "sum"))
                    .reset_index()
                    .sort_values("total", ascending=False)
                    .head(10)
                )
                fig6 = go.Figure()
                fig6.add_trace(go.Bar(
                    x=par_grp_v2[fonte_parceira].astype(str),
                    y=par_grp_v2["total"],
                    name="Total",
                    marker_color="#64748B",
                    text=par_grp_v2["total"],
                    textposition="outside",
                    cliponaxis=False,
                ))
                fig6.add_trace(go.Bar(
                    x=par_grp_v2[fonte_parceira].astype(str),
                    y=par_grp_v2["recup"],
                    name="Recuperados",
                    marker_color="#22A35A",
                    text=par_grp_v2["recup"],
                    textposition="outside",
                    cliponaxis=False,
                ))
                fig6.update_layout(
                    title="Top 10 Parceiras - Total vs Recuperados",
                    barmode="group",
                    plot_bgcolor="white",
                    paper_bgcolor="white",
                    margin=dict(t=48, b=88, l=45, r=25),
                    xaxis=dict(tickangle=-35, automargin=True, tickfont=dict(size=9)),
                    yaxis=dict(title="Contratos", automargin=True, tickfont=dict(size=9)),
                    legend=dict(orientation="h", y=-0.32, font=dict(size=9)),
                    font=dict(family="Arial", size=10, color="#344054"),
                    title_font=dict(size=14, color="#243B64", family="Arial"),
                    title_x=0.04,
                )

        # REFINO VISUAL: Top 10 Parceiras horizontal
        # Reaproveita exatamente os dados já calculados no fig6 e muda apenas
        # a orientação, evitando nomes longos inclinados e sobrepostos.
        if fig6.data:
            nomes_parceiras = None
            for trace in fig6.data:
                valores_atuais = list(trace.y) if getattr(trace, "y", None) is not None else []
                nomes_atuais = list(trace.x) if getattr(trace, "x", None) is not None else []
                if nomes_atuais and valores_atuais:
                    if nomes_parceiras is None:
                        nomes_parceiras = [str(v) for v in nomes_atuais]
                    trace.update(
                        x=valores_atuais,
                        y=[str(v) for v in nomes_atuais],
                        orientation="h",
                        text=valores_atuais,
                        textposition="outside",
                        cliponaxis=False,
                        textfont=dict(size=8),
                    )
            if nomes_parceiras:
                fig6.update_layout(
                    barmode="group",
                    margin=dict(t=48, b=48, l=235, r=62),
                    xaxis=dict(
                        title="Contratos",
                        automargin=True,
                        tickfont=dict(size=9),
                    ),
                    yaxis=dict(
                        title="",
                        autorange="reversed",
                        automargin=True,
                        tickmode="array",
                        tickvals=nomes_parceiras,
                        ticktext=nomes_parceiras,
                        tickfont=dict(size=8),
                    ),
                    legend=dict(
                        orientation="h",
                        x=0,
                        y=-0.18,
                        font=dict(size=9),
                    ),
                )

        # REFINO VISUAL GLOBAL: numeros com maior contraste
        # Aplica peso e contraste somente nos textos das séries. A linha de Taxa
        # permanece com o tratamento adaptativo já aprovado (62,7% em branco).
        for figura in [fig1, fig2, fig3, fig4, fig5, fig6]:
            figura.update_xaxes(tickfont=dict(size=9, color="#344054"))
            figura.update_yaxes(tickfont=dict(size=9, color="#344054"))
            figura.update_layout(
                font=dict(family="Arial", size=10, color="#344054"),
                legend_font=dict(size=9, color="#344054"),
            )
            for trace in figura.data:
                tipo_trace = getattr(trace, "type", "")
                if tipo_trace == "bar":
                    trace.update(textfont=dict(
                        color="#344054",
                        size=9,
                        family="Arial Black, Arial, sans-serif",
                    ))
                elif tipo_trace == "pie":
                    trace.update(textfont=dict(
                        color="#243B53",
                        size=9,
                        family="Arial Black, Arial, sans-serif",
                    ))

        # Parceiras: o nome completo continua no eixo/dado do trace e no hover,
        # mas o texto desenhado no eixo é abreviado para não invadir o card vizinho.
        if fig6.data and getattr(fig6.data[0], "y", None) is not None:
            nomes_completos = [str(v) for v in fig6.data[0].y]
            nomes_visuais = [
                nome if len(nome) <= 42 else nome[:39].rstrip() + "..."
                for nome in nomes_completos
            ]
            fig6.update_yaxes(
                tickmode="array",
                tickvals=nomes_completos,
                ticktext=nomes_visuais,
                tickfont=dict(size=8, color="#344054"),
                automargin=True,
            )
            fig6.update_layout(margin=dict(t=48, b=48, l=220, r=70))

        # FIG 6 - OVERRIDE CORPORATIVO FINAL
        # Fonte exclusiva: safra_enriquecida. O restante do Executivo permanece
        # integralmente baseado em safra_final. EPO nunca participa do cálculo.
        df_fig6 = load_table("safra_enriquecida")
        filtros_fig6 = {
            "safra": safras,
            "tipo": tipos,
            "cidade": cidades,
            "status": statuses,
        }
        if df_fig6 is None or df_fig6.empty:
            fig6 = empty_fig("Safra enriquecida indisponível para o fig6")
            meta_fig6 = {
                "status": "fonte_indisponivel",
                "source": "safra_enriquecida",
                "uses_epo": False,
            }
            fig7 = empty_fig("Safra enriquecida indisponível para o fig7")
            meta_fig7 = dict(meta_fig6)
        else:
            # O recorte por CD_NET vem do dff, que ja recebeu TODOS os filtros
            # do Executivo, inclusive STATUS_OPERACIONAL. Assim, o fig6 nao tenta
            # comparar status corporativo com SITUACAO_AGENDA/TOA_STATUS.
            cd_net_permitidos = (
                dff["CD_NET"].dropna().tolist()
                if "CD_NET" in dff.columns else []
            )
            fig6, meta_fig6 = build_fig6(
                df_enriquecida=df_fig6,
                filters=filtros_fig6,
                allowed_cd_net=cd_net_permitidos,
                top_n=10,
            )
            fig7, meta_fig7 = build_fig7(
                df_enriquecida=df_fig6,
                filters=filtros_fig6,
                allowed_cd_net=cd_net_permitidos,
                top_n=10,
            )
        print("[EXECUTIVO FIG6 CORPORATIVO]", meta_fig6)
        print("[EXECUTIVO FIG7 PERCENTUAL]", meta_fig7)

        return jsonify({
            "kpis": {
                "total": total,
                "recuperado": recuperado,
                "pendente": pendente,
                "taxa": round(taxa, 1),
            },
            "figs": {
                "fig1": json.loads(fig1.to_json()),
                "fig2": json.loads(fig2.to_json()),
                "fig3": json.loads(fig3.to_json()),
                "fig4": json.loads(fig4.to_json()),
                "fig5": json.loads(fig5.to_json()),
                "fig6": json.loads(fig6.to_json()),
                "fig7": json.loads(fig7.to_json()),
            },
        })

    except Exception as e:
        print("[EXECUTIVO ERRO] {}".format(e))
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
