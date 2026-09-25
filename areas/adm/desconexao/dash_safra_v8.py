#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Blueprint, render_template, jsonify, request

import pymysql
import math
import re
from collections import defaultdict
import traceback
import logging

from config import Config

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

bp = Blueprint(
    "dash_safra",
    __name__,
    url_prefix="/dash/safra",
    template_folder="templates"
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
        **Config.db_config_pymysql(),
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

        if chave not in campos:
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
# OPCOES FILTRADAS (CASCATA)
# =====================================================

# Campo DISTINCT de cada filtro dentro da tabela mensal.
CAMPO_MENSAL = {
    "ano": "ano",
    "mes": "mes",
    "uf": "uf",
    "cidade": "cidade",
    "safra": "safra",
    "tipo": "ds_tipo_desconexao",
}


def montar_opcoes_filtradas(filters):
    """
    Deriva as opcoes disponiveis de cada filtro a partir dos DEMAIS
    filtros selecionados (excluindo o proprio campo) -> cascata.

    Ex.: com uf='AP', as opcoes de cidade trazem apenas MACAPA e SANTANA.
    A coluna 'dia' vive na tabela diaria; as demais na mensal.
    """

    opcoes = {}

    # Campos da tabela mensal
    for chave, coluna in CAMPO_MENSAL.items():

        sub = dict(filters)
        sub.pop(chave, None)   # exclui o proprio campo
        sub.pop("dia", None)   # 'dia' nao existe em safra_resumo_mensal

        where_sql, params = build_where(
            sub,
            "safra_resumo_mensal"
        )

        rows = query(
            f"""
            SELECT DISTINCT {coluna} AS v
            FROM safra_resumo_mensal
            {where_sql}
            ORDER BY v
            """,
            params
        )

        opcoes[chave] = [
            r["v"]
            for r in rows
        ]

    # Campo 'dia' usa a tabela diaria
    sub = dict(filters)
    sub.pop("dia", None)       # exclui o proprio campo

    where_sql, params = build_where(
        sub,
        "safra_resumo_diario"
    )

    rows = query(
        f"""
        SELECT DISTINCT dia AS v
        FROM safra_resumo_diario
        {where_sql}
        ORDER BY v
        """,
        params
    )

    opcoes["dia"] = [
        r["v"]
        for r in rows
    ]

    return opcoes

# =====================================================
# INDEX
# =====================================================

@bp.route("/")
def index():

    return render_template(
        "dash_safra_v9_visual.html"
    )

# =====================================================
# DIAGNOSTICO
# =====================================================

@bp.route("/api/diagnostico")
def diagnostico():

    try:

        query("SELECT 1 AS ok")
        return jsonify({
            "ok": True,
            "banco": Config.DB_NAME
        })

    except Exception as e:

        return jsonify({
            "ok": False,
            "erro": "Dados temporariamente indisponíveis."
        }), 503

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
        logger.exception("Falha na API Safra")
        return jsonify({
            "ok": False,
            "erro": "Não foi possível carregar os dados."
        }), 503

# =====================================================
# DATA
# =====================================================

# =====================================================
# HELPERS
# =====================================================

def to_float(value):
    try:
        number = float(value or 0)
        return number if math.isfinite(number) else 0.0
    except (ValueError, TypeError):
        return 0.0


def to_int(value):
    return int(to_float(value))


def _natural(value):
    number = re.search(r"\d+", str(value or ""))
    return (int(number.group()) if number else 999, str(value or ""))


def _detail_rows(rows):
    """Um único nível por período/safra/tipo evita somar RNO + UF + cidades."""
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(k) for k in ("ano", "mes", "dia", "safra", "ds_tipo_desconexao"))].append(row)
    result = []
    priority = {"CIDADE": 0, "UF": 1, "RNO": 2}
    for group in groups.values():
        levels = {str(r.get("nivel") or "").upper() for r in group}
        level = min(levels, key=lambda v: (priority.get(v, 3), v))
        result.extend(r for r in group if str(r.get("nivel") or "").upper() == level)
    return result


def _totals(rows):
    desc = sum(to_float(r.get("desc_total")) for r in rows)
    rec = sum(to_float(r.get("rec_total")) for r in rows)
    target = sum(to_float(r.get("meta_qtd")) if r.get("meta_qtd") is not None
                 else to_float(r.get("desc_total")) * to_float(r.get("meta_percentual")) / 100
                 for r in rows)
    return desc, rec, target


def _latest_daily(rows):
    groups = {}
    for row in rows:
        key = tuple(row.get(k) for k in ("ano", "mes", "nivel", "uf", "cidade", "safra", "ds_tipo_desconexao"))
        if key not in groups or to_int(row.get("dia")) > to_int(groups[key].get("dia")):
            groups[key] = row
    return list(groups.values())


def _monthly_snapshot(rows):
    """Filtro de dia usa o acumulado da última data selecionada, sem somar snapshots."""
    return [dict(r, desc_total=r.get("desc_total_mes"), rec_total=r.get("rec_acumulado"))
            for r in _latest_daily(rows)]


def montar_kpis(mensal, diario):
    rows = _detail_rows(mensal)
    desc, rec, target = _totals(rows)
    pct = rec / desc * 100 if desc else 0
    meta = target / desc * 100 if desc else 0
    gap = pct - meta
    daily = _latest_daily(_detail_rows(diario))
    # A necessidade diária refere-se ao período mais recente selecionado.
    latest_period = max(((to_int(r.get("ano")), to_int(r.get("mes"))) for r in daily), default=None)
    necessary = sum(to_float(r.get("necessario_por_dia")) for r in daily
                    if (to_int(r.get("ano")), to_int(r.get("mes"))) == latest_period)
    return {"desc": round(desc), "rec": round(rec), "pct": round(pct, 2),
            "meta": round(meta, 2), "gap_vol": round(rec - target), "gap_pct": round(gap, 2),
            "faltam": max(0, math.ceil(target - rec)), "necessario_dia": math.ceil(necessary),
            "tendencia": "SEM DADOS" if not desc else "ACIMA DA META" if gap >= 0
                         else "PRÓXIMO DA META" if gap >= -5 else "ABAIXO DA META"}


def _percent_groups(rows, key, output):
    groups = defaultdict(list)
    for row in rows:
        groups[row.get(key) or "N/I"].append(row)
    result = []
    for label, group in groups.items():
        desc, rec, _ = _totals(group)
        result.append({output: label, "pct": round(rec / desc * 100, 2) if desc else 0})
    return result


def montar_ranking(mensal):
    rows = [r for r in mensal if str(r.get("nivel") or "").upper() == "CIDADE"]
    return sorted(_percent_groups(rows, "cidade", "cidade"), key=lambda r: r["pct"], reverse=True)


def montar_comparativo(mensal):
    return sorted(_percent_groups(_detail_rows(mensal), "safra", "safra"), key=lambda r: _natural(r["safra"]))


def montar_tipos(mensal):
    return _percent_groups(_detail_rows(mensal), "ds_tipo_desconexao", "tipo")


def montar_matriz(mensal):
    groups = defaultdict(list)
    for row in mensal:
        level = str(row.get("nivel") or "RNO").upper()
        op = row.get("cidade") if level == "CIDADE" else row.get("uf") if level == "UF" else level
        groups[(row.get("safra") or "N/I", level, row.get("uf"), op)].append(row)
    result = []
    for (safra, level, uf, op), rows in groups.items():
        item = {"safra": safra, "operacao": op or level}
        for prefix, marker in (("inad", "INAD"), ("opcao", "OP")):
            subset = [r for r in rows if marker in str(r.get("ds_tipo_desconexao") or "").upper()]
            desc, rec, target = _totals(subset)
            item.update({prefix + "_desc": round(desc), prefix + "_rec": round(rec),
                         prefix + "_pct": round(rec / desc * 100, 2) if desc else 0,
                         prefix + "_gap_vol": round(rec - target),
                         prefix + "_gap_pct": round((rec - target) / desc * 100, 2) if desc else 0})
        result.append(item)
    return sorted(result, key=lambda r: (_natural(r["safra"]), r["operacao"] != "RNO", r["operacao"]))


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

        if filters.get("dia") and filters["dia"].lower() != "all":
            mensal = _monthly_snapshot(diario)

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

        opcoes = montar_opcoes_filtradas(
            filters
        )

        return jsonify({

            "ok": True,

            "options": opcoes,

            "kpis": kpis,

            "ranking": ranking,

            "comparativo": comparativo,

            "tipos": tipos,

            "matriz": matriz
        })

    except Exception:
        logger.exception("Falha na API Safra")
        return jsonify({
            "ok": False,
            "erro": "Não foi possível carregar os dados."
        }), 503
