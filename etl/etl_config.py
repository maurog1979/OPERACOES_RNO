# -*- coding: utf-8 -*-
"""
=====================================================================
PORTAL OPERACOES RNO - DATA MART DESCONEXAO
etl_config.py - Configuracao central do ETL
=====================================================================
ARQUIVO COMPLETO - substitua o anterior inteiro.

Ajuste APENAS este arquivo se mudar caminho, senha ou banco.
Este arquivo NAO e executavel. Ele e importado pelo etl_02.
=====================================================================
"""

import os

# ---------------------------------------------------------------------
# CONEXAO MYSQL
# ---------------------------------------------------------------------
DB = {
    "host":     "127.0.0.1",
    "port":     3306,
    "user":     "root",
    "password": "",                  # Laragon padrao = vazio
    "database": "desconexao_rno",
    "charset":  "utf8mb4",
}

# ---------------------------------------------------------------------
# CAMINHO RAIZ DOS ANALITICOS
# ---------------------------------------------------------------------
RAIZ = r"C:\Users\n5996917\OneDrive - Claro SA\OPERAÇÕES\ADM\DESCONEXAO\ANALITICOS"

PASTAS = {
    "QUEBRA":       os.path.join(RAIZ, "QUEBRA", "ENTRADA"),
    "QUEBRA_COMPL": os.path.join(RAIZ, "QUEBRA_COMPLEMENTO", "ENTRADA"),
    "TOA":          os.path.join(RAIZ, "TOA", "ENTRADA"),
    "SAFRA":        os.path.join(RAIZ, "SAFRA", "ENTRADA"),
    "BACKLOG":      os.path.join(RAIZ, "BACKLOG_OS", "ENTRADA"),
    "METAS":        os.path.join(RAIZ, "METAS"),
}

# ---------------------------------------------------------------------
# PADRAO DE NOME DOS ARQUIVOS
# Mensais seguem NOME_MM-AAAA.csv
# Backlog e arquivo unico sobrescrito diariamente
# ---------------------------------------------------------------------
PADRAO = {
    "QUEBRA":       r"^QUEBRA_(\d{2})-(\d{4})\.csv$",
    "QUEBRA_COMPL": r"^QUEBRA_COMPL_(\d{2})-(\d{4})\.csv$",
    "TOA":          r"^TOA_(\d{2})-(\d{4})\.csv$",
    "SAFRA":        r"^SAFRA_(\d{2})-(\d{4})\.csv$",
    "BACKLOG":      r"^BACKLOG_OS\.csv$",
    "METAS":        r"^METAS\.xlsx$",
}

# ---------------------------------------------------------------------
# JANELA HISTORICA
# ---------------------------------------------------------------------
MES_INICIO_HISTORICO = "2026-01"

# ---------------------------------------------------------------------
# LEITURA DOS CSV
# ---------------------------------------------------------------------
CSV_SEP = ";"
CSV_ENCODINGS = ["utf-8-sig", "cp1252", "latin-1"]
CHUNK_SIZE = 50_000

# ---------------------------------------------------------------------
# MAPA DE COLUNAS
# cabecalho do CSV  ->  coluna da tabela stg_
# Necessario quando ha acento, ponto ou espaco no cabecalho.
# ---------------------------------------------------------------------
MAPA_COLUNAS = {

    "TOA": {
        "Recurso":                  "RECURSO",
        "Login do Técnico":         "LOGIN_TECNICO",
        "Login do Tecnico":         "LOGIN_TECNICO",
        "Data":                     "DATA",
        "Status da Atividade":      "STATUS_ATIVIDADE",
        "Cidade":                   "CIDADE",
        "CIDADE":                   "CIDADE",
        "UF":                       "UF",
        "CD_OPERADORA":             "OPERADORA",
        "Operadora":                "OPERADORA",
        "OPERADORA":                "OPERADORA",
        "Contrato":                 "CONTRATO",
        "Área de Trabalho":         "AREA_TRABALHO",
        "Area de Trabalho":         "AREA_TRABALHO",
        "Bairro":                   "BAIRRO",
        "Categorias da Capacidade": "CATEGORIA_CAPACIDADE",
        "Status do contrato":       "STATUS_CONTRATO",
        "Status do Contrato":       "STATUS_CONTRATO",
        "Recurso Pai":              "RECURSO_PAI",
        "PARCEIRA":                 "PARCEIRA",
        "Parceira":                 "PARCEIRA",
        "Atributo":                 "ATRIBUTO",
        "O.S":                      "OS",
        "O.S.":                     "OS",
        "Dia":                      "DIA",
        "Mês":                      "MES",
        "Mes":                      "MES",
        "Ano":                      "ANO",
        "CHAVE":                    "CHAVE",
    },

    "SAFRA": {
        "MÊS/ANO PEND.":     "MES_ANO_PEND",
        "MES/ANO PEND.":     "MES_ANO_PEND",
        "MÊS/ANO AÇÃO":      "MES_ANO_ACAO",
        "MES/ANO ACAO":      "MES_ANO_ACAO",
        "MOVIMENTAÇÃO":      "MOVIMENTACAO",
        "MOVIMENTACAO":      "MOVIMENTACAO",
        "PENDÊNCIA":         "PENDENCIA",
        "PENDENCIA":         "PENDENCIA",
        "Sub Tipo de Equip": "SUB_TIPO_EQUIP",
    },

    "METAS": {
        "MÊS":              "MES",
        "MES":              "MES",
        "ANO":              "ANO",
        "SAFRA":            "SAFRA",
        "TIPO_DESCONEXÃO":  "TIPO_DESCONEXAO",
        "TIPO_DESCONEXAO":  "TIPO_DESCONEXAO",
        "META":             "META",
    },

    "BACKLOG": {
        "BKL_TEMPO_ABERTURA_DIAS": "TEMPO_ABERTURA_DIAS",
        "BKL_FX_TEMPO":            "FX_TEMPO_BASE",
        "BKL_AGING":               "AGING",
    },

    "QUEBRA": {},

    "QUEBRA_COMPL": {},
}

# ---------------------------------------------------------------------
# LOG
# ---------------------------------------------------------------------
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_NIVEL = "INFO"      # INFO | DEBUG
