# -*- coding: utf-8 -*-
"""
=====================================================================
PORTAL OPERACOES RNO
data/db_desconexao.py - Conexao com o Data Mart desconexao_rno
=====================================================================
ARQUIVO COMPLETO E CORRIGIDO - substitua o anterior inteiro.

HISTORICO DE CORRECOES

  1) API retornava vazio sem erro
     CAUSA: pd.read_sql(text(sql), engine, params=...) nao vincula
            parametros nomeados em SQLAlchemy 2.x
     SOLUCAO: executar por conn.execute() e montar o DataFrame do cursor

  2) Illegal mix of collations (erro 1267)
     CAUSA: as colunas da vw_safra_base estao em utf8mb4_general_ci
            (herdadas do staging, que era TEXT) enquanto o parametro
            enviado pelo driver chega como utf8mb4_0900_ai_ci.
            O MySQL recusa comparar collations diferentes.
     SOLUCAO: aplicar COLLATE explicito nas comparacoes com parametro:
                WHERE campo = :param COLLATE utf8mb4_unicode_ci
              A funcao _eq() monta essa expressao de forma padronizada.

ONDE SALVAR
  OPERACOES_RNO\\data\\db_desconexao.py
=====================================================================
"""

import time
import pandas as pd
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------
# CONEXAO
# ---------------------------------------------------------------------
DB_DESCONEXAO = {
    "host":     "127.0.0.1",
    "port":     3306,
    "user":     "root",
    "password": "",
    "database": "desconexao_rno",
}

# collation usada nas comparacoes com parametro
COLLATION = "utf8mb4_unicode_ci"


def db_url():
    d = DB_DESCONEXAO
    senha = f":{d['password']}" if d["password"] else ""
    return (f"mysql+pymysql://{d['user']}{senha}"
            f"@{d['host']}:{d['port']}/{d['database']}"
            f"?charset=utf8mb4")


_engine = None

def get_engine():
    """Engine singleton com pool."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            db_url(),
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


# ---------------------------------------------------------------------
# CACHE
# ---------------------------------------------------------------------
_CACHE = {}
TTL_PADRAO = 1800          # 30 minutos
DEBUG = True               # imprime cada consulta no console


def query(sql, params=None, cache_key=None, ttl=TTL_PADRAO):
    """
    Executa consulta e retorna DataFrame.
    Usa conn.execute() para garantir a vinculacao dos parametros.
    """
    if cache_key and cache_key in _CACHE:
        item = _CACHE[cache_key]
        if time.time() - item["ts"] < ttl:
            return item["df"]

    t0 = time.time()
    try:
        with get_engine().connect() as conn:
            res = conn.execute(text(sql), params or {})
            linhas = res.fetchall()
            colunas = list(res.keys())
        df = pd.DataFrame(linhas, columns=colunas)
    except Exception as e:
        print(f"[DB_DESC] ERRO: {str(e)[:300]}")
        print(f"[DB_DESC] params: {params}")
        return pd.DataFrame()

    if cache_key:
        _CACHE[cache_key] = {
            "df": df,
            "ts": time.time(),
            "load_time": round(time.time() - t0, 2),
            "rows": len(df),
        }

    if DEBUG:
        print(f"[DB_DESC] {cache_key or 'query'}: {len(df):,} linhas "
              f"em {time.time() - t0:.2f}s | params={params}")

    return df


def limpar_cache(chave=None):
    global _CACHE
    if chave:
        _CACHE.pop(chave, None)
    else:
        _CACHE.clear()
    print(f"[DB_DESC] cache limpo: {chave or 'tudo'}")


def info_cache():
    return {k: {kk: vv for kk, vv in v.items() if kk != "df"}
            for k, v in _CACHE.items()}


# ---------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------

def _eq(coluna, param):
    """
    Monta comparacao de texto com COLLATE explicito.

    Necessario porque as colunas da vw_safra_base herdaram
    utf8mb4_general_ci do staging, enquanto o parametro chega como
    utf8mb4_0900_ai_ci. Sem o COLLATE, o MySQL lanca o erro 1267.
    """
    return f"{coluna} COLLATE {COLLATION} = :{param}"


def norm_safra(valor):
    """
    Normaliza a safra para o formato gravado no banco: '1 M', '4 M', '13 M'.
    Aceita variacoes: '1M', '1 m', ' 1  M ', '1+M'.
    """
    if not valor:
        return None
    v = str(valor).strip().upper().replace("+", " ")
    v = " ".join(v.split())
    if v.endswith("M") and " " not in v:
        v = v[:-1].strip() + " M"
    return v


MAPA_FILTROS = {
    "status_contrato": "DS_STATUS_CONTR",
    "sub_tipo_equip":  "SUB_TIPO_EQUIP",
    "tec_dedicado":    "POSSUI_TEC_DEDICADO",
    "municipio":       "NM_MUNICIPIO",
    "uf":              "UF",
    "cluster":         "NM_CLUSTER",
}


def _montar_where(mes, safra, filtros=None):
    """Monta a clausula WHERE e os parametros das consultas de safra."""
    filtros = filtros or {}
    where = [
        _eq("MES_REFERENCIA", "mes"),
        _eq("SAFRA", "safra"),
        "TIPO IN ('INAD','OPCAO')",
    ]
    p = {"mes": mes, "safra": norm_safra(safra)}

    for chave, coluna in MAPA_FILTROS.items():
        v = filtros.get(chave)
        if v and v != "TODOS":
            where.append(_eq(coluna, chave))
            p[chave] = v

    return " AND ".join(where), p


# ---------------------------------------------------------------------
# CONSULTAS - SAFRA
# ---------------------------------------------------------------------

def safra_meses():
    """Meses disponiveis, do mais recente para o mais antigo."""
    df = query("""
        SELECT DISTINCT MES_REFERENCIA
        FROM ft_safra_historico
        ORDER BY MES_REFERENCIA DESC
    """, cache_key="safra_meses", ttl=3600)
    return df["MES_REFERENCIA"].tolist() if not df.empty else []


def safra_valores():
    """Safras disponiveis, ordenadas por duracao."""
    df = query("""
        SELECT DISTINCT SAFRA
        FROM ft_safra_historico
        WHERE SAFRA IS NOT NULL
        ORDER BY CAST(REPLACE(SAFRA, ' M', '') AS UNSIGNED)
    """, cache_key="safra_valores", ttl=3600)
    return df["SAFRA"].tolist() if not df.empty else []


def safra_filtros(mes=None, safra=None):
    """
    Valores disponiveis para os filtros do painel.

    OTIMIZACAO
      A versao anterior fazia SEIS queries separadas (~1,2s cada,
      mais de 7s no total). Agora e UMA query com UNION ALL,
      respondendo em menos de 1 segundo.
    """
    safra = norm_safra(safra)

    cond = ["1=1"]
    p = {}
    if mes:
        cond.append(_eq("MES_REFERENCIA", "mes"))
        p["mes"] = mes
    if safra:
        cond.append(_eq("SAFRA", "safra"))
        p["safra"] = safra
    where = " AND ".join(cond)

    campos = [
        ("status_contrato", "DS_STATUS_CONTR"),
        ("sub_tipo_equip",  "SUB_TIPO_EQUIP"),
        ("tec_dedicado",    "POSSUI_TEC_DEDICADO"),
        ("municipio",       "NM_MUNICIPIO"),
        ("uf",              "UF"),
        ("cluster",         "NM_CLUSTER"),
        ("parceira",        "TOA_PARCEIRA"),
        ("regional",        "NM_REGIONAL"),
        ("subcluster",      "NM_SUBCLUSTER"),
        ("segmento",        "NM_SEGMENTO_MUNICIPIO"),
    ]

    blocos = []
    for chave, coluna in campos:
        blocos.append(f"""
            SELECT '{chave}' AS FILTRO, {coluna} AS VALOR
            FROM ft_safra_historico
            WHERE {where}
              AND {coluna} IS NOT NULL
              AND TRIM({coluna}) <> ''
            GROUP BY {coluna}
        """)

    sql = " UNION ALL ".join(blocos) + " ORDER BY FILTRO, VALOR"

    df = query(sql, params=p, cache_key=f"filtros_{mes}_{safra}", ttl=900)

    resultado = {chave: [] for chave, _ in campos}
    if not df.empty:
        for chave in resultado:
            resultado[chave] = df.loc[df["FILTRO"] == chave,
                                      "VALOR"].tolist()

    if DEBUG:
        resumo = " | ".join(f"{k}={len(v)}" for k, v in resultado.items())
        print(f"[DB_DESC] filtros -> {resumo}")

    return resultado


_METRICAS = """
            SUM(TIPO='INAD')                              AS DESCONEC_INAD,
            SUM(TIPO='OPCAO')                             AS DESCONEC_OPCAO,
            COUNT(*)                                      AS DESCONEC_TOTAL,
            ROUND(SUM(TIPO='INAD') /COUNT(*)*100, 2)      AS PCT_DESCONEC_INAD,
            ROUND(SUM(TIPO='OPCAO')/COUNT(*)*100, 2)      AS PCT_DESCONEC_OPCAO,

            SUM(TIPO='INAD'  AND PENDENCIA=0)             AS RECUP_INAD,
            SUM(TIPO='OPCAO' AND PENDENCIA=0)             AS RECUP_OPCAO,
            SUM(PENDENCIA=0)                              AS RECUP_TOTAL,
            ROUND(SUM(TIPO='INAD'  AND PENDENCIA=0)
                  /NULLIF(SUM(PENDENCIA=0),0)*100, 2)     AS PCT_RECUP_INAD,
            ROUND(SUM(TIPO='OPCAO' AND PENDENCIA=0)
                  /NULLIF(SUM(PENDENCIA=0),0)*100, 2)     AS PCT_RECUP_OPCAO,

            SUM(TIPO='INAD'  AND PENDENCIA=1)             AS PEND_INAD,
            SUM(TIPO='OPCAO' AND PENDENCIA=1)             AS PEND_OPCAO,
            SUM(PENDENCIA=1)                              AS PEND_TOTAL,
            ROUND(SUM(TIPO='INAD'  AND PENDENCIA=1)
                  /NULLIF(SUM(PENDENCIA=1),0)*100, 2)     AS PCT_PEND_INAD,
            ROUND(SUM(TIPO='OPCAO' AND PENDENCIA=1)
                  /NULLIF(SUM(PENDENCIA=1),0)*100, 2)     AS PCT_PEND_OPCAO,

            ROUND(SUM(TIPO='INAD'  AND PENDENCIA=0)
                  /NULLIF(SUM(TIPO='INAD'),0)*100, 2)     AS ICG_INAD,
            ROUND(SUM(TIPO='OPCAO' AND PENDENCIA=0)
                  /NULLIF(SUM(TIPO='OPCAO'),0)*100, 2)    AS ICG_OPCAO,
            ROUND(SUM(PENDENCIA=0)/COUNT(*)*100, 2)       AS ICG_TOTAL,

            ROUND(AVG(CASE WHEN TIPO='INAD'
                      THEN NR_DIAS_EM_ABERTO END), 0)     AS MEDIA_DIAS_INAD,
            ROUND(AVG(CASE WHEN TIPO='OPCAO'
                      THEN NR_DIAS_EM_ABERTO END), 0)     AS MEDIA_DIAS_OPCAO,
            ROUND(AVG(NR_DIAS_EM_ABERTO), 0)              AS MEDIA_DIAS_TOTAL,

            ROUND(MAX(CASE WHEN TIPO='INAD'
                      THEN META_VIGENTE END)*100, 2)      AS META_INAD,
            ROUND(MAX(CASE WHEN TIPO='OPCAO'
                      THEN META_VIGENTE END)*100, 2)      AS META_OPCAO,

            CASE
                WHEN SUM(PENDENCIA=0)/COUNT(*) >= 0.65 THEN 'VERDE'
                WHEN SUM(PENDENCIA=0)/COUNT(*) >= 0.60 THEN 'AMARELO'
                ELSE 'VERMELHO'
            END                                           AS FAROL
"""


def safra_painel(mes, safra, filtros=None):
    """Painel por municipio. Reproduz a planilha executiva."""
    where, p = _montar_where(mes, safra, filtros)
    sql = f"""
        SELECT GRUPO, NM_MUNICIPIO, CD_OPERADORA,
        {_METRICAS}
        FROM vw_safra_base
        WHERE {where}
        GROUP BY GRUPO, NM_MUNICIPIO, CD_OPERADORA
        ORDER BY DESCONEC_TOTAL DESC
    """
    return query(sql, params=p)


def safra_total(mes, safra, filtros=None):
    """Linha Total Geral do painel."""
    where, p = _montar_where(mes, safra, filtros)
    sql = f"""
        SELECT
        {_METRICAS}
        FROM vw_safra_base
        WHERE {where}
    """
    df = query(sql, params=p)
    return df.iloc[0].to_dict() if not df.empty else {}


def safra_evolutivo(safra):
    """Serie historica do ICG para o grafico de linha."""
    safra = norm_safra(safra)
    return query(f"""
        SELECT MES_REFERENCIA, ICG_TOTAL, ICG_INAD, ICG_OPCAO,
               DESCONEC_TOTAL, RECUP_TOTAL, PEND_TOTAL, FAROL
        FROM vw_safra_resumo
        WHERE {_eq('SAFRA', 'safra')}
        ORDER BY MES_REFERENCIA
    """, params={"safra": safra},
       cache_key=f"safra_evo_{safra}")


# ---------------------------------------------------------------------
# CONSULTAS - QUEBRA
# ---------------------------------------------------------------------

def quebra_evolutivo():
    return query("""
        SELECT MES_REFERENCIA, TOTAL_OS, COM_QUEBRA, SEM_QUEBRA,
               PCT_QUEBRA, PCT_SEM_QUEBRA, CONTRATOS, PARCEIRAS
        FROM vw_quebra_evolutivo
        ORDER BY MES_REFERENCIA
    """, cache_key="quebra_evo")


def quebra_municipio(mes):
    return query(f"""
        SELECT NM_MUNICIPIO, UF, NM_CLUSTER,
               TOTAL_OS, COM_QUEBRA, SEM_QUEBRA, PCT_QUEBRA
        FROM vw_quebra_municipio
        WHERE {_eq('MES_REFERENCIA', 'mes')}
        ORDER BY TOTAL_OS DESC
    """, params={"mes": mes})


def quebra_parceira(mes):
    return query(f"""
        SELECT TOA_PARCEIRA,
               SUM(TOTAL_OS)   AS TOTAL_OS,
               SUM(COM_QUEBRA) AS COM_QUEBRA,
               ROUND(SUM(COM_QUEBRA)/SUM(TOTAL_OS)*100, 2) AS PCT_QUEBRA,
               SUM(TECNICOS)   AS TECNICOS
        FROM vw_quebra_parceira
        WHERE {_eq('MES_REFERENCIA', 'mes')}
        GROUP BY TOA_PARCEIRA
        ORDER BY TOTAL_OS DESC
    """, params={"mes": mes})


def quebra_motivo(mes, limite=15):
    return query(f"""
        SELECT NM_MOTIVO_REAGENDA, SUM(QTD) AS QTD
        FROM vw_quebra_motivo
        WHERE {_eq('MES_REFERENCIA', 'mes')}
        GROUP BY NM_MOTIVO_REAGENDA
        ORDER BY QTD DESC
        LIMIT {int(limite)}
    """, params={"mes": mes})


# ---------------------------------------------------------------------
# CONSULTAS - BACKLOG
# ---------------------------------------------------------------------

def backlog_resumo():
    return query("""
        SELECT DT_RELATORIO,
               SUM(TOTAL_OS)   AS TOTAL_OS,
               SUM(CONTRATOS)  AS CONTRATOS,
               SUM(AGENDADOS)  AS AGENDADOS,
               SUM(SEM_AGENDA) AS SEM_AGENDA,
               ROUND(SUM(AGENDADOS)/SUM(TOTAL_OS)*100, 2)  AS PCT_AGENDADO,
               ROUND(SUM(SEM_AGENDA)/SUM(TOTAL_OS)*100, 2) AS PCT_SEM_AGENDA
        FROM vw_backlog_painel
        GROUP BY DT_RELATORIO
        ORDER BY DT_RELATORIO DESC
    """, cache_key="backlog_resumo", ttl=600)


def backlog_municipio():
    return query("""
        SELECT NM_MUNICIPIO, UF, TOTAL_OS, CONTRATOS,
               AGENDADOS, SEM_AGENDA, PCT_AGENDADO, PCT_SEM_AGENDA
        FROM vw_backlog_painel
        ORDER BY TOTAL_OS DESC
    """, cache_key="backlog_mun", ttl=600)


def backlog_aging():
    return query("""
        SELECT CLASSIFICACAO_AGENDA, SITUACAO_AGENDA,
               SUM(QTD) AS QTD, SUM(CONTRATOS) AS CONTRATOS
        FROM vw_backlog_aging
        GROUP BY CLASSIFICACAO_AGENDA, SITUACAO_AGENDA
        ORDER BY QTD DESC
    """, cache_key="backlog_aging", ttl=600)


def backlog_motivo(limite=15):
    return query(f"""
        SELECT MOTIVO_REAG, SUM(QTD) AS QTD
        FROM vw_backlog_motivo
        GROUP BY MOTIVO_REAG
        ORDER BY QTD DESC
        LIMIT {int(limite)}
    """, cache_key="backlog_motivo", ttl=600)


# ---------------------------------------------------------------------
# CONSULTA 360 POR CONTRATO
# ---------------------------------------------------------------------

def contrato_resumo(contrato, operadora=None):
    cond = ["CONTRATO = :c"]
    p = {"c": contrato}
    if operadora:
        cond.append("CD_OPERADORA = :o")
        p["o"] = operadora
    return query(f"""
        SELECT * FROM vw_consulta_contrato
        WHERE {' AND '.join(cond)}
        ORDER BY MES_REFERENCIA DESC
    """, params=p)


def contrato_timeline(contrato, operadora=None):
    cond = ["CONTRATO = :c"]
    p = {"c": contrato}
    if operadora:
        cond.append("CD_OPERADORA = :o")
        p["o"] = operadora
    return query(f"""
        SELECT * FROM vw_contrato_timeline
        WHERE {' AND '.join(cond)}
        ORDER BY DATA_EVENTO DESC, ORIGEM
    """, params=p)


# ---------------------------------------------------------------------
# DIAGNOSTICO
# ---------------------------------------------------------------------

def testar_conexao():
    """Verifica a conexao e a presenca das tabelas principais."""
    try:
        df = query("""
            SELECT
                (SELECT COUNT(*) FROM ft_quebra_historico) AS quebra,
                (SELECT COUNT(*) FROM ft_safra_historico)  AS safra,
                (SELECT COUNT(*) FROM ft_backlog_log)      AS backlog,
                (SELECT COUNT(*) FROM dim_metas)           AS metas
        """)
        if df.empty:
            return {"ok": False, "erro": "consulta vazia"}
        d = df.iloc[0].to_dict()
        return {"ok": True, "tabelas": {k: int(v) for k, v in d.items()}}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


def diagnostico_collation():
    """Lista a collation das colunas de texto da vw_safra_base."""
    return query("""
        SELECT COLUMN_NAME, DATA_TYPE, COLLATION_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = 'desconexao_rno'
          AND TABLE_NAME = 'vw_safra_base'
          AND COLLATION_NAME IS NOT NULL
        ORDER BY ORDINAL_POSITION
    """)


# =====================================================================
# TESTE
#   python data\db_desconexao.py
# =====================================================================

if __name__ == "__main__":
    print("=" * 62)
    print("  TESTE DE CONEXAO - desconexao_rno")
    print("=" * 62)

    r = testar_conexao()
    if not r["ok"]:
        print("  ERRO:", r["erro"])
        raise SystemExit(1)

    for k, v in r["tabelas"].items():
        print(f"  {k:<12} {v:>10,} linhas")

    print("\n  meses :", ", ".join(safra_meses()))
    print("  safras:", ", ".join(safra_valores()))

    print("\n" + "=" * 62)
    print("  COLLATIONS DA VIEW")
    print("=" * 62)
    dc = diagnostico_collation()
    if not dc.empty:
        distintas = dc["COLLATION_NAME"].unique().tolist()
        print(f"  encontradas: {', '.join(distintas)}")
        if len(distintas) > 1:
            print("  ATENCAO: mais de uma collation na mesma view")
        print(f"  usando nas comparacoes: {COLLATION}")

    print("\n" + "=" * 62)
    print("  TESTE DO PAINEL - 2026-01 / 1 M")
    print("=" * 62)

    print("\n  [1] norm_safra")
    for v in ["1 M", "1M", " 1  m ", "1+M", "13M"]:
        print(f"      {v!r:<10} -> {norm_safra(v)!r}")

    print("\n  [2] safra_total")
    t = safra_total("2026-01", "1 M")
    if t:
        ok = int(t.get("DESCONEC_TOTAL") or 0) == 11825
        print(f"      DESCONEC .. {int(t.get('DESCONEC_TOTAL') or 0):>7,}"
              f"   esperado 11.825")
        print(f"      RECUP ..... {int(t.get('RECUP_TOTAL') or 0):>7,}"
              f"   esperado  6.357")
        print(f"      PEND ...... {int(t.get('PEND_TOTAL') or 0):>7,}"
              f"   esperado  5.468")
        print(f"      ICG ....... {t.get('ICG_TOTAL')}%"
              f"   esperado 53.76%")
        print(f"      FAROL ..... {t.get('FAROL')}"
              f"   esperado VERMELHO")
        print(f"\n      RESULTADO: {'PASS' if ok else 'FALHA'}")
    else:
        print("      VAZIO - investigar")

    print("\n  [3] safra_painel")
    df = safra_painel("2026-01", "1 M")
    print(f"      {len(df)} municipios")
    if not df.empty:
        print()
        print(f"      {'MUNICIPIO':<16}{'DESCONEC':>9}{'ICG':>9}  FAROL")
        print("      " + "-" * 45)
        for _, x in df.head(8).iterrows():
            print(f"      {str(x['NM_MUNICIPIO']):<16}"
                  f"{int(x['DESCONEC_TOTAL']):>9,}"
                  f"{float(x['ICG_TOTAL']):>8.2f}%"
                  f"  {x['FAROL']}")

    print("\n  [4] safra_evolutivo")
    ev = safra_evolutivo("1 M")
    print(f"      {len(ev)} meses")
    if not ev.empty:
        for _, x in ev.iterrows():
            print(f"      {x['MES_REFERENCIA']}  "
                  f"ICG {float(x['ICG_TOTAL']):>6.2f}%  {x['FAROL']}")

    print("\n  [5] filtros disponiveis")
    f = safra_filtros("2026-01", "1 M")
    for k, v in f.items():
        print(f"      {k:<18} {len(v)} opcoes")

    print("\n" + "=" * 62)
