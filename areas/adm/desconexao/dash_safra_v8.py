#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Blueprint, render_template, jsonify, request

import pymysql
import traceback
import logging

from config import Config

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

bp = Blueprint(
    "dash_safra",
    __name__,
    url_prefix="/dash/safra"
)

# =====================================================
# BANCO
# =====================================================

DB_CONFIG = Config.db_config_pymysql()

# =====================================================
# MYSQL
# =====================================================

def get_conn():

    return pymysql.connect(
        **DB_CONFIG,
        cursorclass=pymysql.cursors.DictCursor
    )


def query(sql, params=None):

    conn = get_conn()

    try:

        with conn.cursor() as cur:

            cur.execute(
                sql,
                params or []
            )

            return cur.fetchall()

    finally:

        conn.close()

# =====================================================
# FILTROS
# =====================================================

def build_where(filters, tabela):

    campos = {
        "ano": "ano",
        "mes": "mes",
        "dia": "dia",
        "uf": "uf",
        "cidade": "cidade",
        "safra": "safra",
        "tipo": "ds_tipo_desconexao"
    }

    partes = []
    valores = []

    for chave, valor in filters.items():

        if valor is None:
            continue

        valor = str(valor).strip()

        if not valor:
            continue

        if valor.lower() == "all":
            continue

        if chave == "dia" and tabela == "safra_resumo_mensal":
            continue

        campo = campos[chave]

        if "," in valor:

            itens = [
                x.strip()
                for x in valor.split(",")
                if x.strip()
            ]

            if not itens:
                continue

            placeholders = ",".join(
                ["%s"] * len(itens)
            )

            partes.append(
                f"{campo} IN ({placeholders})"
            )

            valores.extend(itens)

        else:

            partes.append(
                f"{campo} = %s"
            )

            valores.append(valor)

    if not partes:
        return "", []

    return (
        " WHERE " + " AND ".join(partes),
        valores
    )

# =====================================================
# INDEX
# =====================================================

@bp.route("/")
def index():

    return render_template(
        "dash_safra.html"
    )

# =====================================================
# DIAGNOSTICO
# =====================================================

@bp.route("/api/diagnostico")
def diagnostico():

    try:

        return jsonify({
            "ok": True,
            "banco": "safra"
        })

    except Exception as e:

        return jsonify({
            "ok": False,
            "erro": str(e)
        })

# =====================================================
# OPTIONS
# =====================================================

@bp.route("/api/options")
def options():

    try:

        anos = query("""
            SELECT DISTINCT ano
            FROM safra_resumo_mensal
            ORDER BY ano
        """)

        meses = query("""
            SELECT DISTINCT mes
            FROM safra_resumo_mensal
            ORDER BY mes
        """)

        dias = query("""
            SELECT DISTINCT dia
            FROM safra_resumo_diario
            ORDER BY dia
        """)

        ufs = query("""
            SELECT DISTINCT uf
            FROM safra_resumo_mensal
            ORDER BY uf
        """)

        cidades = query("""
            SELECT DISTINCT cidade
            FROM safra_resumo_mensal
            ORDER BY cidade
        """)

        safras = query("""
            SELECT DISTINCT safra
            FROM safra_resumo_mensal
            ORDER BY safra
        """)

        tipos = query("""
            SELECT DISTINCT ds_tipo_desconexao
            FROM safra_resumo_mensal
            ORDER BY ds_tipo_desconexao
        """)

        return jsonify({

            "ok": True,

            "options": {

                "ano":
                    [x["ano"] for x in anos],

                "mes":
                    [x["mes"] for x in meses],

                "dia":
                    [x["dia"] for x in dias],

                "uf":
                    [x["uf"] for x in ufs],

                "cidade":
                    [x["cidade"] for x in cidades],

                "safra":
                    [x["safra"] for x in safras],

                "tipo":
                    [
                        x["ds_tipo_desconexao"]
                        for x in tipos
                    ]
            }
        })

    except Exception:

        return jsonify({
            "ok": False,
            "erro": traceback.format_exc()
        })

# =====================================================
# DATA
# =====================================================

# =====================================================
# HELPERS
# =====================================================

def to_float(v):

    try:
        return float(v or 0)

    except:
        return 0.0


def to_int(v):

    try:
        return int(float(v or 0))

    except:
        return 0


# =====================================================
# KPI
# =====================================================

def montar_kpis(mensal, diario):

    if not mensal:

        return {
            "desc": 0,
            "rec": 0,
            "pct": 0,
            "meta": 0,
            "gap_vol": 0,
            "gap_pct": 0,
            "faltam": 0,
            "necessario_dia": 0,
            "tendencia": "SEM DADOS"
        }

    desc = sum(
        to_float(x.get("desc_total"))
        for x in mensal
    )

    rec = sum(
        to_float(x.get("rec_total"))
        for x in mensal
    )

    meta = (
        sum(
            to_float(x.get("meta_percentual"))
            for x in mensal
        )
        / max(len(mensal), 1)
    )

    gap_vol = sum(
        to_float(x.get("gap_vol"))
        for x in mensal
    )

    gap_pct = (
        sum(
            to_float(x.get("gap_pp"))
            for x in mensal
        )
        / max(len(mensal), 1)
    )

    faltam = sum(
        to_float(x.get("faltam_recuperar"))
        for x in mensal
    )

    pct = 0

    if desc > 0:

        pct = (
            rec / desc
        ) * 100

    necessario = 0

    if diario:

        ultimo = sorted(
            diario,
            key=lambda x: (
                to_int(x.get("ano")),
                to_int(x.get("mes")),
                to_int(x.get("dia"))
            )
        )[-1]

        necessario = to_float(
            ultimo.get("necessario_por_dia")
        )

    if gap_pct >= 0:

        tendencia = "ACIMA DA META"

    elif gap_pct >= -5:

        tendencia = "PRÓXIMO DA META"

    else:

        tendencia = "ABAIXO DA META"

    return {

        "desc": round(desc),

        "rec": round(rec),

        "pct": round(pct, 2),

        "meta": round(meta, 2),

        "gap_vol": round(gap_vol),

        "gap_pct": round(gap_pct, 2),

        "faltam": round(faltam),

        "necessario_dia": round(necessario),

        "tendencia": tendencia
    }


# =====================================================
# RANKING
# =====================================================

def montar_ranking(mensal):

    cidades = {}

    for r in mensal:

        if r.get("nivel") != "CIDADE":
            continue

        cidade = r.get("cidade")

        cidades.setdefault(
            cidade,
            []
        ).append(
            to_float(
                r.get("perc_rec")
            )
        )

    ranking = []

    for cidade, valores in cidades.items():

        ranking.append({

            "cidade": cidade,

            "pct": round(
                sum(valores)
                / len(valores),
                2
            )
        })

    ranking.sort(
        key=lambda x: x["pct"],
        reverse=True
    )

    return ranking

# =====================================================
# COMPARATIVO
# =====================================================

def montar_comparativo(mensal):

    grupo = {}

    for r in mensal:

        safra = r.get("safra")

        grupo.setdefault(
            safra,
            []
        ).append(
            to_float(
                r.get("perc_rec")
            )
        )

    saida = []

    for safra, valores in grupo.items():

        saida.append({

            "safra": safra,

            "pct": round(
                sum(valores)
                / len(valores),
                2
            )
        })

    return sorted(
        saida,
        key=lambda x: x["safra"]
    )


# =====================================================
# TIPOS
# =====================================================

def montar_tipos(mensal):

    grupo = {}

    for r in mensal:

        tipo = (
            r.get("ds_tipo_desconexao")
            or "N/I"
        )

        grupo.setdefault(
            tipo,
            []
        ).append(
            to_float(
                r.get("perc_rec")
            )
        )

    saida = []

    for tipo, valores in grupo.items():

        saida.append({

            "tipo": tipo,

            "pct": round(
                sum(valores)
                / len(valores),
                2
            )
        })

    return saida


# =====================================================
# MATRIZ
# =====================================================

def montar_matriz(mensal):

    matriz = {}

    for r in mensal:

        op = (
            r.get("cidade")
            if r.get("nivel") == "CIDADE"
            else "RNO"
        )

        safra = r.get("safra")

        tipo = (
            r.get(
                "ds_tipo_desconexao"
            ) or ""
        ).upper()

        chave = (
            safra,
            op
        )

        if chave not in matriz:

            matriz[chave] = {

                "operacao": op,

                "safra": safra,

                "inad_pct": 0,
                "inad_desc": 0,
                "inad_rec": 0,
                "inad_gap_vol": 0,
                "inad_gap_pct": 0,

                "opcao_pct": 0,
                "opcao_desc": 0,
                "opcao_rec": 0,
                "opcao_gap_vol": 0,
                "opcao_gap_pct": 0
            }

        row = matriz[chave]

        if "INAD" in tipo:

            row["inad_pct"] = to_float(
                r.get("perc_rec")
            )

            row["inad_desc"] = to_int(
                r.get("desc_total")
            )

            row["inad_rec"] = to_int(
                r.get("rec_total")
            )

            row["inad_gap_vol"] = round(
                to_float(
                    r.get("gap_vol")
                )
            )

            row["inad_gap_pct"] = round(
                to_float(
                    r.get("gap_pp")
                ),
                2
            )

        else:

            row["opcao_pct"] = to_float(
                r.get("perc_rec")
            )

            row["opcao_desc"] = to_int(
                r.get("desc_total")
            )

            row["opcao_rec"] = to_int(
                r.get("rec_total")
            )

            row["opcao_gap_vol"] = round(
                to_float(
                    r.get("gap_vol")
                )
            )

            row["opcao_gap_pct"] = round(
                to_float(
                    r.get("gap_pp")
                ),
                2
            )

    return list(
        matriz.values()
    )

@bp.route("/api/data")
def data():

    try:

        filters = {

            "ano":
                request.args.get("ano"),

            "mes":
                request.args.get("mes"),

            "dia":
                request.args.get("dia"),

            "uf":
                request.args.get("uf"),

            "cidade":
                request.args.get("cidade"),

            "safra":
                request.args.get("safra"),

            "tipo":
                request.args.get("tipo")
        }

        mensal_where, mensal_params = build_where(
            filters,
            "safra_resumo_mensal"
        )

        diario_where, diario_params = build_where(
            filters,
            "safra_resumo_diario"
        )

        sql_mensal = f"""
            SELECT
                ano,
                mes,
                nivel,
                uf,
                cidade,
                safra,
                ds_tipo_desconexao,

                desc_total,
                rec_total,
                perc_rec,

                meta_percentual,
                meta_qtd,

                gap_vol,
                gap_pp,

                faltam_recuperar

            FROM safra_resumo_mensal

            {mensal_where}
        """

        mensal = query(
            sql_mensal,
            mensal_params
        )

        sql_diario = f"""
            SELECT

                ano,
                mes,
                dia,

                data_ref,

                nivel,
                uf,
                cidade,

                safra,
                ds_tipo_desconexao,

                desc_total_mes,
                rec_dia,
                rec_acumulado,

                perc_rec_acumulado,

                meta_percentual,
                meta_qtd,

                gap_vol_acumulado,
                gap_pp_acumulado,

                faltam_recuperar,
                dias_restantes,
                necessario_por_dia

            FROM safra_resumo_diario

            {diario_where}
        """

        diario = query(
            sql_diario,
            diario_params
        )

        # =================================================
        # PRÓXIMA ETAPA
        # =================================================
        #
        # KPI
        # Ranking
        # Comparativo
        # Tipos
        # Matriz
        #
        # usando:
        #
        # mensal
        # diario
        #

        kpis = montar_kpis(
            mensal,
            diario
        )

        ranking = montar_ranking(
            mensal
        )

        comparativo = montar_comparativo(
            mensal
        )

        tipos = montar_tipos(
            mensal
        )

        matriz = montar_matriz(
            mensal
        )

        return jsonify({

            "ok": True,

            "kpis": kpis,

            "ranking": ranking,

            "comparativo": comparativo,

            "tipos": tipos,

            "matriz": matriz
        })

    except Exception:

        return jsonify({
            "ok": False,
            "erro": traceback.format_exc()
        })