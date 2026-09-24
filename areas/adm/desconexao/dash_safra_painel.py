# -*- coding: utf-8 -*-
"""
=====================================================================
PORTAL OPERACOES RNO
areas/adm/desconexao/dash_safra_painel.py
Blueprint do Painel Safra (1 M / 4 M / 13 M)
=====================================================================
ARQUIVO COMPLETO E CORRIGIDO - substitua o anterior inteiro.

CORRECAO APLICADA
  UnboundLocalError: cannot access local variable 'safra'

  CAUSA: o print de DEBUG foi inserido ANTES da linha que define
  a variavel safra. Como consequencia, /api/filtros quebrava e o
  painel exibia apenas "Todos" em todos os filtros.

  SOLUCAO: prints de diagnostico removidos. O log fica a cargo do
  db_desconexao.py, que ja imprime cada consulta com seus parametros.

NOVIDADES DESTA VERSAO
  - /api/filtros agora devolve 10 filtros (antes 6)
    novos: parceira, regional, subcluster, segmento
  - /api/dados calcula GAP_VOL, GAP_PP e FALTAM_RECUPERAR
    (conceitos aproveitados do dash_safra_v8)
  - /api/evolutivo devolve tambem a meta e o gap por mes

ROTAS
  GET  /dash/safra-painel/                pagina
  GET  /dash/safra-painel/api/filtros     opcoes dos filtros
  GET  /dash/safra-painel/api/dados       painel + total
  GET  /dash/safra-painel/api/evolutivo   serie historica
  GET  /dash/safra-painel/api/diagnostico status da conexao

INDICADOR
  ICG = RECUPERADOS / DESCONECTADOS
  Validado: 1 M jan/2026 = 53,76% (6.357 / 11.825)

FAROL (limiar fixo da planilha)
  VERDE     ICG >= 65%
  AMARELO   ICG >= 60% e < 65%
  VERMELHO  ICG <  60%

ONDE SALVAR
  areas\\adm\\desconexao\\dash_safra_painel.py
=====================================================================
"""

from flask import Blueprint, render_template, jsonify, request

try:
    from data.db_desconexao import (
        safra_meses, safra_valores, safra_filtros,
        safra_painel, safra_total, safra_evolutivo,
        testar_conexao,
    )
except ImportError as e:
    print(f"[dash_safra_painel] ERRO ao importar db_desconexao: {e}")
    raise


bp = Blueprint(
    "dash_safra_painel",
    __name__,
    url_prefix="/dash/safra-painel",
    template_folder="templates",
)

SAFRAS_PADRAO = ["1 M", "4 M", "13 M"]

# chaves de filtro aceitas na querystring
CHAVES_FILTRO = [
    "status_contrato", "sub_tipo_equip", "tec_dedicado",
    "municipio", "uf", "cluster",
    "parceira", "regional", "subcluster", "segmento",
]


# =====================================================================
# HELPERS
# =====================================================================

def _num(v, default=0):
    """Converte para numero tratando None e NaN."""
    if v is None:
        return default
    try:
        f = float(v)
        return default if f != f else f        # NaN
    except (TypeError, ValueError):
        return default


def _int(v):
    return int(_num(v))


def _farol(icg):
    """Limiar fixo extraido da formatacao condicional da planilha."""
    if icg >= 65:
        return "VERDE"
    if icg >= 60:
        return "AMARELO"
    return "VERMELHO"


def _ler_filtros():
    """Extrai os filtros da querystring, ignorando TODOS."""
    f = {}
    for k in CHAVES_FILTRO:
        v = request.args.get(k)
        if v and v != "TODOS":
            f[k] = v
    return f


def _gap(desconec, recup, meta_pct):
    """
    Calcula o GAP contra a meta.
    Conceito aproveitado do dash_safra_v8.

    gap_pp    diferenca em pontos percentuais
    gap_vol   quantos contratos faltam para atingir a meta
    """
    if not desconec or not meta_pct:
        return {"gap_pp": 0, "gap_vol": 0, "faltam": 0}

    icg = recup / desconec * 100
    meta_qtd = desconec * meta_pct / 100

    return {
        "gap_pp":  round(icg - meta_pct, 2),
        "gap_vol": round(recup - meta_qtd),
        "faltam":  max(0, round(meta_qtd - recup)),
    }


# =====================================================================
# PAGINA
# =====================================================================

@bp.route("/")
def index():
    meses = safra_meses()
    try:
        safras = safra_valores() or SAFRAS_PADRAO
    except Exception:
        safras = SAFRAS_PADRAO

    return render_template(
        "dash_safra_painel.html",
        meses=meses,
        mes_atual=meses[0] if meses else None,
        safras=safras,
    )


# =====================================================================
# API - FILTROS
# =====================================================================

@bp.route("/api/filtros")
def api_filtros():
    mes = request.args.get("mes")
    safra = request.args.get("safra", "1 M")

    try:
        filtros = safra_filtros(mes, safra)
        return jsonify({
            "ok": True,
            "mes": mes,
            "safra": safra,
            "meses": safra_meses(),
            "safras": safra_valores() or SAFRAS_PADRAO,
            "filtros": filtros,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "erro": str(e)}), 500


# =====================================================================
# API - DADOS DO PAINEL
# =====================================================================

@bp.route("/api/dados")
def api_dados():
    mes = request.args.get("mes")
    safra = request.args.get("safra", "1 M")

    if not mes:
        meses = safra_meses()
        if not meses:
            return jsonify({"ok": False, "erro": "sem dados"}), 404
        mes = meses[0]

    filtros = _ler_filtros()

    try:
        df = safra_painel(mes, safra, filtros)
        total = safra_total(mes, safra, filtros)

        # ---------- linhas por municipio ----------
        linhas = []
        for _, r in df.iterrows():
            desc  = _int(r.get("DESCONEC_TOTAL"))
            recup = _int(r.get("RECUP_TOTAL"))
            icg   = _num(r.get("ICG_TOTAL"))

            # meta ponderada pelo mix da linha, para o GAP
            m_inad  = _num(r.get("META_INAD"))
            m_opcao = _num(r.get("META_OPCAO"))
            d_inad  = _int(r.get("DESCONEC_INAD"))
            d_opcao = _int(r.get("DESCONEC_OPCAO"))
            meta_lin = ((d_inad * m_inad + d_opcao * m_opcao) / desc
                        if desc else 0)

            g = _gap(desc, recup, meta_lin)

            linhas.append({
                "grupo":       r.get("GRUPO") or "",
                "municipio":   r.get("NM_MUNICIPIO") or "",
                "operadora":   _int(r.get("CD_OPERADORA")),

                "desc_inad":   d_inad,
                "desc_opcao":  d_opcao,
                "desc_total":  desc,
                "pct_desc_inad":  _num(r.get("PCT_DESCONEC_INAD")),
                "pct_desc_opcao": _num(r.get("PCT_DESCONEC_OPCAO")),

                "recup_inad":  _int(r.get("RECUP_INAD")),
                "recup_opcao": _int(r.get("RECUP_OPCAO")),
                "recup_total": recup,
                "pct_recup_inad":  _num(r.get("PCT_RECUP_INAD")),
                "pct_recup_opcao": _num(r.get("PCT_RECUP_OPCAO")),

                "pend_inad":   _int(r.get("PEND_INAD")),
                "pend_opcao":  _int(r.get("PEND_OPCAO")),
                "pend_total":  _int(r.get("PEND_TOTAL")),
                "pct_pend_inad":  _num(r.get("PCT_PEND_INAD")),
                "pct_pend_opcao": _num(r.get("PCT_PEND_OPCAO")),

                "icg_inad":    _num(r.get("ICG_INAD")),
                "icg_opcao":   _num(r.get("ICG_OPCAO")),
                "icg_total":   icg,

                "media_inad":  _int(r.get("MEDIA_DIAS_INAD")),
                "media_opcao": _int(r.get("MEDIA_DIAS_OPCAO")),
                "media_total": _int(r.get("MEDIA_DIAS_TOTAL")),

                "meta":        round(meta_lin, 2),
                "gap_pp":      g["gap_pp"],
                "gap_vol":     g["gap_vol"],
                "faltam":      g["faltam"],

                "farol":       r.get("FAROL") or _farol(icg),
            })

        # ---------- linha de total ----------
        t_desc  = _int(total.get("DESCONEC_TOTAL"))
        t_recup = _int(total.get("RECUP_TOTAL"))
        t_icg   = _num(total.get("ICG_TOTAL"))

        tm_inad  = _num(total.get("META_INAD"))
        tm_opcao = _num(total.get("META_OPCAO"))
        td_inad  = _int(total.get("DESCONEC_INAD"))
        td_opcao = _int(total.get("DESCONEC_OPCAO"))
        meta_tot = ((td_inad * tm_inad + td_opcao * tm_opcao) / t_desc
                    if t_desc else 0)

        gt = _gap(t_desc, t_recup, meta_tot)

        resumo = {
            "desc_inad":   td_inad,
            "desc_opcao":  td_opcao,
            "desc_total":  t_desc,
            "pct_desc_inad":  _num(total.get("PCT_DESCONEC_INAD")),
            "pct_desc_opcao": _num(total.get("PCT_DESCONEC_OPCAO")),

            "recup_inad":  _int(total.get("RECUP_INAD")),
            "recup_opcao": _int(total.get("RECUP_OPCAO")),
            "recup_total": t_recup,
            "pct_recup_inad":  _num(total.get("PCT_RECUP_INAD")),
            "pct_recup_opcao": _num(total.get("PCT_RECUP_OPCAO")),

            "pend_inad":   _int(total.get("PEND_INAD")),
            "pend_opcao":  _int(total.get("PEND_OPCAO")),
            "pend_total":  _int(total.get("PEND_TOTAL")),
            "pct_pend_inad":  _num(total.get("PCT_PEND_INAD")),
            "pct_pend_opcao": _num(total.get("PCT_PEND_OPCAO")),

            "icg_inad":    _num(total.get("ICG_INAD")),
            "icg_opcao":   _num(total.get("ICG_OPCAO")),
            "icg_total":   t_icg,

            "media_inad":  _int(total.get("MEDIA_DIAS_INAD")),
            "media_opcao": _int(total.get("MEDIA_DIAS_OPCAO")),
            "media_total": _int(total.get("MEDIA_DIAS_TOTAL")),

            "meta_inad":   tm_inad,
            "meta_opcao":  tm_opcao,
            "meta":        round(meta_tot, 2),
            "gap_pp":      gt["gap_pp"],
            "gap_vol":     gt["gap_vol"],
            "faltam":      gt["faltam"],

            "farol":       total.get("FAROL") or _farol(t_icg),
        }

        return jsonify({
            "ok": True,
            "mes": mes,
            "safra": safra,
            "filtros_aplicados": filtros,
            "total": resumo,
            "linhas": linhas,
            "qtd_linhas": len(linhas),
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "erro": str(e)}), 500


# =====================================================================
# API - EVOLUTIVO
# =====================================================================

@bp.route("/api/evolutivo")
def api_evolutivo():
    safra = request.args.get("safra", "1 M")

    try:
        df = safra_evolutivo(safra)

        if df.empty:
            return jsonify({
                "ok": True, "safra": safra,
                "meses": [], "icg_total": [], "icg_inad": [],
                "icg_opcao": [], "desconec": [], "recup": [],
                "farol": [],
            })

        return jsonify({
            "ok": True,
            "safra": safra,
            "meses":     df["MES_REFERENCIA"].tolist(),
            "icg_total": [_num(v) for v in df["ICG_TOTAL"]],
            "icg_inad":  [_num(v) for v in df["ICG_INAD"]],
            "icg_opcao": [_num(v) for v in df["ICG_OPCAO"]],
            "desconec":  [_int(v) for v in df["DESCONEC_TOTAL"]],
            "recup":     [_int(v) for v in df["RECUP_TOTAL"]],
            "pend":      [_int(v) for v in df["PEND_TOTAL"]],
            "farol":     df["FAROL"].tolist(),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "erro": str(e)}), 500


# =====================================================================
# API - DIAGNOSTICO
# =====================================================================

@bp.route("/api/diagnostico")
def api_diagnostico():
    return jsonify(testar_conexao())
