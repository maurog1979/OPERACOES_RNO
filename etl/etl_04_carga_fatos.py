# -*- coding: utf-8 -*-
"""
=====================================================================
PORTAL OPERACOES RNO - DATA MART DESCONEXAO
Script 04 - CARGA DOS FATOS
=====================================================================
ARQUIVO COMPLETO E CORRIGIDO

CORRECAO APLICADA
  1) TypeError: %d format: a real number is required, not str
  2) OperationalError 1411: Incorrect datetime value

  CAUSA: o pymysql usa %s como placeholder de parametro. Quando o SQL
  contem STR_TO_DATE(campo, '%d/%m/%Y'), o driver interpreta o %d
  como placeholder numerico e falha.

  SOLUCAO 1: escapar todos os % de formato de data como %%.

  CAUSA 2: em sql_mode estrito o MySQL LANCA ERRO quando o
  STR_TO_DATE falha, em vez de retornar NULL. Assim o COALESCE
  nunca chegava a testar o segundo formato (caso de maio/2026).

  SOLUCAO 2: detectar o formato com REGEXP ANTES de converter,
  usando CASE WHEN. Mais SET SESSION sql_mode = '' na conexao.

POR QUE EM PYTHON E NAO EM SQL PURO
  As tentativas anteriores no HeidiSQL travaram ou derrubaram o MySQL
  em operacoes grandes. Aqui o processamento e MES A MES, com
  transacao individual. Se um mes falhar, os demais ficam intactos.

DECISOES APLICADAS (baseadas no perfilamento real)

  DATAS DA QUEBRA
    QUEBRA_05-2026.csv veio em formato ISO (2026/05/21 00:00:00);
    os demais em BR (21/05/2026 00:00).
    Solucao: COALESCE tentando os dois formatos.

  CAMPOS DESCARTADOS - perfilados como VAZIO ou 100% sentinela '-3'
    stg_quebra        CD_LOGIN_VENDEDOR, NM_TIPO_TRATAMENTO_CHIP,
                      CD_LOGIN_TECNICO, NM_UNIDADE_NEGOCIO_TECNICO
    stg_quebra_compl  DSC_TIPO_DESPACHO, DSC_TIPO_DEPACHO_OS,
                      DSC_CANAL_VENDA, DSC_CANAL_VENDA_GRUPO,
                      DSC_CANAL_VENDA_SUBGRUPO, LOGIN_VENDEDOR,
                      DSC_PARCEIRO_VENDA, DSC_AREA_RESP_MOTIVO_BI,
                      DSC_QUEBRA_CENARIO, COD_LOGIN_DESPACHO_OS
    stg_toa           CHAVE
    stg_safra         MES_REFERENCIA
    stg_backlog       FX_TEMPO_BASE, NM_AREA_GEO, EMPRESA_VENDEDOR

  BACKLOG - categoricos mantidos como texto
    AGING                 classificacao de agenda (7 valores)
    TEMPO_ABERTURA_DIAS   faixa textual
    DIAS_AGENDAMENTO      hibrido: data OU faixa
    AGING_REGULATORIO     unico aging numerico real

REGRA CRITICA
  Enriquecimento NUNCA altera o numero de linhas do fato.
  O script valida e faz ROLLBACK se detectar multiplicacao.

TESTE DE ACEITE
  2026-08 deve resultar em 63,14% (12.934 de 20.484).

USO
    python etl_04_carga_fatos.py                 # tudo
    python etl_04_carga_fatos.py --fato quebra
    python etl_04_carga_fatos.py --fato quebra --mes 2026-08
    python etl_04_carga_fatos.py --dry-run
=====================================================================
"""

import os
import sys
import time
import argparse
from datetime import datetime

try:
    import pymysql
except ImportError:
    sys.exit("ERRO: pymysql nao instalado.  Execute:  pip install pymysql")

try:
    from etl_config import DB
except ImportError:
    DB = {
        "host": "127.0.0.1", "port": 3306, "user": "root",
        "password": "", "database": "desconexao_rno", "charset": "utf8mb4",
    }

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"fatos_{datetime.now():%Y%m%d_%H%M%S}.log")


# =====================================================================
# EXPRESSOES DE CONVERSAO
# ATENCAO: todo % de formato de data e escapado como %%
#          porque o pymysql usa % como placeholder de parametro.
# =====================================================================

def data_flex(col):
    """
    Converte data detectando o formato ANTES de converter.

    IMPORTANTE: nao usar COALESCE de STR_TO_DATE. Em sql_mode estrito
    o MySQL lanca erro 1411 quando o STR_TO_DATE falha, em vez de
    retornar NULL. Por isso o formato e identificado com REGEXP.

    Formatos tratados:
      dd/mm/aaaa hh:mm      padrao BR  (7 dos 8 meses)
      aaaa/mm/dd hh:mm:ss   ISO        (apenas QUEBRA_05-2026)
    """
    c = f"SUBSTRING_INDEX(TRIM({col}), ' ', 1)"
    return (f"CASE "
            f"WHEN {c} REGEXP '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$' "
            f"THEN STR_TO_DATE({c}, '%%d/%%m/%%Y') "
            f"WHEN {c} REGEXP '^[0-9]{{4}}/[0-9]{{2}}/[0-9]{{2}}$' "
            f"THEN STR_TO_DATE({c}, '%%Y/%%m/%%d') "
            f"WHEN {c} REGEXP '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$' "
            f"THEN STR_TO_DATE({c}, '%%Y-%%m-%%d') "
            f"ELSE NULL END")


def dt_flex(col):
    """
    Converte datetime detectando o formato ANTES de converter.
    Mesma protecao contra o erro 1411 do sql_mode estrito.
    """
    t = f"TRIM({col})"
    return (f"CASE "
            f"WHEN {t} REGEXP '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}} [0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}' "
            f"THEN STR_TO_DATE({t}, '%%d/%%m/%%Y %%H:%%i:%%s') "
            f"WHEN {t} REGEXP '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}} [0-9]{{2}}:[0-9]{{2}}' "
            f"THEN STR_TO_DATE({t}, '%%d/%%m/%%Y %%H:%%i') "
            f"WHEN {t} REGEXP '^[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}$' "
            f"THEN STR_TO_DATE({t}, '%%d/%%m/%%Y') "
            f"WHEN {t} REGEXP '^[0-9]{{4}}/[0-9]{{2}}/[0-9]{{2}} [0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}' "
            f"THEN STR_TO_DATE({t}, '%%Y/%%m/%%d %%H:%%i:%%s') "
            f"WHEN {t} REGEXP '^[0-9]{{4}}/[0-9]{{2}}/[0-9]{{2}}$' "
            f"THEN STR_TO_DATE({t}, '%%Y/%%m/%%d') "
            f"WHEN {t} REGEXP '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}' "
            f"THEN STR_TO_DATE(SUBSTRING({t},1,10), '%%Y-%%m-%%d') "
            f"ELSE NULL END")


def inteiro(col):
    """Converte para inteiro tratando vazio e sentinela -3."""
    return (f"CASE WHEN TRIM({col}) REGEXP '^-?[0-9]+$' "
            f"AND TRIM({col}) <> '-3' "
            f"THEN CAST(TRIM({col}) AS SIGNED) ELSE NULL END")


def texto(col, tam):
    """Corta texto e converte sentinela -3 em NULL."""
    return (f"CASE WHEN TRIM({col}) IN ('', '-3') THEN NULL "
            f"ELSE LEFT(TRIM({col}), {tam}) END")


def norm_txt(col):
    """Normaliza texto para JOIN: maiusculo sem acento."""
    return (f"UPPER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE("
            f"TRIM({col}), 'Ç','C'),'Ã','A'),'É','E'),'Ê','E'),'Á','A'))")


# =====================================================================
# INFRAESTRUTURA
# =====================================================================

def log(msg=""):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def conectar():
    try:
        cnx = pymysql.connect(
            host=DB["host"], port=DB["port"], user=DB["user"],
            password=DB["password"], database=DB["database"],
            charset=DB["charset"], autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
        )
        # sql_mode permissivo: evita o erro 1411 em conversao de data
        with cnx.cursor() as cur:
            cur.execute("SET SESSION sql_mode = ''")
        cnx.commit()
        log(f"Conectado -> {DB['host']}/{DB['database']}")
        return cnx
    except Exception as e:
        sys.exit(f"ERRO de conexao: {e}\nVerifique se o MySQL do Laragon esta ativo.")


def escalar(cnx, sql, params=None):
    with cnx.cursor() as cur:
        cur.execute(sql, params or ())
        r = cur.fetchone()
        return list(r.values())[0] if r else None


def meses_disponiveis(cnx, tabela):
    with cnx.cursor() as cur:
        cur.execute(f"""
            SELECT DISTINCT _MES_REFERENCIA AS mes
            FROM {tabela}
            WHERE _MES_REFERENCIA IS NOT NULL
            ORDER BY _MES_REFERENCIA
        """)
        return [r["mes"] for r in cur.fetchall()]


def auditar(cnx, dominio, mes, lidos, inseridos, t0, status, msg=None):
    with cnx.cursor() as cur:
        cur.execute("""
            INSERT INTO tb_auditoria_carga
                (DT_INICIO, DT_FIM, DOMINIO, ARQUIVO, MES_REFERENCIA,
                 REGISTROS_LIDOS, REGISTROS_INSERIDOS, REGISTROS_REJEITADOS,
                 TEMPO_PROCESSAMENTO_SEG, STATUS, MENSAGEM)
            VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (datetime.fromtimestamp(t0), dominio, f"FATO_{dominio}", mes,
              lidos, inseridos, max(0, lidos - inseridos),
              int(time.time() - t0), status, msg))


def registrar_teste(cnx, nome, esperado, obtido, ok, obs=None):
    with cnx.cursor() as cur:
        cur.execute("""
            INSERT INTO tb_teste_aceite
                (NOME_TESTE, VALOR_ESPERADO, VALOR_OBTIDO, RESULTADO, OBSERVACAO)
            VALUES (%s, %s, %s, %s, %s)
        """, (nome, str(esperado), str(obtido), "PASS" if ok else "FAIL", obs))


# =====================================================================
# FATO 1 - QUEBRA
# =====================================================================

def carregar_quebra(cnx, mes, dry_run=False):
    t0 = time.time()
    log(f"  [{mes}] ft_quebra_historico")

    origem = escalar(cnx,
        "SELECT COUNT(*) FROM stg_quebra WHERE _MES_REFERENCIA = %s", (mes,))
    log(f"     origem ............. {origem:,} linhas")

    if origem == 0:
        log("     sem dados - ignorado")
        return 0

    if dry_run:
        log("     [DRY-RUN] nada gravado")
        return origem

    sql = f"""
    INSERT INTO ft_quebra_historico (
        HASH_REGISTRO, ANO_REFERENCIA, MES_REFERENCIA, DATA_EVENTO,
        DH_GERACAO_ARQUIVO, NR_ORDEM_SERVICO, NR_SOLICITACAO, ID_TIPO_OS,
        TIPO_OS, CD_IBGE, CD_OPERADORA, MARCA, CD_LOGIN_AGENDADOR,
        DATA_INSTALACAO, STATUS_OS, DT_AGENDA, DT_AGENDA_MES,
        DT_AGENDA_QUINZENA, DT_AGENDA_DIA, DS_PERIODO_AGENDA, NR_CONTRATO,
        COD_NODE, NM_TIPO_PRODUTO, DT_ABERTURA_OS, CD_LOGIN_ABERTURA_OS,
        NM_GRUPO_OS, NM_CANAL_VENDA, NM_CANAL_VENDA_GRUPO,
        NM_CANAL_VENDA_SUBGRUPO, DATA_BAIXA_OS, DH_REAGENDA,
        NM_MOTIVO_REAGENDA, CD_LOGIN_REAGENDA, NM_TIPO_TRATAMENTO,
        NM_NOVO_DOMICILIO, NM_LINHA_NEGOCIO, NM_QUEBRA_RESPONSAVEL,
        NM_QUEBRA_CENARIO, NM_STATUS_TEC1, NM_CARACTERISTICA_PRODUTO,
        CD_CODIGO_BAIXA, CD_CODIGO_CANCELAMENTO, TIPO_AREA, NM_CIDADE,
        NM_GRUPO, NM_REGIONAL, NM_CLUSTER, USR_ATEND, USR_BAIXA,
        USR_ATEND_PF, USR_BAIXA_PF, NM_REGIONAL_DTH, NM_SEGMENTO_MUNICIPIO,
        LINHA_NEGOCIO_DOM,
        NM_MUNICIPIO, NM_MUNICIPIO_NORM, UF,
        CP_UF, CP_DSC_SUBCLUSTER, CP_DSC_REGIONAL_CMV, CP_DSC_GERENTE,
        CP_COD_CIDADE_NETSMS, CP_COD_BASE, CP_DSC_TIPO_SEGMENTO,
        CP_DSC_LINHA_NEGOCIO, CP_FLAG_ALTO_VALOR, CP_FLAG_MDU,
        CP_FLAG_CONVENIENCIA, CP_FLAG_IMEDIATA, CP_DSC_PRODUTO,
        CP_COD_PONTO, CP_DAT_NOTA, CP_DAT_HOR_BAIXA,
        CP_DAT_INICIO_EXECUCAO, CP_DAT_TERMINO_EXECUCAO,
        CP_COD_EMPRESA_EXECUCAO, CP_DSC_EMPRESA_EXECUCAO,
        CP_NUM_CNPJ_EMPRESA_EXECUCAO, CP_DSC_EQUIPE_TECNICA,
        CP_DSC_AREA_DESPACHO, CP_COD_EMPRESA_DESPACHO,
        CP_DSC_EMPRESA_DESPACHO, CP_NUM_CNPJ_EMPRESA_DESPACHO,
        CP_COD_IMOVEL, CP_NUM_WORKORDER_WORKFORCE, CP_COD_TECNICO_WFM,
        CP_DSC_AREA_WORKFORCE, CP_DSC_BASE_WORKFORCE,
        CP_DSC_CANAL_USUARIO_AGENDA, CP_DSC_EMPRESA_USUARIO_AGENDA,
        CP_DSC_PERFIL_USUARIO_AGENDA, CP_AREA_RESPONSAVEL_ORDEM_SERVICO,
        CP_COD_USER_ABERTURA_SOLICITACAO, CP_DSC_USR_ATEND_PF,
        CP_DSC_PF_BAIXA, CP_DSC_PARCEIRO_BAIXA,
        CP_COD_MOTIVO_REAGENDAMENTO_OS, CP_DSC_OBSERVACAO_ORDEM_SERVICO,
        CP_CEP_CABEADO,
        TOA_PARCEIRA, TOA_RECURSO, TOA_LOGIN_TECNICO, TOA_STATUS_ATIVIDADE,
        TOA_AREA_TRABALHO, TOA_BAIRRO, TOA_CATEGORIA_CAPACIDADE,
        TOA_RECURSO_PAI, TOA_DATA, TOA_ATRIBUTO,
        NIVEL_MATCH_COMPLEMENTO, NIVEL_MATCH_TOA,
        ARQUIVO_ORIGEM_QUEBRA, DT_CARGA
    )
    SELECT
        SHA2(CONCAT_WS('|',
            q.NR_ORDEM_SERVICO, q.NR_CONTRATO, q.CD_OPERADORA,
            {data_flex('q.DT_AGENDA')},
            IFNULL(q.STATUS_OS,''), IFNULL(q.NM_TIPO_TRATAMENTO,''),
            IFNULL(q.DH_REAGENDA,''), IFNULL(q.CD_CODIGO_BAIXA,''),
            q._LINHA_ARQUIVO
        ), 256),
        CAST(LEFT(q._MES_REFERENCIA, 4) AS SIGNED),
        q._MES_REFERENCIA,
        {data_flex('q.DT_AGENDA')},

        {dt_flex('q.DH_GERACAO_ARQUIVO')},
        {inteiro('q.NR_ORDEM_SERVICO')},
        {inteiro('q.NR_SOLICITACAO')},
        {inteiro('q.ID_TIPO_OS')},
        {texto('q.TIPO_OS', 120)},
        {inteiro('q.CD_IBGE')},
        {inteiro('q.CD_OPERADORA')},
        {texto('q.MARCA', 60)},
        {texto('q.CD_LOGIN_AGENDADOR', 80)},
        {data_flex('q.DATA_INSTALACAO')},
        {texto('q.STATUS_OS', 60)},
        {data_flex('q.DT_AGENDA')},
        {inteiro('q.DT_AGENDA_MES')},
        {inteiro('q.DT_AGENDA_QUINZENA')},
        {inteiro('q.DT_AGENDA_DIA')},
        {texto('q.DS_PERIODO_AGENDA', 40)},
        {inteiro('q.NR_CONTRATO')},
        {texto('q.COD_NODE', 40)},
        {texto('q.NM_TIPO_PRODUTO', 60)},
        {dt_flex('q.DT_ABERTURA_OS')},
        {texto('q.CD_LOGIN_ABERTURA_OS', 80)},
        {texto('q.NM_GRUPO_OS', 60)},
        {texto('q.NM_CANAL_VENDA', 120)},
        {texto('q.NM_CANAL_VENDA_GRUPO', 120)},
        {texto('q.NM_CANAL_VENDA_SUBGRUPO', 120)},
        {dt_flex('q.DATA_BAIXA_OS')},
        {dt_flex('q.DH_REAGENDA')},
        {texto('q.NM_MOTIVO_REAGENDA', 255)},
        {texto('q.CD_LOGIN_REAGENDA', 80)},
        {texto('q.NM_TIPO_TRATAMENTO', 60)},
        {texto('q.NM_NOVO_DOMICILIO', 20)},
        {texto('q.NM_LINHA_NEGOCIO', 60)},
        {texto('q.NM_QUEBRA_RESPONSAVEL', 80)},
        {texto('q.NM_QUEBRA_CENARIO', 80)},
        {texto('q.NM_STATUS_TEC1', 80)},
        {texto('q.NM_CARACTERISTICA_PRODUTO', 80)},
        {texto('q.CD_CODIGO_BAIXA', 20)},
        {texto('q.CD_CODIGO_CANCELAMENTO', 20)},
        {texto('q.TIPO_AREA', 40)},
        {texto('q.NM_CIDADE', 100)},
        {texto('q.NM_GRUPO', 60)},
        {texto('q.NM_REGIONAL', 60)},
        {texto('q.NM_CLUSTER', 60)},
        {texto('q.USR_ATEND', 80)},
        {texto('q.USR_BAIXA', 80)},
        {texto('q.USR_ATEND_PF', 120)},
        {texto('q.USR_BAIXA_PF', 120)},
        {texto('q.NM_REGIONAL_DTH', 60)},
        {texto('q.NM_SEGMENTO_MUNICIPIO', 80)},
        {texto('q.LINHA_NEGOCIO_DOM', 60)},

        d.NM_MUNICIPIO, d.NM_MUNICIPIO_NORM, d.UF,

        c.CP_UF, c.CP_DSC_SUBCLUSTER, c.CP_DSC_REGIONAL_CMV, c.CP_DSC_GERENTE,
        c.CP_COD_CIDADE_NETSMS, c.CP_COD_BASE, c.CP_DSC_TIPO_SEGMENTO,
        c.CP_DSC_LINHA_NEGOCIO, c.CP_FLAG_ALTO_VALOR, c.CP_FLAG_MDU,
        c.CP_FLAG_CONVENIENCIA, c.CP_FLAG_IMEDIATA, c.CP_DSC_PRODUTO,
        c.CP_COD_PONTO, c.CP_DAT_NOTA,
        {dt_flex('c.CP_DAT_HOR_BAIXA')},
        {dt_flex('c.CP_DAT_INICIO_EXECUCAO')},
        {dt_flex('c.CP_DAT_TERMINO_EXECUCAO')},
        c.CP_COD_EMPRESA_EXECUCAO, c.CP_DSC_EMPRESA_EXECUCAO,
        c.CP_NUM_CNPJ_EMPRESA_EXECUCAO, c.CP_DSC_EQUIPE_TECNICA,
        c.CP_DSC_AREA_DESPACHO, c.CP_COD_EMPRESA_DESPACHO,
        c.CP_DSC_EMPRESA_DESPACHO, c.CP_NUM_CNPJ_EMPRESA_DESPACHO,
        c.CP_COD_IMOVEL, c.CP_NUM_WORKORDER_WORKFORCE, c.CP_COD_TECNICO_WFM,
        c.CP_DSC_AREA_WORKFORCE, c.CP_DSC_BASE_WORKFORCE,
        c.CP_DSC_CANAL_USUARIO_AGENDA, c.CP_DSC_EMPRESA_USUARIO_AGENDA,
        c.CP_DSC_PERFIL_USUARIO_AGENDA, c.CP_AREA_RESPONSAVEL_ORDEM_SERVICO,
        c.CP_COD_USER_ABERTURA_SOLICITACAO, c.CP_DSC_USR_ATEND_PF,
        c.CP_DSC_PF_BAIXA, c.CP_DSC_PARCEIRO_BAIXA,
        c.CP_COD_MOTIVO_REAGENDAMENTO_OS, c.CP_DSC_OBSERVACAO_ORDEM_SERVICO,
        c.CP_CEP_CABEADO,

        t.PARCEIRA, t.RECURSO, t.LOGIN_TECNICO, t.STATUS_ATIVIDADE,
        t.AREA_TRABALHO, t.BAIRRO, t.CATEGORIA_CAPACIDADE,
        t.RECURSO_PAI, t.DATA_N, t.ATRIBUTO,

        CASE WHEN c.CONTRATO_N IS NULL THEN 'N0_SEM_MATCH'
             ELSE 'N1_COMPLETO' END,
        CASE WHEN t.CONTRATO_N IS NULL THEN 'N0_SEM_MATCH'
             ELSE 'N1_COMPLETO' END,
        q._ARQUIVO_ORIGEM,
        NOW()

    FROM stg_quebra q

    LEFT JOIN dim_operadora_municipio d
           ON {inteiro('q.CD_OPERADORA')} = d.CD_OPERADORA

    LEFT JOIN dd_compl c
           ON  {inteiro('q.NR_CONTRATO')}      = c.CONTRATO_N
           AND {inteiro('q.NR_ORDEM_SERVICO')} = c.OS_N
           AND {inteiro('q.CD_OPERADORA')}     = c.OPERADORA_N
           AND {data_flex('q.DT_AGENDA')}      = c.DT_AGENDA_N

    LEFT JOIN dd_toa_evento t
           ON  {inteiro('q.NR_CONTRATO')}      = t.CONTRATO_N
           AND {inteiro('q.NR_ORDEM_SERVICO')} = t.OS_N
           AND {data_flex('q.DT_AGENDA')}      = t.DATA_N

    WHERE q._MES_REFERENCIA = %s
    """

    with cnx.cursor() as cur:
        cur.execute("DELETE FROM ft_quebra_historico WHERE MES_REFERENCIA = %s", (mes,))
        removidos = cur.rowcount
        if removidos:
            log(f"     removidos anteriores {removidos:,}")

        cur.execute(sql, (mes,))
        inseridos = cur.rowcount

    log(f"     inseridos .......... {inseridos:,}")

    # --------------------------------------------------------------
    # VALIDACAO ANTI-MULTIPLICACAO
    # --------------------------------------------------------------
    if inseridos != origem:
        cnx.rollback()
        log(f"     ERRO: origem={origem:,} destino={inseridos:,}")
        log("     ROLLBACK - enriquecimento multiplicou ou perdeu linhas")
        registrar_teste(cnx, f"quebra_grao_{mes}", origem, inseridos, False,
                        "enriquecimento alterou o numero de linhas")
        cnx.commit()
        return 0

    # --------------------------------------------------------------
    # QUALIDADE DO MATCH
    # --------------------------------------------------------------
    with cnx.cursor() as cur:
        cur.execute("""
            SELECT
                ROUND(SUM(NIVEL_MATCH_COMPLEMENTO <> 'N0_SEM_MATCH')
                      / COUNT(*) * 100, 1) AS pct_compl,
                ROUND(SUM(NIVEL_MATCH_TOA <> 'N0_SEM_MATCH')
                      / COUNT(*) * 100, 1) AS pct_toa,
                ROUND(SUM(NM_MUNICIPIO IS NOT NULL)
                      / COUNT(*) * 100, 1) AS pct_mun,
                SUM(NM_TIPO_TRATAMENTO = 'COM QUEBRA DE AGENDA') AS com_quebra,
                COUNT(*) AS total
            FROM ft_quebra_historico
            WHERE MES_REFERENCIA = %s
        """, (mes,))
        m = cur.fetchone()

    pct_quebra = float(m["com_quebra"] or 0) / float(m["total"]) * 100
    log(f"     match complemento .. {m['pct_compl']}%")
    log(f"     match TOA .......... {m['pct_toa']}%")
    log(f"     match municipio .... {m['pct_mun']}%")
    log(f"     % QUEBRA ........... {pct_quebra:.2f}%")

    if mes == "2026-08":
        ok = abs(pct_quebra - 63.14) < 0.05 and int(m["total"]) == 20484
        registrar_teste(cnx, "aceite_quebra_2026_08", "63,14% / 20.484",
                        f"{pct_quebra:.2f}% / {m['total']}", ok)
        log(f"     TESTE DE ACEITE .... {'PASS' if ok else 'FAIL'}")

    auditar(cnx, "QUEBRA", mes, origem, inseridos, t0, "OK")
    cnx.commit()
    log(f"     concluido em {time.time() - t0:.1f}s")
    return inseridos


# =====================================================================
# FATO 2 - SAFRA
# =====================================================================

def carregar_safra(cnx, mes, dry_run=False):
    t0 = time.time()
    log(f"  [{mes}] ft_safra_historico")

    origem = escalar(cnx,
        "SELECT COUNT(*) FROM stg_safra WHERE _MES_REFERENCIA = %s", (mes,))
    log(f"     origem ............. {origem:,} linhas")

    if origem == 0:
        log("     sem dados - ignorado")
        return 0

    if dry_run:
        log("     [DRY-RUN] nada gravado")
        return origem

    sql = f"""
    INSERT INTO ft_safra_historico (
        HASH_REGISTRO, ANO_REFERENCIA, MES_REFERENCIA,
        DT_BASE, DATA_PEND, DT_ACAO, NM_CIDADE, NM_CLUSTER, NM_SUBCLUSTER,
        NM_REGIONAL, DS_MODELO_EQPTO, DS_SUBTIPO_EQPTO, DS_TIPO_DESCONEXAO,
        DS_TIPO_DESCONEXAO_NORM, CD_NET, CD_OS, NR_AGING_OS,
        NR_DIAS_EM_ABERTO, DS_STATUS_CONTR, MES_ANO_PEND, MES_ANO_ACAO,
        GRUPO, MOVIMENTACAO, PENDENCIA, SUB_TIPO_EQUIP,
        NM_SEGMENTO_MUNICIPIO, EPO, DDD, NR_SERIAL, NR_MAC,
        POSSUI_TEC_DEDICADO, SAFRA, ANO_MES,
        CD_OPERADORA, NM_MUNICIPIO, NM_MUNICIPIO_NORM, UF,
        QB_NR_ORDEM_SERVICO, QB_DT_AGENDA, QB_STATUS_OS, QB_TIPO_OS,
        QB_NM_TIPO_TRATAMENTO, QB_NM_QUEBRA_RESPONSAVEL,
        QB_NM_QUEBRA_CENARIO, QB_NM_MOTIVO_REAGENDA, QB_CD_CODIGO_BAIXA,
        QTD_OS_CONTRATO, QTD_QUEBRAS_CONTRATO, QTD_REAGENDAMENTOS_CONTRATO,
        DT_PRIMEIRA_AGENDA, DT_ULTIMA_AGENDA,
        TOA_PARCEIRA, TOA_RECURSO, TOA_LOGIN_TECNICO, TOA_STATUS_ATIVIDADE,
        TOA_AREA_TRABALHO, TOA_BAIRRO, TOA_DATA,
        BK_POSSUI_BACKLOG, BK_SITUACAO_AGENDA, BK_DT_AGENDA, BK_STATUS_OS,
        BK_MOTIVO_REAG, BK_STATUS_CONTRATO, BK_SEGMENTO_CONTRATO,
        BK_TIPO_ASSINANTE, BK_NM_TECNOLOGIA, BK_QTD_DIAS_EM_BACKLOG,
        BK_QTD_AGENDAMENTOS, BK_QTD_REAGENDAMENTOS, BK_PRIMEIRA_APARICAO,
        BK_ULTIMA_APARICAO, BK_QTDE_EQUIPAMENTOS_TOTAL,
        META_VIGENTE,
        NIVEL_MATCH_QUEBRA, NIVEL_MATCH_TOA, NIVEL_MATCH_BACKLOG,
        ARQUIVO_ORIGEM_SAFRA, DT_CARGA
    )
    SELECT
        SHA2(CONCAT_WS('|',
            s.CD_NET, IFNULL(s.CD_OS,''), IFNULL(s.NR_SERIAL,''),
            s.DT_BASE, s.SAFRA, s.DS_TIPO_DESCONEXAO,
            s._MES_REFERENCIA, s._LINHA_ARQUIVO
        ), 256),
        CAST(LEFT(s._MES_REFERENCIA, 4) AS SIGNED),
        s._MES_REFERENCIA,

        {data_flex('s.DT_BASE')},
        {data_flex('s.DATA_PEND')},
        {data_flex('s.DT_ACAO')},
        {texto('s.NM_CIDADE', 100)},
        {texto('s.NM_CLUSTER', 60)},
        {texto('s.NM_SUBCLUSTER', 80)},
        {texto('s.NM_REGIONAL', 60)},
        {texto('s.DS_MODELO_EQPTO', 150)},
        {texto('s.DS_SUBTIPO_EQPTO', 80)},
        {texto('s.DS_TIPO_DESCONEXAO', 60)},
        {norm_txt('s.DS_TIPO_DESCONEXAO')},
        {inteiro('s.CD_NET')},
        {inteiro('s.CD_OS')},
        {inteiro('s.NR_AGING_OS')},
        {inteiro('s.NR_DIAS_EM_ABERTO')},
        {texto('s.DS_STATUS_CONTR', 120)},
        {texto('s.MES_ANO_PEND', 20)},
        {texto('s.MES_ANO_ACAO', 20)},
        {texto('s.GRUPO', 60)},
        {inteiro('s.MOVIMENTACAO')},
        {inteiro('s.PENDENCIA')},
        {texto('s.SUB_TIPO_EQUIP', 80)},
        {texto('s.NM_SEGMENTO_MUNICIPIO', 80)},
        {texto('s.EPO', 120)},
        {texto('s.DDD', 10)},
        {texto('s.NR_SERIAL', 60)},
        {texto('s.NR_MAC', 60)},
        {texto('s.POSSUI_TEC_DEDICADO', 10)},
        {texto('s.SAFRA', 10)},
        {texto('s.ANO_MES', 10)},

        d.CD_OPERADORA, d.NM_MUNICIPIO, d.NM_MUNICIPIO_NORM, d.UF,

        qc.QB_NR_ORDEM_SERVICO, qc.QB_DT_AGENDA, qc.QB_STATUS_OS,
        qc.QB_TIPO_OS, qc.QB_NM_TIPO_TRATAMENTO, qc.QB_NM_QUEBRA_RESPONSAVEL,
        qc.QB_NM_QUEBRA_CENARIO, qc.QB_NM_MOTIVO_REAGENDA,
        qc.QB_CD_CODIGO_BAIXA,
        IFNULL(qc.QTD_OS_CONTRATO, 0),
        IFNULL(qc.QTD_QUEBRAS_CONTRATO, 0),
        IFNULL(qc.QTD_REAGENDAMENTOS_CONTRATO, 0),
        qc.DT_PRIMEIRA_AGENDA, qc.DT_ULTIMA_AGENDA,

        tc.PARCEIRA, tc.RECURSO, tc.LOGIN_TECNICO, tc.STATUS_ATIVIDADE,
        tc.AREA_TRABALHO, tc.BAIRRO, tc.DATA_N,

        CASE WHEN bc.CONTRATO_N IS NULL THEN 0 ELSE 1 END,
        bc.BK_SITUACAO_AGENDA, bc.BK_DT_AGENDA, bc.BK_STATUS_OS,
        bc.BK_MOTIVO_REAG, bc.BK_STATUS_CONTRATO, bc.BK_SEGMENTO_CONTRATO,
        bc.BK_TIPO_ASSINANTE, bc.BK_NM_TECNOLOGIA,
        IFNULL(bc.BK_QTD_DIAS_EM_BACKLOG, 0),
        IFNULL(bc.BK_QTD_AGENDAMENTOS, 0),
        IFNULL(bc.BK_QTD_REAGENDAMENTOS, 0),
        bc.BK_PRIMEIRA_APARICAO, bc.BK_ULTIMA_APARICAO,
        bc.BK_QTDE_EQUIPAMENTOS_TOTAL,

        mt.META,

        CASE WHEN qc.CONTRATO_N IS NULL THEN 'S0_SEM_MATCH'
             ELSE 'S2_CONTRATO_OPER' END,
        CASE WHEN tc.CONTRATO_N IS NULL THEN 'S0_SEM_MATCH'
             ELSE 'S2_CONTRATO_OPER' END,
        CASE WHEN bc.CONTRATO_N IS NULL THEN 'S0_SEM_MATCH'
             ELSE 'S2_CONTRATO_OPER' END,
        s._ARQUIVO_ORIGEM,
        NOW()

    FROM stg_safra s

    LEFT JOIN dim_operadora_municipio d
           ON UPPER(TRIM(s.NM_CIDADE)) = d.NM_MUNICIPIO_NORM

    LEFT JOIN dd_quebra_contrato qc
           ON  {inteiro('s.CD_NET')} = qc.CONTRATO_N
           AND d.CD_OPERADORA        = qc.OPERADORA_N

    LEFT JOIN dd_toa_contrato tc
           ON  {inteiro('s.CD_NET')} = tc.CONTRATO_N
           AND d.CD_OPERADORA        = tc.OPERADORA_N

    LEFT JOIN dd_backlog_contrato bc
           ON  {inteiro('s.CD_NET')} = bc.CONTRATO_N
           AND d.CD_OPERADORA        = bc.OPERADORA_N

    LEFT JOIN dim_metas mt
           ON  mt.ANO   = CAST(LEFT(s._MES_REFERENCIA, 4) AS SIGNED)
           AND mt.MES   = CAST(RIGHT(s._MES_REFERENCIA, 2) AS SIGNED)
           AND mt.SAFRA = TRIM(s.SAFRA)
           AND mt.TIPO_DESCONEXAO_NORM = {norm_txt('s.DS_TIPO_DESCONEXAO')}

    WHERE s._MES_REFERENCIA = %s
    """

    with cnx.cursor() as cur:
        cur.execute("DELETE FROM ft_safra_historico WHERE MES_REFERENCIA = %s", (mes,))
        removidos = cur.rowcount
        if removidos:
            log(f"     removidos anteriores {removidos:,}")

        cur.execute(sql, (mes,))
        inseridos = cur.rowcount

    log(f"     inseridos .......... {inseridos:,}")

    if inseridos != origem:
        cnx.rollback()
        log(f"     ERRO: origem={origem:,} destino={inseridos:,}")
        log("     ROLLBACK - enriquecimento alterou o numero de linhas")
        registrar_teste(cnx, f"safra_grao_{mes}", origem, inseridos, False,
                        "enriquecimento alterou o numero de linhas")
        cnx.commit()
        return 0

    with cnx.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(PENDENCIA = 0) AS recuperados,
                SUM(PENDENCIA = 1) AS pendentes,
                ROUND(SUM(NIVEL_MATCH_QUEBRA  <> 'S0_SEM_MATCH')/COUNT(*)*100,1) AS pct_qb,
                ROUND(SUM(NIVEL_MATCH_TOA     <> 'S0_SEM_MATCH')/COUNT(*)*100,1) AS pct_toa,
                ROUND(SUM(NIVEL_MATCH_BACKLOG <> 'S0_SEM_MATCH')/COUNT(*)*100,1) AS pct_bk,
                ROUND(SUM(NM_MUNICIPIO IS NOT NULL)/COUNT(*)*100,1) AS pct_mun,
                ROUND(SUM(META_VIGENTE IS NOT NULL)/COUNT(*)*100,1) AS pct_meta
            FROM ft_safra_historico
            WHERE MES_REFERENCIA = %s
        """, (mes,))
        m = cur.fetchone()

    total = float(m["total"])
    rec = float(m["recuperados"] or 0)
    log(f"     match quebra ....... {m['pct_qb']}%")
    log(f"     match TOA .......... {m['pct_toa']}%")
    log(f"     match backlog ...... {m['pct_bk']}%")
    log(f"     match municipio .... {m['pct_mun']}%")
    log(f"     com meta ........... {m['pct_meta']}%")
    log(f"     recuperacao ........ {rec/total*100:.2f}%")

    soma = int(m["recuperados"] or 0) + int(m["pendentes"] or 0)
    ok_soma = soma == int(m["total"])
    registrar_teste(cnx, f"safra_soma_{mes}", m["total"], soma, ok_soma)
    if not ok_soma:
        log("     ATENCAO: recuperados + pendentes nao fecha com o total")

    auditar(cnx, "SAFRA", mes, origem, inseridos, t0, "OK")
    cnx.commit()
    log(f"     concluido em {time.time() - t0:.1f}s")
    return inseridos


# =====================================================================
# FATO 3 - BACKLOG LOG
# =====================================================================

def carregar_backlog(cnx, dry_run=False):
    t0 = time.time()
    log("  ft_backlog_log")

    existe = escalar(cnx, """
        SELECT COUNT(*) FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'tmp_backlog_norm'
    """, (DB["database"],))

    if not existe:
        log("     tmp_backlog_norm nao existe - execute o script 03g antes")
        return 0

    origem = escalar(cnx, "SELECT COUNT(*) FROM tmp_backlog_norm")
    log(f"     origem ............. {origem:,} linhas")

    if dry_run:
        log("     [DRY-RUN] nada gravado")
        return origem

    sql = """
    INSERT IGNORE INTO ft_backlog_log (
        HASH_REGISTRO, DT_RELATORIO, MES_REFERENCIA,
        CD_OPERADORA, CD_CONTRATO, CD_OS,
        NM_CIDADE, NM_REGIONAL, NM_CLUSTER, NM_SUBCLUSTER,
        NM_MUNICIPIO, NM_MUNICIPIO_NORM, UF,
        STATUS_OS, SITUACAO_AGENDA, DATA_AGENDAMENTO,
        MOTIVO_REAG, FX_TEMPO_BASE, DATA_ABERTURA_OS,
        STATUS_CONTRATO, SEGMENTO_CONTRATO,
        TIPO_ASSINANTE, NM_TECNOLOGIA,
        QTDE_EQUIP_TOTAL, ARQUIVO_ORIGEM, DT_CARGA
    )
    SELECT
        SHA2(CONCAT_WS('|', n.CONTRATO_N, IFNULL(n.OPERADORA_N,''),
             IFNULL(n.OS_N,''), n.DT_RELATORIO_N, n.ID_UNICO), 256),
        n.DT_RELATORIO_N,
        DATE_FORMAT(n.DT_RELATORIO_N, '%%Y-%%m'),
        n.OPERADORA_N, n.CONTRATO_N, n.OS_N,
        n.NM_CIDADE, n.NM_REGIONAL, n.NM_CLUSTER, n.NM_SUBCLUSTER,
        d.NM_MUNICIPIO, d.NM_MUNICIPIO_NORM, d.UF,
        n.STATUS_OS, n.SITUACAO_AGENDA, n.DT_AGENDA_N,
        n.MOTIVO_REAG, n.AGING_CLASSIFICACAO, n.DT_ABERTURA_OS_N,
        n.STATUS_CONTRATO, n.SEGMENTO_CONTRATO,
        n.TIPO_ASSINANTE, n.NM_TECNOLOGIA,
        n.QTDE_EQUIP_TOTAL, 'BACKLOG_OS.csv', NOW()
    FROM tmp_backlog_norm n
    LEFT JOIN dim_operadora_municipio d
           ON n.OPERADORA_N = d.CD_OPERADORA
    """

    with cnx.cursor() as cur:
        cur.execute(sql)
        inseridos = cur.rowcount

    log(f"     inseridos .......... {inseridos:,}")
    if inseridos < origem:
        log(f"     ({origem - inseridos:,} ja existiam - INSERT IGNORE)")

    total = escalar(cnx, "SELECT COUNT(*) FROM ft_backlog_log")
    datas = escalar(cnx, "SELECT COUNT(DISTINCT DT_RELATORIO) FROM ft_backlog_log")
    log(f"     total no log ....... {total:,}")
    log(f"     datas distintas .... {datas}")

    with cnx.cursor() as cur:
        cur.execute("TRUNCATE ft_backlog_atual")
        cur.execute("""
            INSERT INTO ft_backlog_atual
            SELECT l.*, l.DT_RELATORIO, 0, 0
            FROM ft_backlog_log l
            INNER JOIN (
                SELECT CD_CONTRATO, CD_OPERADORA, CD_OS,
                       MAX(DT_RELATORIO) AS dt
                FROM ft_backlog_log
                GROUP BY CD_CONTRATO, CD_OPERADORA, CD_OS
            ) u ON  l.CD_CONTRATO  = u.CD_CONTRATO
                AND l.CD_OPERADORA <=> u.CD_OPERADORA
                AND l.CD_OS        <=> u.CD_OS
                AND l.DT_RELATORIO = u.dt
        """)
        atual = cur.rowcount

    log(f"     posicao atual ...... {atual:,}")

    auditar(cnx, "BACKLOG", None, origem, inseridos, t0, "OK")
    cnx.commit()
    log(f"     concluido em {time.time() - t0:.1f}s")
    return inseridos


# =====================================================================
# METAS
# =====================================================================

def carregar_metas(cnx, dry_run=False):
    log("  dim_metas")

    origem = escalar(cnx, "SELECT COUNT(*) FROM stg_metas")
    log(f"     origem ............. {origem} linhas")

    if origem == 0 or dry_run:
        return origem

    with cnx.cursor() as cur:
        cur.execute("TRUNCATE dim_metas")
        cur.execute(f"""
            INSERT INTO dim_metas
                (MES, ANO, SAFRA, TIPO_DESCONEXAO, TIPO_DESCONEXAO_NORM, META)
            SELECT
                CAST(TRIM(MES) AS SIGNED),
                CAST(TRIM(ANO) AS SIGNED),
                TRIM(SAFRA),
                TRIM(TIPO_DESCONEXAO),
                {norm_txt('TIPO_DESCONEXAO')},
                CAST(REPLACE(TRIM(META), ',', '.') AS DECIMAL(6,4))
            FROM stg_metas
            WHERE TRIM(MES) REGEXP '^[0-9]+$'
        """)
        inseridos = cur.rowcount

    log(f"     inseridos .......... {inseridos}")
    cnx.commit()
    return inseridos


# =====================================================================
# MAIN
# =====================================================================

def main():
    ap = argparse.ArgumentParser(description="Carga dos fatos")
    ap.add_argument("--fato", choices=["quebra", "safra", "backlog", "metas"],
                    help="carrega apenas um fato")
    ap.add_argument("--mes", help="processa apenas um mes (ex: 2026-08)")
    ap.add_argument("--dry-run", action="store_true", help="simula sem gravar")
    args = ap.parse_args()

    log("=" * 70)
    log("  CARGA DOS FATOS - DATA MART DESCONEXAO RNO")
    log("=" * 70)
    if args.dry_run:
        log("  MODO DRY-RUN - nada sera gravado")
    log("")

    cnx = conectar()
    t_inicio = time.time()
    resumo = {}

    if args.fato in (None, "metas"):
        log("")
        log("[METAS]")
        resumo["metas"] = carregar_metas(cnx, args.dry_run)

    if args.fato in (None, "quebra"):
        log("")
        log("[QUEBRA]")
        meses = [args.mes] if args.mes else meses_disponiveis(cnx, "stg_quebra")
        total = 0
        for m in meses:
            try:
                total += carregar_quebra(cnx, m, args.dry_run)
            except Exception as e:
                cnx.rollback()
                log(f"     FALHA em {m}: {e}")
                log("     mes ignorado - os demais continuam")
        resumo["quebra"] = total

    if args.fato in (None, "safra"):
        log("")
        log("[SAFRA]")
        meses = [args.mes] if args.mes else meses_disponiveis(cnx, "stg_safra")
        total = 0
        for m in meses:
            try:
                total += carregar_safra(cnx, m, args.dry_run)
            except Exception as e:
                cnx.rollback()
                log(f"     FALHA em {m}: {e}")
                log("     mes ignorado - os demais continuam")
        resumo["safra"] = total

    if args.fato in (None, "backlog"):
        log("")
        log("[BACKLOG]")
        try:
            resumo["backlog"] = carregar_backlog(cnx, args.dry_run)
        except Exception as e:
            cnx.rollback()
            log(f"     FALHA no backlog: {e}")
            resumo["backlog"] = 0

    log("")
    log("=" * 70)
    log("  RESUMO")
    log("=" * 70)
    for k, v in resumo.items():
        log(f"  {k:<12} {v:>12,} linhas")
    log("-" * 70)
    log(f"  tempo total: {time.time() - t_inicio:.1f}s")

    with cnx.cursor() as cur:
        cur.execute("""
            SELECT NOME_TESTE, VALOR_ESPERADO, VALOR_OBTIDO, RESULTADO
            FROM tb_teste_aceite
            WHERE DT_EXECUCAO >= %s
            ORDER BY ID_TESTE
        """, (datetime.fromtimestamp(t_inicio),))
        testes = cur.fetchall()

    if testes:
        log("")
        log("  TESTES DE ACEITE")
        log("-" * 70)
        for t in testes:
            marca = "OK   " if t["RESULTADO"] == "PASS" else "FALHA"
            log(f"  [{marca}] {t['NOME_TESTE']:<26} "
                f"esperado={t['VALOR_ESPERADO']}  obtido={t['VALOR_OBTIDO']}")

    log("")
    log(f"  log: {LOG_FILE}")
    log("=" * 70)

    cnx.close()


if __name__ == "__main__":
    main()
