# -*- coding: utf-8 -*-
"""
=====================================================================
PORTAL OPERACOES RNO
areas/adm/desconexao/dash_quebra_rno.py
Quebra de Agenda - os contratos da Safra na lente da quebra
=====================================================================

CONCEITO
  A base e a SAFRA. A Quebra e a lente.

      FROM ft_safra_historico s        <- universo
      LEFT JOIN ft_quebra_historico q  <- lente

  Nao mostra "a Quebra tem 182.893 eventos".
  Mostra "dos contratos da Safra, X tiveram quebra de agenda".

TRES MODOS  (herdados do dash_quebra)
  quantidade         volume absoluto de quebras
  taxa               quebras / total de eventos do grupo
  representatividade quebras do grupo / total de quebras

ANTI-MULTIPLICACAO
  Um contrato da Safra pode ter N eventos de quebra.
  As metricas usam COUNT(DISTINCT) conforme o que se quer medir:
      linhas da Safra   -> COUNT(DISTINCT s.ID_SAFRA)
      contratos         -> COUNT(DISTINCT s.CD_NET)
      eventos de quebra -> COUNT(DISTINCT q.ID_QUEBRA)

ROTAS
  GET  /dash/quebra-rno/                 pagina
  GET  /dash/quebra-rno/api/status       estado do cache
  GET  /dash/quebra-rno/api/refresh      dados + opcoes em cascata
  GET  /dash/quebra-rno/api/consulta     consulta 360 por contrato

ONDE SALVAR
  areas\\adm\\desconexao\\dash_quebra_rno.py
=====================================================================
"""

from flask import Blueprint, render_template, jsonify, request

try:
    from data.db_desconexao import query, COLLATION
except ImportError as e:
    print(f"[dash_quebra_rno] ERRO ao importar db_desconexao: {e}")
    raise


bp = Blueprint(
    "dash_quebra_rno",
    __name__,
    url_prefix="/dash/quebra-rno",
    template_folder="templates",
)


# =====================================================================
# HELPERS
# =====================================================================

def _num(v, default=0):
    if v is None:
        return default
    try:
        f = float(v)
        return default if f != f else f
    except (TypeError, ValueError):
        return default


def _int(v):
    return int(_num(v))


def _txt(v, default=""):
    """Trata None, NaN e NaT, que quebram o JSON."""
    if v is None:
        return default
    if isinstance(v, float) and v != v:
        return default
    s = str(v).strip()
    if s.lower() in ("nan", "none", "nat", "<na>"):
        return default
    return s


def _fmt_pct(v):
    return f"{v:.1f}%".replace(".", ",")


# ---------------------------------------------------------------------
# FILTROS
# Mesmo padrao do dash_quebra: multipla selecao, um parametro por valor
# ---------------------------------------------------------------------
CAMPOS = {
    "meses":     "s.MES_REFERENCIA",
    "safras":    "s.SAFRA",
    "situacao":  "_PENDENCIA_",
    "tipos":     "s.DS_TIPO_DESCONEXAO",
    "ufs":       "s.UF",
    "cids":      "s.NM_MUNICIPIO",
    "parcs":     "s.TOA_PARCEIRA",
}

CAMPOS_OPCOES = {
    "meses":  "MES_REFERENCIA",
    "safras": "SAFRA",
    "tipos":  "DS_TIPO_DESCONEXAO",
    "ufs":    "UF",
    "cids":   "NM_MUNICIPIO",
    "parcs":  "TOA_PARCEIRA",
}

SITUACOES = ["PENDENTE", "RECUPERADO"]

QUEBRA = "COM QUEBRA DE AGENDA"
SEM_QUEBRA = "SEM QUEBRA DE AGENDA"


def ler_lista(nome):
    """
    Le um filtro que pode vir repetido na querystring.
    O dash_quebra envia ?ufs=PA&ufs=AM
    """
    vals = request.args.getlist(nome)
    if not vals:
        bruto = request.args.get(nome, "")
        vals = bruto.split(",") if bruto else []
    return [str(v).strip() for v in vals
            if str(v).strip()
            and str(v).strip().lower() not in
            {"todos", "todas", "all", "null", "none"}]


def ler_filtros():
    return {campo: ler_lista(campo) for campo in CAMPOS}


def montar_where(filtros, excluir=None, alias="s"):
    """Monta o WHERE da Safra. excluir serve para a cascata."""
    cond = ["1=1"]
    p = {}

    for campo, coluna in CAMPOS.items():
        if campo == excluir:
            continue

        vals = filtros.get(campo) or []
        if not vals:
            continue

        if campo == "situacao":
            partes = []
            if "PENDENTE" in vals:
                partes.append(f"{alias}.PENDENCIA = 1")
            if "RECUPERADO" in vals:
                partes.append(f"{alias}.PENDENCIA = 0")
            if partes:
                cond.append("(" + " OR ".join(partes) + ")")
            continue

        col = coluna.replace("s.", f"{alias}.")
        marcas = []
        for i, v in enumerate(vals):
            chave = f"{campo}_{i}"
            marcas.append(f":{chave}")
            p[chave] = v
        cond.append(f"{col} COLLATE {COLLATION} IN ({', '.join(marcas)})")

    return " AND ".join(cond), p


def montar_opcoes(filtros):
    """Cascata: as opcoes de cada filtro derivam dos demais."""
    opcoes = {}

    for campo, coluna in CAMPOS_OPCOES.items():
        where, p = montar_where(filtros, excluir=campo)
        df = query(f"""
            SELECT DISTINCT {coluna} AS v
            FROM ft_safra_historico s
            WHERE {where}
              AND {coluna} IS NOT NULL
              AND TRIM({coluna}) <> ''
            ORDER BY v
        """, params=p)
        opcoes[campo] = [_txt(v) for v in df["v"]] if not df.empty else []

    opcoes["situacao"] = SITUACOES
    return opcoes


# ---------------------------------------------------------------------
# JOIN COM A QUEBRA
# ---------------------------------------------------------------------
JOIN_QUEBRA = """LEFT JOIN ft_quebra_historico q
           ON  q.NR_CONTRATO  = s.CD_NET
           AND q.CD_OPERADORA = s.CD_OPERADORA"""

# so os eventos de quebra, para os graficos de motivo e responsavel
JOIN_QUEBRA_INNER = """INNER JOIN ft_quebra_historico q
            ON  q.NR_CONTRATO  = s.CD_NET
            AND q.CD_OPERADORA = s.CD_OPERADORA"""


def serie(df, col_rotulo, total_quebras, modo, limite=None):
    """
    Monta a serie no formato que o frontend espera, com os tres modos.

    quantidade          eventos com quebra
    taxa                quebras / eventos do grupo
    representatividade  quebras do grupo / total geral de quebras
    """
    itens = []
    for _, r in df.iterrows():
        eventos = _int(r["eventos"])
        quebras = _int(r["quebras"])
        taxa = round(quebras / eventos * 100, 2) if eventos else 0
        repr_ = round(quebras / total_quebras * 100, 2) if total_quebras else 0

        if modo == "taxa":
            valor = taxa
        elif modo == "representatividade":
            valor = repr_
        else:
            valor = quebras

        itens.append({
            "label": _txt(r[col_rotulo], "NAO INFORMADO"),
            "valor": valor,
            "eventos": eventos,
            "quebras": quebras,
            "taxa": taxa,
            "representatividade": repr_,
            "contratos": _int(r.get("contratos")),
        })

    if limite:
        itens = sorted(itens, key=lambda x: x["valor"], reverse=True)[:limite]

    return {
        "labels":     [i["label"] for i in itens],
        "values":     [i["valor"] for i in itens],
        "customdata": [{
            "eventos": i["eventos"],
            "quebras": i["quebras"],
            "taxa": i["taxa"],
            "representatividade": i["representatividade"],
            "contratos": i["contratos"],
        } for i in itens],
        "mode": modo,
    }


# =====================================================================
# PAGINA
# =====================================================================

@bp.route("/")
def index():
    return render_template("dash_quebra_rno.html")


# =====================================================================
# API - STATUS
# =====================================================================

@bp.route("/api/status")
def api_status():
    try:
        df = query("""
            SELECT
                (SELECT COUNT(*) FROM ft_safra_historico)  AS safra,
                (SELECT COUNT(*) FROM ft_quebra_historico) AS quebra,
                (SELECT COUNT(DISTINCT MES_REFERENCIA)
                   FROM ft_quebra_historico)               AS meses
        """, cache_key="qb_status", ttl=600)

        d = df.iloc[0].to_dict() if not df.empty else {}
        return jsonify({
            "ok": True,
            "loaded": True,
            "rows": _int(d.get("quebra")),
            "safra": _int(d.get("safra")),
            "meses": _int(d.get("meses")),
        })
    except Exception as e:
        return jsonify({"ok": False, "loaded": False,
                        "rows": 0, "error": str(e)}), 500


# =====================================================================
# API - REFRESH
# =====================================================================

@bp.route("/api/refresh")
def api_refresh():
    modo = request.args.get("mode", "quantidade").strip().lower()
    if modo not in {"quantidade", "taxa", "representatividade"}:
        modo = "quantidade"

    filtros = ler_filtros()
    where, p = montar_where(filtros)

    try:
        # ---------------- KPIs ----------------
        df_k = query(f"""
            SELECT
                COUNT(DISTINCT s.ID_SAFRA)                     AS linhas,
                COUNT(DISTINCT s.CD_NET)                       AS contratos,
                COUNT(DISTINCT q.ID_QUEBRA)                    AS eventos,
                COUNT(DISTINCT CASE
                      WHEN q.NM_TIPO_TRATAMENTO = '{QUEBRA}'
                      THEN q.ID_QUEBRA END)                    AS quebras,
                COUNT(DISTINCT CASE
                      WHEN q.NM_TIPO_TRATAMENTO = '{SEM_QUEBRA}'
                      THEN q.ID_QUEBRA END)                    AS sem_quebra,
                COUNT(DISTINCT CASE
                      WHEN q.NM_TIPO_TRATAMENTO = '{QUEBRA}'
                      THEN s.CD_NET END)                       AS contr_quebra,
                COUNT(DISTINCT CASE WHEN q.NR_CONTRATO IS NULL
                      THEN s.CD_NET END)                       AS sem_evento,
                COUNT(DISTINCT s.NM_MUNICIPIO)                 AS municipios,
                COUNT(DISTINCT s.TOA_PARCEIRA)                 AS parceiras
            FROM ft_safra_historico s
            {JOIN_QUEBRA}
            WHERE {where}
        """, params=p)

        k = df_k.iloc[0].to_dict() if not df_k.empty else {}
        eventos = _int(k.get("eventos"))
        quebras = _int(k.get("quebras"))
        contratos = _int(k.get("contratos"))
        contr_qb = _int(k.get("contr_quebra"))

        taxa = round(quebras / eventos * 100, 2) if eventos else 0
        pct_contr = round(contr_qb / contratos * 100, 2) if contratos else 0

        kpis = {
            "linhas":       _int(k.get("linhas")),
            "contratos":    contratos,
            "eventos":      eventos,
            "quebras":      quebras,
            "sem_quebra":   _int(k.get("sem_quebra")),
            "contr_quebra": contr_qb,
            "sem_evento":   _int(k.get("sem_evento")),
            "municipios":   _int(k.get("municipios")),
            "parceiras":    _int(k.get("parceiras")),
            "taxa_quebra":  taxa,
            "taxa_quebra_label": _fmt_pct(taxa),
            "pct_contratos": pct_contr,
            "pct_contratos_label": _fmt_pct(pct_contr),
        }

        # ---------------- G1: evolucao mensal ----------------
        df_g1 = query(f"""
            SELECT q.MES_REFERENCIA                      AS rotulo,
                   COUNT(DISTINCT q.ID_QUEBRA)           AS eventos,
                   COUNT(DISTINCT CASE
                         WHEN q.NM_TIPO_TRATAMENTO = '{QUEBRA}'
                         THEN q.ID_QUEBRA END)           AS quebras,
                   COUNT(DISTINCT s.CD_NET)              AS contratos
            FROM ft_safra_historico s
            {JOIN_QUEBRA_INNER}
            WHERE {where}
            GROUP BY q.MES_REFERENCIA
            ORDER BY q.MES_REFERENCIA
        """, params=p)

        # ---------------- G2: por safra ----------------
        df_g2 = query(f"""
            SELECT s.SAFRA                               AS rotulo,
                   COUNT(DISTINCT q.ID_QUEBRA)           AS eventos,
                   COUNT(DISTINCT CASE
                         WHEN q.NM_TIPO_TRATAMENTO = '{QUEBRA}'
                         THEN q.ID_QUEBRA END)           AS quebras,
                   COUNT(DISTINCT s.CD_NET)              AS contratos
            FROM ft_safra_historico s
            {JOIN_QUEBRA_INNER}
            WHERE {where}
            GROUP BY s.SAFRA
            ORDER BY CAST(REPLACE(s.SAFRA, ' M', '') AS UNSIGNED)
        """, params=p)

        # ---------------- G3: cidades ----------------
        df_g3 = query(f"""
            SELECT s.NM_MUNICIPIO                        AS rotulo,
                   COUNT(DISTINCT q.ID_QUEBRA)           AS eventos,
                   COUNT(DISTINCT CASE
                         WHEN q.NM_TIPO_TRATAMENTO = '{QUEBRA}'
                         THEN q.ID_QUEBRA END)           AS quebras,
                   COUNT(DISTINCT s.CD_NET)              AS contratos
            FROM ft_safra_historico s
            {JOIN_QUEBRA_INNER}
            WHERE {where}
              AND s.NM_MUNICIPIO IS NOT NULL
            GROUP BY s.NM_MUNICIPIO
        """, params=p)

        # ---------------- G4: motivos ----------------
        df_g4 = query(f"""
            SELECT q.NM_MOTIVO_REAGENDA                  AS rotulo,
                   COUNT(DISTINCT q.ID_QUEBRA)           AS eventos,
                   COUNT(DISTINCT q.ID_QUEBRA)           AS quebras,
                   COUNT(DISTINCT s.CD_NET)              AS contratos
            FROM ft_safra_historico s
            {JOIN_QUEBRA_INNER}
            WHERE {where}
              AND q.NM_TIPO_TRATAMENTO = '{QUEBRA}'
              AND q.NM_MOTIVO_REAGENDA IS NOT NULL
              AND TRIM(q.NM_MOTIVO_REAGENDA) <> ''
            GROUP BY q.NM_MOTIVO_REAGENDA
        """, params=p)

        # ---------------- G5: parceiras ----------------
        df_g5 = query(f"""
            SELECT s.TOA_PARCEIRA                        AS rotulo,
                   COUNT(DISTINCT q.ID_QUEBRA)           AS eventos,
                   COUNT(DISTINCT CASE
                         WHEN q.NM_TIPO_TRATAMENTO = '{QUEBRA}'
                         THEN q.ID_QUEBRA END)           AS quebras,
                   COUNT(DISTINCT s.CD_NET)              AS contratos
            FROM ft_safra_historico s
            {JOIN_QUEBRA_INNER}
            WHERE {where}
              AND s.TOA_PARCEIRA IS NOT NULL
              AND TRIM(s.TOA_PARCEIRA) <> ''
            GROUP BY s.TOA_PARCEIRA
        """, params=p)

        # ---------------- G6: responsavel ----------------
        df_g6 = query(f"""
            SELECT q.NM_QUEBRA_RESPONSAVEL               AS rotulo,
                   COUNT(DISTINCT q.ID_QUEBRA)           AS eventos,
                   COUNT(DISTINCT q.ID_QUEBRA)           AS quebras,
                   COUNT(DISTINCT s.CD_NET)              AS contratos
            FROM ft_safra_historico s
            {JOIN_QUEBRA_INNER}
            WHERE {where}
              AND q.NM_TIPO_TRATAMENTO = '{QUEBRA}'
              AND q.NM_QUEBRA_RESPONSAVEL IS NOT NULL
              AND TRIM(q.NM_QUEBRA_RESPONSAVEL) <> ''
            GROUP BY q.NM_QUEBRA_RESPONSAVEL
        """, params=p)

        charts = {
            "g1": serie(df_g1, "rotulo", quebras, modo),
            "g2": serie(df_g2, "rotulo", quebras, modo),
            "g3": serie(df_g3, "rotulo", quebras, modo, limite=10),
            "g4": serie(df_g4, "rotulo", quebras, modo, limite=10),
            "g5": serie(df_g5, "rotulo", quebras, modo, limite=12),
            "g6": serie(df_g6, "rotulo", quebras, modo, limite=10),
        }

        opcoes = montar_opcoes(filtros)

        return jsonify({
            "ok": True,
            "mode": modo,
            "empty": eventos == 0,
            "options": opcoes,
            "kpis": kpis,
            "charts": charts,
            "diag": {"rows": eventos},
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False, "error": str(e),
            "options": {c: [] for c in CAMPOS},
        }), 500


# =====================================================================
# API - CONSULTA POR CONTRATO
# =====================================================================

@bp.route("/api/consulta")
def api_consulta():
    contrato = request.args.get("contrato", "").strip()

    if not contrato:
        return jsonify({"ok": False, "erro": "informe o contrato"}), 400

    try:
        df_id = query("""
            SELECT CD_NET, CD_OPERADORA, NM_MUNICIPIO, UF,
                   NM_REGIONAL, NM_CLUSTER, DS_STATUS_CONTR,
                   TOA_PARCEIRA
            FROM ft_safra_historico
            WHERE CD_NET = :c
            ORDER BY MES_REFERENCIA DESC
            LIMIT 1
        """, params={"c": contrato})

        ident = {}
        if not df_id.empty:
            r = df_id.iloc[0]
            ident = {
                "contrato":  _txt(r["CD_NET"]),
                "operadora": _int(r["CD_OPERADORA"]),
                "municipio": _txt(r["NM_MUNICIPIO"]),
                "uf":        _txt(r["UF"]),
                "regional":  _txt(r["NM_REGIONAL"]),
                "cluster":   _txt(r["NM_CLUSTER"]),
                "status":    _txt(r["DS_STATUS_CONTR"]),
                "parceira":  _txt(r["TOA_PARCEIRA"]),
            }

        df_qb = query("""
            SELECT DATA_EVENTO, MES_REFERENCIA, NR_ORDEM_SERVICO,
                   TIPO_OS, STATUS_OS, NM_TIPO_TRATAMENTO,
                   NM_MOTIVO_REAGENDA, NM_QUEBRA_RESPONSAVEL,
                   NM_QUEBRA_CENARIO, DS_PERIODO_AGENDA,
                   CD_CODIGO_BAIXA, TOA_PARCEIRA, TOA_LOGIN_TECNICO,
                   TOA_BAIRRO, CP_DSC_EMPRESA_EXECUCAO
            FROM ft_quebra_historico
            WHERE NR_CONTRATO = :c
            ORDER BY DATA_EVENTO DESC
            LIMIT 80
        """, params={"c": contrato})

        eventos = [{
            "data":        _txt(r["DATA_EVENTO"]),
            "mes":         _txt(r["MES_REFERENCIA"]),
            "os":          _txt(r["NR_ORDEM_SERVICO"]),
            "tipo_os":     _txt(r["TIPO_OS"]),
            "status":      _txt(r["STATUS_OS"]),
            "tratamento":  _txt(r["NM_TIPO_TRATAMENTO"]),
            "motivo":      _txt(r["NM_MOTIVO_REAGENDA"]),
            "responsavel": _txt(r["NM_QUEBRA_RESPONSAVEL"]),
            "cenario":     _txt(r["NM_QUEBRA_CENARIO"]),
            "periodo":     _txt(r["DS_PERIODO_AGENDA"]),
            "cod_baixa":   _txt(r["CD_CODIGO_BAIXA"]),
            "parceira":    _txt(r["TOA_PARCEIRA"]),
            "tecnico":     _txt(r["TOA_LOGIN_TECNICO"]),
            "bairro":      _txt(r["TOA_BAIRRO"]),
            "empresa":     _txt(r["CP_DSC_EMPRESA_EXECUCAO"]),
        } for _, r in df_qb.iterrows()]

        df_sf = query("""
            SELECT MES_REFERENCIA, SAFRA, DS_TIPO_DESCONEXAO,
                   PENDENCIA, NR_DIAS_EM_ABERTO,
                   DS_MODELO_EQPTO, NR_SERIAL
            FROM ft_safra_historico
            WHERE CD_NET = :c
            ORDER BY MES_REFERENCIA DESC
            LIMIT 30
        """, params={"c": contrato})

        safra = [{
            "mes":         _txt(r["MES_REFERENCIA"]),
            "safra":       _txt(r["SAFRA"]),
            "tipo":        _txt(r["DS_TIPO_DESCONEXAO"]),
            "pendencia":   "RECUPERADO" if _int(r["PENDENCIA"]) == 0
                           else "PENDENTE",
            "dias":        _int(r["NR_DIAS_EM_ABERTO"]),
            "equipamento": _txt(r["DS_MODELO_EQPTO"]),
            "serial":      _txt(r["NR_SERIAL"]),
        } for _, r in df_sf.iterrows()]

        com_quebra = sum(1 for e in eventos if e["tratamento"] == QUEBRA)

        return jsonify({
            "ok": True,
            "contrato": contrato,
            "encontrado": bool(eventos or safra),
            "identificacao": ident,
            "resumo": {
                "eventos":    len(eventos),
                "com_quebra": com_quebra,
                "sem_quebra": len(eventos) - com_quebra,
                "linhas_safra": len(safra),
                "meses": len({s["mes"] for s in safra}),
                "taxa": round(com_quebra / len(eventos) * 100, 1)
                        if eventos else 0,
            },
            "eventos": eventos,
            "safra": safra,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "erro": str(e)}), 500
