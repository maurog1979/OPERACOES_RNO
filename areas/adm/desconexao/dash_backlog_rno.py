# -*- coding: utf-8 -*-
"""
=====================================================================
PORTAL OPERACOES RNO
areas/adm/desconexao/dash_backlog_rno.py
Dashboard Backlog - os contratos da Safra na agenda
=====================================================================
ARQUIVO COMPLETO - substitua o anterior inteiro.

MUDANCA NESTA VERSAO
  Filtros no mesmo padrao do dash_backlog existente:

    - TODOS os filtros aceitam multipla selecao
    - separador '||' entre valores, como no dash_backlog
    - cascata: as opcoes de cada filtro derivam dos DEMAIS
    - sem filtro obrigatorio; vazio significa todos

  Consequencia: sem mes selecionado, soma os 8 meses.
  Numeros altos por padrao, mas consistente com o padrao ja aprovado.

CONCEITO
  A base e a SAFRA. O Backlog e a lente.
      FROM ft_safra_historico s     <- universo
      LEFT JOIN ft_backlog_atual b  <- lente

CRITERIO DE CONTAGEM
  Cada OS do Backlog conta no seu proprio dia de agenda.
  Um contrato com 3 OS em dias diferentes aparece nos 3 dias.

TRES METRICAS
  linhas     registros da Safra, compoe o percentual do indicador
  contratos  contratos distintos
  os         ordens de servico, equivale a visitas a executar

ROTAS
  GET  /dash/backlog-rno/                 pagina
  GET  /dash/backlog-rno/api/refresh      dados + opcoes em cascata
  GET  /dash/backlog-rno/api/matriz       cidade|parceira x agenda
  GET  /dash/backlog-rno/api/consulta     consulta 360 por contrato
  GET  /dash/backlog-rno/api/evolutivo    serie diaria
  GET  /dash/backlog-rno/api/diagnostico  status

ONDE SALVAR
  areas\\adm\\desconexao\\dash_backlog_rno.py
=====================================================================
"""

from flask import Blueprint, render_template, jsonify, request

try:
    from data.db_desconexao import query, COLLATION
except ImportError as e:
    print(f"[dash_backlog_rno] ERRO ao importar db_desconexao: {e}")
    raise


bp = Blueprint(
    "dash_backlog_rno",
    __name__,
    url_prefix="/dash/backlog-rno",
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


# ---------------------------------------------------------------------
# FILTROS
# Mesmo padrao do dash_backlog: multipla selecao com separador '||'
# ---------------------------------------------------------------------
CAMPOS = {
    "MES_REFERENCIA":     "s.MES_REFERENCIA",
    "SAFRA":              "s.SAFRA",
    "SITUACAO":           "_PENDENCIA_",          # tratado a parte
    "DS_TIPO_DESCONEXAO": "s.DS_TIPO_DESCONEXAO",
    "UF":                 "s.UF",
    "NM_MUNICIPIO":       "s.NM_MUNICIPIO",
    "NM_CLUSTER":         "s.NM_CLUSTER",
    "TOA_PARCEIRA":       "s.TOA_PARCEIRA",
}

# campos usados para montar as opcoes em cascata
CAMPOS_OPCOES = {
    "MES_REFERENCIA":     "MES_REFERENCIA",
    "SAFRA":              "SAFRA",
    "DS_TIPO_DESCONEXAO": "DS_TIPO_DESCONEXAO",
    "UF":                 "UF",
    "NM_MUNICIPIO":       "NM_MUNICIPIO",
    "NM_CLUSTER":         "NM_CLUSTER",
    "TOA_PARCEIRA":       "TOA_PARCEIRA",
}

SITUACOES = ["PENDENTE", "RECUPERADO"]


def parse_multi(valor):
    """Divide o parametro pelo separador '||', como no dash_backlog."""
    if not valor:
        return []
    return [v.strip() for v in str(valor).split("||") if v.strip()]


def ler_filtros():
    """Extrai todos os filtros da querystring."""
    return {campo: parse_multi(request.args.get(campo, ""))
            for campo in CAMPOS}


def montar_where(filtros, excluir=None, alias="s"):
    """
    Monta o WHERE a partir dos filtros.

    excluir  nome do campo a ignorar, usado para montar as opcoes
             em cascata de cada filtro
    """
    cond = ["1=1"]
    p = {}

    for campo, coluna in CAMPOS.items():
        if campo == excluir:
            continue

        vals = filtros.get(campo) or []
        if not vals:
            continue

        # SITUACAO nao e coluna, e traducao para PENDENCIA
        if campo == "SITUACAO":
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
    """
    Deriva as opcoes de cada filtro a partir dos DEMAIS filtros.
    Mesma logica de cascata do dash_backlog.
    """
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

    # SITUACAO e fixa
    opcoes["SITUACAO"] = SITUACOES

    return opcoes


# ---------------------------------------------------------------------
# EXPRESSOES DA AGENDA
# Precisam ser repetidas no GROUP BY. Alias de CASE em GROUP BY
# faz o MySQL retornar vazio com ONLY_FULL_GROUP_BY.
# ---------------------------------------------------------------------
GRUPO_AGENDA = """CASE
        WHEN b.CD_CONTRATO IS NULL
            THEN 'FORA DO BACKLOG'
        WHEN b.DATA_AGENDAMENTO IS NOT NULL
            THEN DATE_FORMAT(b.DATA_AGENDAMENTO, '%d/%m/%Y')
        ELSE COALESCE(NULLIF(TRIM(b.FX_TEMPO_BASE), ''),
                      'SEM CLASSIFICACAO')
    END"""

ORDEM_AGENDA = """CASE
        WHEN b.CD_CONTRATO IS NULL          THEN 3
        WHEN b.DATA_AGENDAMENTO IS NOT NULL THEN 1
        ELSE 2
    END"""

JOIN_BACKLOG = """LEFT JOIN ft_backlog_atual b
           ON  b.CD_CONTRATO  = s.CD_NET
           AND b.CD_OPERADORA = s.CD_OPERADORA"""


# =====================================================================
# PAGINA
# =====================================================================

@bp.route("/")
def index():
    df_f = query("""
        SELECT COUNT(DISTINCT DT_RELATORIO) AS fotos,
               MAX(DT_RELATORIO) AS ultima
        FROM ft_backlog_log
    """, cache_key="bk_fotos", ttl=600)

    foto = df_f.iloc[0].to_dict() if not df_f.empty else {}

    return render_template(
        "dash_backlog_rno.html",
        qtd_fotos=_int(foto.get("fotos")),
        ultima_foto=_txt(foto.get("ultima")),
    )


# =====================================================================
# API - REFRESH
# Devolve dados e opcoes em cascata, como no dash_backlog
# =====================================================================

@bp.route("/api/refresh")
def api_refresh():
    filtros = ler_filtros()
    where, p = montar_where(filtros)

    try:
        # ---------------- distribuicao da agenda ----------------
        df = query(f"""
            SELECT
                {ORDEM_AGENDA}              AS ordem,
                {GRUPO_AGENDA}              AS grupo,
                b.DATA_AGENDAMENTO          AS dt,
                COUNT(*)                    AS linhas,
                COUNT(DISTINCT s.CD_NET)    AS contratos,
                COUNT(DISTINCT b.CD_OS)     AS os
            FROM ft_safra_historico s
            {JOIN_BACKLOG}
            WHERE {where}
            GROUP BY
                {ORDEM_AGENDA},
                {GRUPO_AGENDA},
                b.DATA_AGENDAMENTO
            ORDER BY
                {ORDEM_AGENDA},
                b.DATA_AGENDAMENTO
        """, params=p)

        agenda = [{
            "grupo":      _txt(r["grupo"], "SEM CLASSIFICACAO"),
            "data":       _txt(r["dt"]),
            "ordem":      _int(r["ordem"]),
            "tem_data":   _int(r["ordem"]) == 1,
            "no_backlog": _int(r["ordem"]) != 3,
            "linhas":     _int(r["linhas"]),
            "contratos":  _int(r["contratos"]),
            "os":         _int(r["os"]),
        } for _, r in df.iterrows()]

        # ---------------- totais ----------------
        df_t = query(f"""
            SELECT
                COUNT(DISTINCT s.ID_SAFRA)                AS linhas,
                COUNT(DISTINCT s.CD_NET)                  AS contratos,
                COUNT(DISTINCT CASE WHEN b.CD_CONTRATO IS NOT NULL
                      THEN s.ID_SAFRA END)                AS no_backlog,
                COUNT(DISTINCT CASE WHEN b.CD_CONTRATO IS NULL
                      THEN s.ID_SAFRA END)                AS fora_backlog,
                COUNT(DISTINCT b.CD_OS)                   AS os_backlog,
                COUNT(DISTINCT CASE WHEN b.DATA_AGENDAMENTO IS NOT NULL
                      THEN b.CD_OS END)                   AS os_com_data,
                COUNT(DISTINCT CASE WHEN b.CD_CONTRATO IS NOT NULL
                      AND b.DATA_AGENDAMENTO IS NULL
                      THEN b.CD_OS END)                   AS os_sem_data,
                COUNT(DISTINCT s.NM_MUNICIPIO)            AS municipios,
                COUNT(DISTINCT s.MES_REFERENCIA)          AS meses,
                COUNT(DISTINCT CASE
                      WHEN DATEDIFF(b.DATA_AGENDAMENTO, CURDATE()) < 0
                      THEN b.CD_OS END)                   AS vencida,
                COUNT(DISTINCT CASE
                      WHEN DATEDIFF(b.DATA_AGENDAMENTO, CURDATE()) = 0
                      THEN b.CD_OS END)                   AS hoje,
                COUNT(DISTINCT CASE
                      WHEN DATEDIFF(b.DATA_AGENDAMENTO, CURDATE()) > 0
                      THEN b.CD_OS END)                   AS futura,
                ROUND(AVG(s.NR_DIAS_EM_ABERTO), 0)        AS media_dias
            FROM ft_safra_historico s
            {JOIN_BACKLOG}
            WHERE {where}
        """, params=p)

        t = df_t.iloc[0].to_dict() if not df_t.empty else {}
        linhas = _int(t.get("linhas"))
        nobk   = _int(t.get("no_backlog"))
        os_bk  = _int(t.get("os_backlog"))

        kpis = {
            "linhas":       linhas,
            "contratos":    _int(t.get("contratos")),
            "no_backlog":   nobk,
            "fora_backlog": _int(t.get("fora_backlog")),
            "os_backlog":   os_bk,
            "os_com_data":  _int(t.get("os_com_data")),
            "os_sem_data":  _int(t.get("os_sem_data")),
            "vencida":      _int(t.get("vencida")),
            "hoje":         _int(t.get("hoje")),
            "futura":       _int(t.get("futura")),
            "municipios":   _int(t.get("municipios")),
            "meses":        _int(t.get("meses")),
            "media_dias":   _int(t.get("media_dias")),
            "pct_backlog":  round(nobk / linhas * 100, 2) if linhas else 0,
            "pct_com_data": round(_int(t.get("os_com_data")) / os_bk * 100, 2)
                            if os_bk else 0,
        }

        # ---------------- motivos ----------------
        df_mot = query(f"""
            SELECT b.MOTIVO_REAG AS motivo,
                   COUNT(*) AS linhas,
                   COUNT(DISTINCT s.CD_NET) AS contratos,
                   COUNT(DISTINCT b.CD_OS) AS os
            FROM ft_safra_historico s
            INNER JOIN ft_backlog_atual b
                    ON  b.CD_CONTRATO  = s.CD_NET
                    AND b.CD_OPERADORA = s.CD_OPERADORA
            WHERE {where}
              AND b.MOTIVO_REAG IS NOT NULL
              AND TRIM(b.MOTIVO_REAG) NOT IN ('', '-3')
            GROUP BY b.MOTIVO_REAG
            ORDER BY os DESC
            LIMIT 15
        """, params=p)

        motivos = [{
            "motivo":    _txt(r["motivo"]),
            "linhas":    _int(r["linhas"]),
            "contratos": _int(r["contratos"]),
            "os":        _int(r["os"]),
        } for _, r in df_mot.iterrows()]

        # ---------------- opcoes em cascata ----------------
        opcoes = montar_opcoes(filtros)

        return jsonify({
            "ok": True,
            "empty": linhas == 0,
            "total": linhas,
            "options": opcoes,
            "kpis": kpis,
            "agenda": agenda,
            "motivos": motivos,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False, "empty": True, "erro": str(e),
            "options": {c: [] for c in CAMPOS},
        }), 500


# =====================================================================
# API - MATRIZ
# =====================================================================

@bp.route("/api/matriz")
def api_matriz():
    dimensao = request.args.get("dimensao", "cidade")
    filtros = ler_filtros()
    where, p = montar_where(filtros)

    coluna = {
        "cidade":   "s.NM_MUNICIPIO",
        "parceira": "s.TOA_PARCEIRA",
        "cluster":  "s.NM_CLUSTER",
        "tipo":     "s.DS_TIPO_DESCONEXAO",
    }.get(dimensao, "s.NM_MUNICIPIO")

    try:
        df = query(f"""
            SELECT
                {coluna}                    AS dim,
                {ORDEM_AGENDA}              AS ordem,
                {GRUPO_AGENDA}              AS grupo,
                b.DATA_AGENDAMENTO          AS dt,
                COUNT(*)                    AS linhas,
                COUNT(DISTINCT s.CD_NET)    AS contratos,
                COUNT(DISTINCT b.CD_OS)     AS os
            FROM ft_safra_historico s
            {JOIN_BACKLOG}
            WHERE {where}
              AND {coluna} IS NOT NULL
              AND TRIM({coluna}) <> ''
            GROUP BY
                {coluna},
                {ORDEM_AGENDA},
                {GRUPO_AGENDA},
                b.DATA_AGENDAMENTO
            ORDER BY
                {coluna},
                {ORDEM_AGENDA},
                b.DATA_AGENDAMENTO
        """, params=p)

        celulas = [{
            "dim":       _txt(r["dim"]),
            "grupo":     _txt(r["grupo"], "SEM CLASSIFICACAO"),
            "ordem":     _int(r["ordem"]),
            "tem_data":  _int(r["ordem"]) == 1,
            "linhas":    _int(r["linhas"]),
            "contratos": _int(r["contratos"]),
            "os":        _int(r["os"]),
        } for _, r in df.iterrows()]

        return jsonify({
            "ok": True,
            "dimensao": dimensao,
            "celulas": celulas,
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
    filtros = ler_filtros()
    where, p = montar_where(filtros)

    try:
        df = query(f"""
            SELECT l.DT_RELATORIO                        AS data,
                   COUNT(*)                              AS linhas,
                   COUNT(DISTINCT s.CD_NET)              AS contratos,
                   COUNT(DISTINCT l.CD_OS)               AS os,
                   COUNT(DISTINCT CASE
                         WHEN l.DATA_AGENDAMENTO IS NOT NULL
                         THEN l.CD_OS END)               AS com_data,
                   COUNT(DISTINCT CASE
                         WHEN l.DATA_AGENDAMENTO IS NULL
                         THEN l.CD_OS END)               AS sem_data
            FROM ft_safra_historico s
            INNER JOIN ft_backlog_log l
                    ON  l.CD_CONTRATO  = s.CD_NET
                    AND l.CD_OPERADORA = s.CD_OPERADORA
            WHERE {where}
            GROUP BY l.DT_RELATORIO
            ORDER BY l.DT_RELATORIO
        """, params=p)

        if df.empty:
            return jsonify({
                "ok": True, "qtd_fotos": 0, "datas": [],
                "linhas": [], "contratos": [], "os": [],
                "com_data": [], "sem_data": [],
            })

        return jsonify({
            "ok": True,
            "qtd_fotos": len(df),
            "datas":     [_txt(d) for d in df["data"]],
            "linhas":    [_int(v) for v in df["linhas"]],
            "contratos": [_int(v) for v in df["contratos"]],
            "os":        [_int(v) for v in df["os"]],
            "com_data":  [_int(v) for v in df["com_data"]],
            "sem_data":  [_int(v) for v in df["sem_data"]],
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "erro": str(e)}), 500


# =====================================================================
# API - CONSULTA 360 POR CONTRATO
# =====================================================================

@bp.route("/api/consulta")
def api_consulta():
    contrato = request.args.get("contrato", "").strip()

    if not contrato:
        return jsonify({"ok": False, "erro": "informe o contrato"}), 400

    try:
        # ---------- identificacao ----------
        df_id = query("""
            SELECT CD_NET, CD_OPERADORA, NM_MUNICIPIO, UF,
                   NM_REGIONAL, NM_CLUSTER, NM_SUBCLUSTER,
                   NM_SEGMENTO_MUNICIPIO, DS_STATUS_CONTR,
                   EPO, DDD, POSSUI_TEC_DEDICADO
            FROM ft_safra_historico
            WHERE CD_NET = :c
            ORDER BY MES_REFERENCIA DESC
            LIMIT 1
        """, params={"c": contrato})

        ident = {}
        if not df_id.empty:
            r = df_id.iloc[0]
            ident = {
                "contrato":     _txt(r["CD_NET"]),
                "operadora":    _int(r["CD_OPERADORA"]),
                "municipio":    _txt(r["NM_MUNICIPIO"]),
                "uf":           _txt(r["UF"]),
                "regional":     _txt(r["NM_REGIONAL"]),
                "cluster":      _txt(r["NM_CLUSTER"]),
                "subcluster":   _txt(r["NM_SUBCLUSTER"]),
                "segmento":     _txt(r["NM_SEGMENTO_MUNICIPIO"]),
                "status":       _txt(r["DS_STATUS_CONTR"]),
                "epo":          _txt(r["EPO"]),
                "ddd":          _txt(r["DDD"]),
                "tec_dedicado": _txt(r["POSSUI_TEC_DEDICADO"]),
            }

        # ---------- safra com equipamentos ----------
        df_sf = query("""
            SELECT MES_REFERENCIA, SAFRA, DS_TIPO_DESCONEXAO,
                   PENDENCIA, MOVIMENTACAO,
                   DT_BASE, DATA_PEND, DT_ACAO,
                   NR_DIAS_EM_ABERTO, NR_AGING_OS,
                   DS_MODELO_EQPTO, DS_SUBTIPO_EQPTO, SUB_TIPO_EQUIP,
                   NR_SERIAL, NR_MAC,
                   TOA_PARCEIRA, TOA_LOGIN_TECNICO, TOA_STATUS_ATIVIDADE,
                   META_VIGENTE
            FROM ft_safra_historico
            WHERE CD_NET = :c
            ORDER BY MES_REFERENCIA DESC, SAFRA, NR_SERIAL
        """, params={"c": contrato})

        safra = [{
            "mes":         _txt(r["MES_REFERENCIA"]),
            "safra":       _txt(r["SAFRA"]),
            "tipo":        _txt(r["DS_TIPO_DESCONEXAO"]),
            "pendencia":   "RECUPERADO" if _int(r["PENDENCIA"]) == 0
                           else "PENDENTE",
            "dt_base":     _txt(r["DT_BASE"]),
            "dt_pend":     _txt(r["DATA_PEND"]),
            "dt_acao":     _txt(r["DT_ACAO"]),
            "dias":        _int(r["NR_DIAS_EM_ABERTO"]),
            "aging":       _int(r["NR_AGING_OS"]),
            "equipamento": _txt(r["DS_MODELO_EQPTO"]),
            "subtipo":     _txt(r["SUB_TIPO_EQUIP"]),
            "serial":      _txt(r["NR_SERIAL"]),
            "mac":         _txt(r["NR_MAC"]),
            "parceira":    _txt(r["TOA_PARCEIRA"]),
            "tecnico":     _txt(r["TOA_LOGIN_TECNICO"]),
            "toa_status":  _txt(r["TOA_STATUS_ATIVIDADE"]),
            "meta":        round(_num(r["META_VIGENTE"]) * 100, 2),
        } for _, r in df_sf.iterrows()]

        # ---------- backlog ----------
        df_bk = query("""
            SELECT CD_OS, DT_RELATORIO, SITUACAO_AGENDA,
                   FX_TEMPO_BASE, DATA_AGENDAMENTO, DATA_ABERTURA_OS,
                   STATUS_OS, MOTIVO_REAG, NM_TECNOLOGIA,
                   SEGMENTO_CONTRATO, TIPO_ASSINANTE, QTDE_EQUIP_TOTAL
            FROM ft_backlog_atual
            WHERE CD_CONTRATO = :c
            ORDER BY DATA_AGENDAMENTO, CD_OS
        """, params={"c": contrato})

        backlog = [{
            "os":            _txt(r["CD_OS"]),
            "foto":          _txt(r["DT_RELATORIO"]),
            "situacao":      _txt(r["SITUACAO_AGENDA"]),
            "classificacao": _txt(r["FX_TEMPO_BASE"]),
            "dt_agenda":     _txt(r["DATA_AGENDAMENTO"]),
            "dt_abertura":   _txt(r["DATA_ABERTURA_OS"]),
            "status":        _txt(r["STATUS_OS"]),
            "motivo":        _txt(r["MOTIVO_REAG"]),
            "tecnologia":    _txt(r["NM_TECNOLOGIA"]),
            "segmento":      _txt(r["SEGMENTO_CONTRATO"]),
            "assinante":     _txt(r["TIPO_ASSINANTE"]),
            "equipamentos":  _int(r["QTDE_EQUIP_TOTAL"]),
        } for _, r in df_bk.iterrows()]

        # ---------- movimentacao ----------
        df_mov = query("""
            SELECT DT_RELATORIO, CD_OS, SITUACAO_AGENDA,
                   FX_TEMPO_BASE, DATA_AGENDAMENTO, MOTIVO_REAG
            FROM ft_backlog_log
            WHERE CD_CONTRATO = :c
            ORDER BY DT_RELATORIO DESC, CD_OS
            LIMIT 60
        """, params={"c": contrato})

        movimentacao = [{
            "data":          _txt(r["DT_RELATORIO"]),
            "os":            _txt(r["CD_OS"]),
            "situacao":      _txt(r["SITUACAO_AGENDA"]),
            "classificacao": _txt(r["FX_TEMPO_BASE"]),
            "dt_agenda":     _txt(r["DATA_AGENDAMENTO"]),
            "motivo":        _txt(r["MOTIVO_REAG"]),
        } for _, r in df_mov.iterrows()]

        # ---------- quebra ----------
        df_qb = query("""
            SELECT DATA_EVENTO, NR_ORDEM_SERVICO, TIPO_OS, STATUS_OS,
                   NM_TIPO_TRATAMENTO, NM_MOTIVO_REAGENDA,
                   NM_QUEBRA_RESPONSAVEL, NM_QUEBRA_CENARIO,
                   CD_CODIGO_BAIXA, DS_PERIODO_AGENDA,
                   TOA_PARCEIRA, TOA_LOGIN_TECNICO, TOA_BAIRRO,
                   CP_DSC_EMPRESA_EXECUCAO, CP_DSC_EQUIPE_TECNICA
            FROM ft_quebra_historico
            WHERE NR_CONTRATO = :c
            ORDER BY DATA_EVENTO DESC
            LIMIT 50
        """, params={"c": contrato})

        quebras = [{
            "data":        _txt(r["DATA_EVENTO"]),
            "os":          _txt(r["NR_ORDEM_SERVICO"]),
            "tipo_os":     _txt(r["TIPO_OS"]),
            "status":      _txt(r["STATUS_OS"]),
            "tratamento":  _txt(r["NM_TIPO_TRATAMENTO"]),
            "motivo":      _txt(r["NM_MOTIVO_REAGENDA"]),
            "responsavel": _txt(r["NM_QUEBRA_RESPONSAVEL"]),
            "cenario":     _txt(r["NM_QUEBRA_CENARIO"]),
            "cod_baixa":   _txt(r["CD_CODIGO_BAIXA"]),
            "periodo":     _txt(r["DS_PERIODO_AGENDA"]),
            "parceira":    _txt(r["TOA_PARCEIRA"]),
            "tecnico":     _txt(r["TOA_LOGIN_TECNICO"]),
            "bairro":      _txt(r["TOA_BAIRRO"]),
            "empresa":     _txt(r["CP_DSC_EMPRESA_EXECUCAO"]),
            "equipe":      _txt(r["CP_DSC_EQUIPE_TECNICA"]),
        } for _, r in df_qb.iterrows()]

        resumo = {
            "linhas_safra":   len(safra),
            "meses":          len({s["mes"] for s in safra}),
            "equipamentos":   len({s["serial"] for s in safra if s["serial"]}),
            "os_backlog":     len(backlog),
            "fotos_backlog":  len({m["data"] for m in movimentacao}),
            "eventos_quebra": len(quebras),
            "com_quebra":     sum(1 for q in quebras
                                  if "COM QUEBRA" in q["tratamento"]),
        }

        return jsonify({
            "ok": True,
            "contrato": contrato,
            "encontrado": bool(safra or backlog or quebras),
            "identificacao": ident,
            "resumo": resumo,
            "safra": safra,
            "backlog": backlog,
            "movimentacao": movimentacao,
            "quebras": quebras,
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
    try:
        df = query("""
            SELECT
                (SELECT COUNT(*) FROM ft_safra_historico)  AS safra,
                (SELECT COUNT(*) FROM ft_backlog_atual)    AS backlog,
                (SELECT COUNT(*) FROM ft_backlog_log)      AS log,
                (SELECT COUNT(DISTINCT DT_RELATORIO)
                   FROM ft_backlog_log)                    AS fotos,
                (SELECT COUNT(DISTINCT DATA_AGENDAMENTO)
                   FROM ft_backlog_atual
                   WHERE DATA_AGENDAMENTO IS NOT NULL)     AS datas_agenda,
                (SELECT COUNT(*) FROM ft_quebra_historico) AS quebra
        """)
        d = df.iloc[0].to_dict() if not df.empty else {}
        return jsonify({
            "ok": True,
            "safra":        _int(d.get("safra")),
            "backlog":      _int(d.get("backlog")),
            "log":          _int(d.get("log")),
            "fotos":        _int(d.get("fotos")),
            "datas_agenda": _int(d.get("datas_agenda")),
            "quebra":       _int(d.get("quebra")),
        })
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 500
