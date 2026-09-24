-- =====================================================================
-- PORTAL OPERACOES RNO — DATA MART DESCONEXAO
-- Script 01 — DDL COMPLETO (Staging + Dimensoes + Fatos + Auditoria)
-- Modelagem V2.1
-- MySQL 8.x
-- =====================================================================
-- EXECUCAO:
--   mysql -u root -p < 01_ddl_desconexao_rno.sql
-- =====================================================================

CREATE DATABASE IF NOT EXISTS desconexao_rno
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE desconexao_rno;

SET FOREIGN_KEY_CHECKS = 0;

-- =====================================================================
-- CAMADA 1 — STAGING
-- Espelho fiel dos CSV. Tudo VARCHAR/TEXT. Sem conversao nesta camada.
-- Recarregada a cada execucao (TRUNCATE + LOAD).
-- =====================================================================

-- ---------------------------------------------------------------------
-- STG_QUEBRA  (54 colunas)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS stg_quebra;
CREATE TABLE stg_quebra (
  DH_GERACAO_ARQUIVO          VARCHAR(30),
  NR_ORDEM_SERVICO            VARCHAR(30),
  NR_SOLICITACAO              VARCHAR(30),
  ID_TIPO_OS                  VARCHAR(20),
  TIPO_OS                     VARCHAR(120),
  CD_IBGE                     VARCHAR(20),
  CD_OPERADORA                VARCHAR(20),
  MARCA                       VARCHAR(60),
  CD_LOGIN_AGENDADOR          VARCHAR(80),
  DATA_INSTALACAO             VARCHAR(30),
  STATUS_OS                   VARCHAR(60),
  DT_AGENDA                   VARCHAR(30),
  DT_AGENDA_MES               VARCHAR(10),
  DT_AGENDA_QUINZENA          VARCHAR(10),
  DT_AGENDA_DIA               VARCHAR(10),
  DS_PERIODO_AGENDA           VARCHAR(40),
  NR_CONTRATO                 VARCHAR(30),
  COD_NODE                    VARCHAR(40),
  NM_TIPO_PRODUTO             VARCHAR(60),
  DT_ABERTURA_OS              VARCHAR(30),
  CD_LOGIN_ABERTURA_OS        VARCHAR(80),
  NM_GRUPO_OS                 VARCHAR(60),
  NM_CANAL_VENDA              VARCHAR(120),
  NM_CANAL_VENDA_GRUPO        VARCHAR(120),
  NM_CANAL_VENDA_SUBGRUPO     VARCHAR(120),
  CD_LOGIN_VENDEDOR           VARCHAR(80),
  DATA_BAIXA_OS               VARCHAR(30),
  DH_REAGENDA                 VARCHAR(30),
  NM_MOTIVO_REAGENDA          VARCHAR(255),
  CD_LOGIN_REAGENDA           VARCHAR(80),
  NM_TIPO_TRATAMENTO          VARCHAR(60),
  NM_TIPO_TRATAMENTO_CHIP     VARCHAR(60),
  NM_NOVO_DOMICILIO           VARCHAR(20),
  NM_LINHA_NEGOCIO            VARCHAR(60),
  NM_QUEBRA_RESPONSAVEL       VARCHAR(80),
  NM_QUEBRA_CENARIO           VARCHAR(80),
  NM_STATUS_TEC1              VARCHAR(80),
  NM_CARACTERISTICA_PRODUTO   VARCHAR(80),
  CD_CODIGO_BAIXA             VARCHAR(20),
  CD_CODIGO_CANCELAMENTO      VARCHAR(20),
  CD_LOGIN_TECNICO            VARCHAR(80),
  NM_UNIDADE_NEGOCIO_TECNICO  VARCHAR(120),
  TIPO_AREA                   VARCHAR(40),
  NM_CIDADE                   VARCHAR(100),
  NM_GRUPO                    VARCHAR(60),
  NM_REGIONAL                 VARCHAR(60),
  NM_CLUSTER                  VARCHAR(60),
  USR_ATEND                   VARCHAR(80),
  USR_BAIXA                   VARCHAR(80),
  USR_ATEND_PF                VARCHAR(120),
  USR_BAIXA_PF                VARCHAR(120),
  NM_REGIONAL_DTH             VARCHAR(60),
  NM_SEGMENTO_MUNICIPIO       VARCHAR(80),
  LINHA_NEGOCIO_DOM           VARCHAR(60),
  -- controle
  _ARQUIVO_ORIGEM             VARCHAR(120),
  _MES_REFERENCIA             CHAR(7),
  _LINHA_ARQUIVO              INT,
  KEY idx_stg_qb (NR_CONTRATO, NR_ORDEM_SERVICO, CD_OPERADORA),
  KEY idx_stg_qb_mes (_MES_REFERENCIA)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- STG_QUEBRA_COMPL  (90 colunas)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS stg_quebra_compl;
CREATE TABLE stg_quebra_compl (
  DSC_MARCA                       VARCHAR(60),
  DSC_SISTEMA_ORIGEM              VARCHAR(60),
  DSC_REGIONAL                    VARCHAR(60),
  DSC_GRUPO_REGIONAL              VARCHAR(60),
  DSC_CLUSTER                     VARCHAR(60),
  DSC_SUBCLUSTER                  VARCHAR(80),
  DSC_MUNICIPIO                   VARCHAR(100),
  DSC_SEGMENTO_MUNICIPIO          VARCHAR(80),
  DSC_REGIONAL_CMV                VARCHAR(80),
  DSC_GERENTE                     VARCHAR(150),
  UF                              VARCHAR(5),
  COD_IBGE                        VARCHAR(20),
  COD_OPERADORA                   VARCHAR(20),
  COD_CIDADE_NETSMS               VARCHAR(20),
  COD_BASE                        VARCHAR(20),
  DSC_GRUPO_OS                    VARCHAR(60),
  DSC_LINHA_NEGOCIO               VARCHAR(80),
  DSC_TIPO_SEGMENTO               VARCHAR(60),
  FLAG_ALTO_VALOR                 VARCHAR(10),
  FLAG_MDU                        VARCHAR(10),
  FLAG_NOVO_DOMICILIO             VARCHAR(10),
  DAT_NOTA                        VARCHAR(30),
  COD_OS                          VARCHAR(30),
  NUM_CONTRATO                    VARCHAR(30),
  NUM_SOLICITACAO                 VARCHAR(30),
  DAT_AGENDA_MES                  VARCHAR(10),
  DAT_AGENDA_QUINZENA             VARCHAR(10),
  DAT_AGENDA_DIA                  VARCHAR(10),
  DSC_TIPO_ORDEM_SERVICO          VARCHAR(120),
  COD_NODE                        VARCHAR(40),
  COD_PONTO                       VARCHAR(30),
  DSC_STATUS_OS                   VARCHAR(60),
  DAT_ABERTURA_ORDEM_SERVICO      VARCHAR(30),
  DSC_CANAL_VENDA                 VARCHAR(120),
  DSC_CANAL_VENDA_GRUPO           VARCHAR(120),
  DSC_CANAL_VENDA_SUBGRUPO        VARCHAR(120),
  LOGIN_VENDEDOR                  VARCHAR(80),
  NUM_CNPJ_PARCEIRO_VENDA         VARCHAR(40),
  DSC_PARCEIRO_VENDA              VARCHAR(150),
  DSC_PRODUTO                     VARCHAR(150),
  DAT_AGENDA                      VARCHAR(30),
  DSC_PERIODO_AGENDA              VARCHAR(40),
  FLAG_CONVENIENCIA               VARCHAR(10),
  FLAG_IMEDIATA                   VARCHAR(10),
  DSC_TIPO_PRODUTO                VARCHAR(60),
  DAT_AGENDAMENTO                 VARCHAR(30),
  COD_LOGIN_AGENDAMENTO           VARCHAR(80),
  DAT_REAGENDAMENTO               VARCHAR(30),
  COD_LOGIN_REAGENDAMENTO         VARCHAR(80),
  DSC_MOTIVO_REAGENDAMENTO        VARCHAR(255),
  COD_LOGIN_DESPACHO_OS           VARCHAR(80),
  DAT_INSTALACAO_CONTRATO         VARCHAR(30),
  DAT_HOR_BAIXA                   VARCHAR(30),
  DAT_INICIO_EXECUCAO             VARCHAR(30),
  DAT_TERMINO_EXECUCAO            VARCHAR(30),
  COD_EMPRESA_EXECUCAO            VARCHAR(30),
  DSC_EMPRESA_EXECUCAO            VARCHAR(150),
  NUM_CNPJ_EMPRESA_EXECUCAO       VARCHAR(40),
  COD_LOGIN_BAIXA_OS              VARCHAR(80),
  COD_BAIXA_OS                    VARCHAR(20),
  DSC_EQUIPE_TECNICA              VARCHAR(200),
  DSC_AREA_DESPACHO               VARCHAR(150),
  COD_EMPRESA_DESPACHO            VARCHAR(30),
  DSC_EMPRESA_DESPACHO            VARCHAR(150),
  NUM_CNPJ_EMPRESA_DESPACHO       VARCHAR(40),
  COD_IMOVEL                      VARCHAR(30),
  DSC_STATUS_TEC1                 VARCHAR(80),
  DSC_TIPO_TRATAMENTO             VARCHAR(60),
  NUM_WORKORDER_WORKFORCE         VARCHAR(60),
  COD_TECNICO_WFM                 VARCHAR(60),
  DSC_UNIDADE_NEGOCIO_TECNICO     VARCHAR(150),
  DSC_AREA_WORKFORCE              VARCHAR(80),
  DSC_BASE_WORKFORCE              VARCHAR(80),
  DSC_TIPO_TRATAMENTO_CHIP        VARCHAR(80),
  DSC_AREA_RESP_MOTIVO_BI         VARCHAR(80),
  DSC_QUEBRA_CENARIO              VARCHAR(80),
  DSC_CANAL_USUARIO_AGENDA        VARCHAR(120),
  DSC_EMPRESA_USUARIO_AGENDA      VARCHAR(150),
  DSC_PERFIL_USUARIO_AGENDA       VARCHAR(150),
  AREA_RESPONSAVEL_ORDEM_SERVICO  VARCHAR(120),
  DSC_TIPO_DESPACHO               VARCHAR(80),
  DSC_TIPO_DEPACHO_OS             VARCHAR(80),
  COD_USER_ABERTURA_SOLICITACAO   VARCHAR(80),
  NUM_CNPJ_PARCEIRO_ABERTURA      VARCHAR(40),
  DSC_USR_ATEND_PF                VARCHAR(150),
  COD_LOGIN_ATEND_OS              VARCHAR(80),
  DSC_PF_BAIXA                    VARCHAR(150),
  DSC_PARCEIRO_BAIXA              VARCHAR(150),
  NUM_CNPJ_PARCEIRO_BAIXA         VARCHAR(40),
  COD_MOTIVO_REAGENDAMENTO_OS     VARCHAR(20),
  DSC_OBSERVACAO_ORDEM_SERVICO    TEXT,
  CEP_CABEADO                     VARCHAR(60),
  -- controle
  _ARQUIVO_ORIGEM                 VARCHAR(120),
  _MES_REFERENCIA                 CHAR(7),
  _LINHA_ARQUIVO                  INT,
  KEY idx_stg_cp (NUM_CONTRATO, COD_OS, COD_OPERADORA),
  KEY idx_stg_cp_mes (_MES_REFERENCIA)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- STG_TOA  (16 colunas + 2 novas previstas: OPERADORA e CIDADE)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS stg_toa;
CREATE TABLE stg_toa (
  RECURSO                   VARCHAR(200),
  LOGIN_TECNICO             VARCHAR(60),
  DATA                      VARCHAR(30),
  STATUS_ATIVIDADE          VARCHAR(60),
  CONTRATO                  VARCHAR(30),
  AREA_TRABALHO             VARCHAR(80),
  BAIRRO                    VARCHAR(150),
  CATEGORIA_CAPACIDADE      VARCHAR(60),
  RECURSO_PAI               VARCHAR(150),
  PARCEIRA                  VARCHAR(100),
  ATRIBUTO                  VARCHAR(60),
  OS                        VARCHAR(30),
  DIA                       VARCHAR(10),
  MES                       VARCHAR(10),
  ANO                       VARCHAR(10),
  CHAVE                     VARCHAR(120),
  -- campos novos a serem incluidos no analitico
  OPERADORA                 VARCHAR(20),
  CIDADE                    VARCHAR(100),
  -- controle
  _ARQUIVO_ORIGEM           VARCHAR(120),
  _MES_REFERENCIA           CHAR(7),
  _LINHA_ARQUIVO            INT,
  KEY idx_stg_toa (CONTRATO, OS),
  KEY idx_stg_toa_mes (_MES_REFERENCIA)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- STG_SAFRA  (31 colunas)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS stg_safra;
CREATE TABLE stg_safra (
  DT_BASE                 VARCHAR(30),
  DATA_PEND               VARCHAR(30),
  DT_ACAO                 VARCHAR(30),
  NM_CIDADE               VARCHAR(100),
  NM_CLUSTER              VARCHAR(60),
  NM_SUBCLUSTER           VARCHAR(80),
  NM_REGIONAL             VARCHAR(60),
  DS_MODELO_EQPTO         VARCHAR(150),
  DS_SUBTIPO_EQPTO        VARCHAR(80),
  DS_TIPO_DESCONEXAO      VARCHAR(60),
  CD_NET                  VARCHAR(30),
  CD_OS                   VARCHAR(30),
  NR_AGING_OS             VARCHAR(20),
  NR_DIAS_EM_ABERTO       VARCHAR(20),
  DS_STATUS_CONTR         VARCHAR(120),
  MES_ANO_PEND            VARCHAR(20),
  MES_ANO_ACAO            VARCHAR(20),
  GRUPO                   VARCHAR(60),
  MOVIMENTACAO            VARCHAR(10),
  PENDENCIA               VARCHAR(10),
  SUB_TIPO_EQUIP          VARCHAR(80),
  NM_SEGMENTO_MUNICIPIO   VARCHAR(80),
  EPO                     VARCHAR(120),
  DDD                     VARCHAR(10),
  NR_SERIAL               VARCHAR(60),
  NR_MAC                  VARCHAR(60),
  POSSUI_TEC_DEDICADO     VARCHAR(10),
  SAFRA                   VARCHAR(10),
  ANO_MES                 VARCHAR(10),
  MES_REFERENCIA          VARCHAR(10),
  ANO_REFERENCIA          VARCHAR(10),
  -- controle
  _ARQUIVO_ORIGEM         VARCHAR(120),
  _MES_REFERENCIA         CHAR(7),
  _LINHA_ARQUIVO          INT,
  KEY idx_stg_sf (CD_NET),
  KEY idx_stg_sf_mes (_MES_REFERENCIA)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- STG_BACKLOG  (75 colunas)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS stg_backlog;
CREATE TABLE stg_backlog (
  DT_RELATORIO                VARCHAR(30),
  DIA                         VARCHAR(10),
  CD_OPERADORA                VARCHAR(20),
  CD_CONTRATO                 VARCHAR(30),
  NM_CIDADE                   VARCHAR(100),
  NM_REGIONAL                 VARCHAR(60),
  NM_GRUPO                    VARCHAR(60),
  NM_CLUSTER                  VARCHAR(60),
  NM_SUBCLUSTER               VARCHAR(80),
  NM_OPERADORA                VARCHAR(100),
  CD_OS                       VARCHAR(30),
  SOLIC                       VARCHAR(30),
  PRODUTO_PARA                VARCHAR(150),
  PRODUTO_DE                  VARCHAR(150),
  TIPO_PORTFOLIO              VARCHAR(80),
  TIPO_OS                     VARCHAR(120),
  STATUS_OS                   VARCHAR(60),
  TIPO_PRODUTO                VARCHAR(60),
  DOMICILIO                   VARCHAR(60),
  DATA_AGENDAMENTO            VARCHAR(30),
  AGING                       VARCHAR(20),
  DIAS_AGENDAMENTO            VARCHAR(20),
  TEMPO_ABERTURA_SEMANA       VARCHAR(20),
  MES_AGENDAMENTO             VARCHAR(20),
  DATA_ABERTURA_OS            VARCHAR(30),
  TEMPO_ABERTURA_DIAS         VARCHAR(20),
  MES                         VARCHAR(10),
  MES_RELATORIO               VARCHAR(20),
  LOGIN_ABERTURA_OS           VARCHAR(80),
  MES_GERACAO                 VARCHAR(20),
  GERADA_MES                  VARCHAR(20),
  IMEDIATA                    VARCHAR(10),
  PERIODO                     VARCHAR(40),
  CD_STATUS                   VARCHAR(20),
  ID_TIPO_OS                  VARCHAR(20),
  CD_OPERADORA_TI             VARCHAR(20),
  DIA_REAG                    VARCHAR(10),
  MES_REAGENDAMENTO           VARCHAR(20),
  DT_REAG                     VARCHAR(30),
  USER_REAG                   VARCHAR(80),
  MOTIVO_REAG                 VARCHAR(255),
  FX_TEMPO_BASE               VARCHAR(60),
  COMBO                       VARCHAR(80),
  PERFIL_USER_OS              VARCHAR(150),
  FUNC_ABRIU_OS               VARCHAR(150),
  PERFIL_USER_OS_AGE          VARCHAR(150),
  QTDE_CABLE_EMTAS            VARCHAR(20),
  QTDE_CABLE_MODEM            VARCHAR(20),
  QTDE_DECODER_ANALOG         VARCHAR(20),
  QTDE_DECODER_DIGITAL        VARCHAR(20),
  SEGMENTO_CONTRATO           VARCHAR(80),
  STATUS_CONTRATO             VARCHAR(120),
  TIPO_ASSINANTE              VARCHAR(80),
  PROD_DE                     VARCHAR(150),
  TIPO_CONTRATO               VARCHAR(80),
  CANAL_DE_VENDA_CONTRATO     VARCHAR(150),
  AREA_DESPACHO               VARCHAR(150),
  COD_NODE                    VARCHAR(40),
  ID_CANAL_VENDA_SUBGRUPO     VARCHAR(40),
  NOVO_CANAL_VENDA_GRUPO      VARCHAR(150),
  NM_CANAL_VENDA_SUBGRUPO     VARCHAR(150),
  CLASSE_OS                   VARCHAR(80),
  CONSOLIDA_OS                VARCHAR(80),
  BACKLOG_PRO                 VARCHAR(40),
  DS_TP_OCORRENCIA            VARCHAR(120),
  NM_AREA_GEO                 VARCHAR(120),
  TIPO_CLIENTE                VARCHAR(80),
  AGING_REGULATORIO           VARCHAR(20),
  DS_VENDEDOR                 VARCHAR(150),
  EMPRESA_VENDEDOR            VARCHAR(150),
  STATUS_REGULATORIO          VARCHAR(80),
  TP_ASSINATURA               VARCHAR(80),
  PERFIL                      VARCHAR(120),
  NM_TECNOLOGIA               VARCHAR(80),
  -- controle
  _ARQUIVO_ORIGEM             VARCHAR(120),
  _DT_POSICAO                 DATE,
  _LINHA_ARQUIVO              INT,
  KEY idx_stg_bk (CD_CONTRATO, CD_OPERADORA, CD_OS),
  KEY idx_stg_bk_dt (_DT_POSICAO)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- STG_METAS
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS stg_metas;
CREATE TABLE stg_metas (
  MES               VARCHAR(10),
  ANO               VARCHAR(10),
  SAFRA             VARCHAR(10),
  TIPO_DESCONEXAO   VARCHAR(40),
  META              VARCHAR(20),
  _ARQUIVO_ORIGEM   VARCHAR(120)
) ENGINE=InnoDB;


-- =====================================================================
-- CAMADA 4 — DIMENSOES
-- =====================================================================

-- ---------------------------------------------------------------------
-- DIM_OPERADORA_MUNICIPIO
-- Match obrigatorio 100%. Falha aqui bloqueia a carga.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS dim_operadora_municipio;
CREATE TABLE dim_operadora_municipio (
  CD_OPERADORA        INT           NOT NULL,
  NM_MUNICIPIO        VARCHAR(100)  NOT NULL,   -- acentuado (exibicao)
  NM_MUNICIPIO_NORM   VARCHAR(100)  NOT NULL,   -- normalizado (join)
  UF                  CHAR(2)       NULL,
  NM_CLUSTER          VARCHAR(60)   NULL,
  NM_SUBCLUSTER       VARCHAR(80)   NULL,
  NM_REGIONAL         VARCHAR(60)   NULL,
  ATIVO               TINYINT(1)    NOT NULL DEFAULT 1,
  PRIMARY KEY (CD_OPERADORA),
  UNIQUE KEY uk_mun_norm (NM_MUNICIPIO_NORM),
  KEY idx_uf (UF)
) ENGINE=InnoDB;

INSERT INTO dim_operadora_municipio
  (CD_OPERADORA, NM_MUNICIPIO, NM_MUNICIPIO_NORM, UF, NM_CLUSTER, NM_SUBCLUSTER, NM_REGIONAL) VALUES
  (178, 'Ananindeua',  'ANANINDEUA',  'PA', 'Cluster PA/AP',    'Subcluster PA',                    'Regional Leste'),
  (194, 'Belém',       'BELEM',       'PA', 'Cluster PA/AP',    'Subcluster PA',                    'Regional Leste'),
  ( 23, 'Castanhal',   'CASTANHAL',   'PA', 'Cluster PA/AP',    'Subcluster PA',                    'Regional Leste'),
  (713, 'Caxias',      'CAXIAS',      'MA', 'Cluster Maranhão', 'Subcluster Leste MA Interior',     'Regional Leste'),
  ( 51, 'Imperatriz',  'IMPERATRIZ',  'MA', 'Cluster Maranhão', 'Subcluster Oeste MA Interior',     'Regional Leste'),
  (393, 'Macapá',      'MACAPA',      'AP', 'Cluster PA/AP',    'Subcluster AP',                    'Regional Leste'),
  (121, 'Manaus',      'MANAUS',      'AM', 'Cluster AM/RR',    'Subcluster AM',                    'Regional Leste'),
  (  2, 'Marabá',      'MARABA',      'PA', 'Cluster PA/AP',    'Subcluster Carajás PA Interior',   'Regional Leste'),
  (628, 'Paragominas', 'PARAGOMINAS', 'PA', 'Cluster PA/AP',    'Subcluster PA Interior',           'Regional Leste'),
  (745, 'Parauapebas', 'PARAUAPEBAS', 'PA', 'Cluster PA/AP',    'Subcluster Carajás PA Interior',   'Regional Leste'),
  (616, 'Santana',     'SANTANA',     'AP', 'Cluster PA/AP',    'Subcluster AP',                    'Regional Leste'),
  ( 96, 'São Luís',    'SAO LUIS',    'MA', 'Cluster Maranhão', 'Subcluster MA',                    'Regional Leste'),
  (165, 'Timon',       'TIMON',       'MA', 'Cluster Maranhão', 'Subcluster Leste MA Interior',     'Regional Leste'),
  (156, 'Boa Vista',   'BOA VISTA',   'RR', 'Cluster AM/RR',    'Subcluster RR',                    'Regional Leste');

-- ---------------------------------------------------------------------
-- DIM_METAS
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS dim_metas;
CREATE TABLE dim_metas (
  MES                    TINYINT       NOT NULL,
  ANO                    SMALLINT      NOT NULL,
  SAFRA                  VARCHAR(5)    NOT NULL,   -- '1 M' | '4 M' | '13 M'
  TIPO_DESCONEXAO        VARCHAR(30)   NOT NULL,   -- exibicao
  TIPO_DESCONEXAO_NORM   VARCHAR(30)   NOT NULL,   -- join (upper sem acento)
  META                   DECIMAL(6,4)  NOT NULL,
  DT_CARGA               DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ANO, MES, SAFRA, TIPO_DESCONEXAO_NORM)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- DIM_FAIXA_AGING  (parametrizavel)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS dim_faixa_aging;
CREATE TABLE dim_faixa_aging (
  ID_FAIXA     TINYINT      NOT NULL,
  DS_FAIXA     VARCHAR(30)  NOT NULL,
  DIA_INICIO   INT          NOT NULL,
  DIA_FIM      INT          NOT NULL,
  ORDEM        TINYINT      NOT NULL,
  PRIMARY KEY (ID_FAIXA)
) ENGINE=InnoDB;

INSERT INTO dim_faixa_aging (ID_FAIXA, DS_FAIXA, DIA_INICIO, DIA_FIM, ORDEM) VALUES
  (1, '0-7 dias',    0,   7, 1),
  (2, '8-15 dias',   8,  15, 2),
  (3, '16-30 dias', 16,  30, 3),
  (4, '31-60 dias', 31,  60, 4),
  (5, '60+ dias',   61, 99999, 5);


-- =====================================================================
-- CAMADA 3 — FATOS
-- =====================================================================

-- ---------------------------------------------------------------------
-- FT_QUEBRA_HISTORICO
-- Grao: 1 linha da QUEBRA = 1 linha do fato. NUNCA multiplicar.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS ft_quebra_historico;
CREATE TABLE ft_quebra_historico (
  ID_QUEBRA                   BIGINT AUTO_INCREMENT PRIMARY KEY,
  HASH_REGISTRO               CHAR(64)      NOT NULL,
  ANO_REFERENCIA              SMALLINT      NOT NULL,
  MES_REFERENCIA              CHAR(7)       NOT NULL,
  DATA_EVENTO                 DATE          NULL,

  -- ===== BLOCO QUEBRA (integral) =====
  DH_GERACAO_ARQUIVO          DATETIME      NULL,
  NR_ORDEM_SERVICO            BIGINT        NULL,
  NR_SOLICITACAO              BIGINT        NULL,
  ID_TIPO_OS                  INT           NULL,
  TIPO_OS                     VARCHAR(120)  NULL,
  CD_IBGE                     INT           NULL,
  CD_OPERADORA                INT           NULL,
  MARCA                       VARCHAR(60)   NULL,
  CD_LOGIN_AGENDADOR          VARCHAR(80)   NULL,
  DATA_INSTALACAO             DATE          NULL,
  STATUS_OS                   VARCHAR(60)   NULL,
  DT_AGENDA                   DATE          NULL,
  DT_AGENDA_MES               TINYINT       NULL,
  DT_AGENDA_QUINZENA          TINYINT       NULL,
  DT_AGENDA_DIA               TINYINT       NULL,
  DS_PERIODO_AGENDA           VARCHAR(40)   NULL,
  NR_CONTRATO                 BIGINT        NULL,
  COD_NODE                    VARCHAR(40)   NULL,
  NM_TIPO_PRODUTO             VARCHAR(60)   NULL,
  DT_ABERTURA_OS              DATETIME      NULL,
  CD_LOGIN_ABERTURA_OS        VARCHAR(80)   NULL,
  NM_GRUPO_OS                 VARCHAR(60)   NULL,
  NM_CANAL_VENDA              VARCHAR(120)  NULL,
  NM_CANAL_VENDA_GRUPO        VARCHAR(120)  NULL,
  NM_CANAL_VENDA_SUBGRUPO     VARCHAR(120)  NULL,
  CD_LOGIN_VENDEDOR           VARCHAR(80)   NULL,
  DATA_BAIXA_OS               DATETIME      NULL,
  DH_REAGENDA                 DATETIME      NULL,
  NM_MOTIVO_REAGENDA          VARCHAR(255)  NULL,
  CD_LOGIN_REAGENDA           VARCHAR(80)   NULL,
  NM_TIPO_TRATAMENTO          VARCHAR(60)   NULL,   -- *** INDICADOR ***
  NM_TIPO_TRATAMENTO_CHIP     VARCHAR(60)   NULL,
  NM_NOVO_DOMICILIO           VARCHAR(20)   NULL,
  NM_LINHA_NEGOCIO            VARCHAR(60)   NULL,
  NM_QUEBRA_RESPONSAVEL       VARCHAR(80)   NULL,
  NM_QUEBRA_CENARIO           VARCHAR(80)   NULL,
  NM_STATUS_TEC1              VARCHAR(80)   NULL,
  NM_CARACTERISTICA_PRODUTO   VARCHAR(80)   NULL,
  CD_CODIGO_BAIXA             VARCHAR(20)   NULL,
  CD_CODIGO_CANCELAMENTO      VARCHAR(20)   NULL,
  CD_LOGIN_TECNICO            VARCHAR(80)   NULL,
  NM_UNIDADE_NEGOCIO_TECNICO  VARCHAR(120)  NULL,
  TIPO_AREA                   VARCHAR(40)   NULL,
  NM_CIDADE                   VARCHAR(100)  NULL,
  NM_GRUPO                    VARCHAR(60)   NULL,
  NM_REGIONAL                 VARCHAR(60)   NULL,
  NM_CLUSTER                  VARCHAR(60)   NULL,
  USR_ATEND                   VARCHAR(80)   NULL,
  USR_BAIXA                   VARCHAR(80)   NULL,
  USR_ATEND_PF                VARCHAR(120)  NULL,
  USR_BAIXA_PF                VARCHAR(120)  NULL,
  NM_REGIONAL_DTH             VARCHAR(60)   NULL,
  NM_SEGMENTO_MUNICIPIO       VARCHAR(80)   NULL,
  LINHA_NEGOCIO_DOM           VARCHAR(60)   NULL,

  -- ===== DERIVADOS DA DIMENSAO =====
  NM_MUNICIPIO                VARCHAR(100)  NULL,
  NM_MUNICIPIO_NORM           VARCHAR(100)  NULL,
  UF                          CHAR(2)       NULL,

  -- ===== BLOCO COMPLEMENTO (prefixo CP_) =====
  CP_UF                             VARCHAR(5)    NULL,
  CP_DSC_SUBCLUSTER                 VARCHAR(80)   NULL,
  CP_DSC_REGIONAL_CMV               VARCHAR(80)   NULL,
  CP_DSC_GERENTE                    VARCHAR(150)  NULL,
  CP_COD_CIDADE_NETSMS              VARCHAR(20)   NULL,
  CP_COD_BASE                       VARCHAR(20)   NULL,
  CP_DSC_TIPO_SEGMENTO              VARCHAR(60)   NULL,
  CP_DSC_LINHA_NEGOCIO              VARCHAR(80)   NULL,
  CP_FLAG_ALTO_VALOR                VARCHAR(10)   NULL,
  CP_FLAG_MDU                       VARCHAR(10)   NULL,
  CP_FLAG_CONVENIENCIA              VARCHAR(10)   NULL,
  CP_FLAG_IMEDIATA                  VARCHAR(10)   NULL,
  CP_DSC_PRODUTO                    VARCHAR(150)  NULL,
  CP_COD_PONTO                      VARCHAR(30)   NULL,
  CP_DAT_NOTA                       DATE          NULL,
  CP_DAT_AGENDAMENTO                DATETIME      NULL,
  CP_DAT_HOR_BAIXA                  DATETIME      NULL,
  CP_DAT_INICIO_EXECUCAO            DATETIME      NULL,
  CP_DAT_TERMINO_EXECUCAO           DATETIME      NULL,
  CP_COD_EMPRESA_EXECUCAO           VARCHAR(30)   NULL,
  CP_DSC_EMPRESA_EXECUCAO           VARCHAR(150)  NULL,
  CP_NUM_CNPJ_EMPRESA_EXECUCAO      VARCHAR(40)   NULL,
  CP_DSC_EQUIPE_TECNICA             VARCHAR(200)  NULL,
  CP_DSC_AREA_DESPACHO              VARCHAR(150)  NULL,
  CP_COD_EMPRESA_DESPACHO           VARCHAR(30)   NULL,
  CP_DSC_EMPRESA_DESPACHO           VARCHAR(150)  NULL,
  CP_NUM_CNPJ_EMPRESA_DESPACHO      VARCHAR(40)   NULL,
  CP_COD_IMOVEL                     VARCHAR(30)   NULL,
  CP_NUM_WORKORDER_WORKFORCE        VARCHAR(60)   NULL,
  CP_COD_TECNICO_WFM                VARCHAR(60)   NULL,
  CP_DSC_AREA_WORKFORCE             VARCHAR(80)   NULL,
  CP_DSC_BASE_WORKFORCE             VARCHAR(80)   NULL,
  CP_DSC_AREA_RESP_MOTIVO_BI        VARCHAR(80)   NULL,
  CP_DSC_QUEBRA_CENARIO             VARCHAR(80)   NULL,
  CP_DSC_CANAL_USUARIO_AGENDA       VARCHAR(120)  NULL,
  CP_DSC_EMPRESA_USUARIO_AGENDA     VARCHAR(150)  NULL,
  CP_DSC_PERFIL_USUARIO_AGENDA      VARCHAR(150)  NULL,
  CP_AREA_RESPONSAVEL_ORDEM_SERVICO VARCHAR(120)  NULL,
  CP_DSC_TIPO_DESPACHO              VARCHAR(80)   NULL,
  CP_DSC_TIPO_DEPACHO_OS            VARCHAR(80)   NULL,
  CP_COD_USER_ABERTURA_SOLICITACAO  VARCHAR(80)   NULL,
  CP_DSC_USR_ATEND_PF               VARCHAR(150)  NULL,
  CP_DSC_PF_BAIXA                   VARCHAR(150)  NULL,
  CP_DSC_PARCEIRO_BAIXA             VARCHAR(150)  NULL,
  CP_COD_MOTIVO_REAGENDAMENTO_OS    VARCHAR(20)   NULL,
  CP_DSC_OBSERVACAO_ORDEM_SERVICO   TEXT          NULL,
  CP_CEP_CABEADO                    VARCHAR(60)   NULL,

  -- ===== BLOCO TOA (prefixo TOA_) =====
  TOA_PARCEIRA                VARCHAR(100)  NULL,
  TOA_RECURSO                 VARCHAR(200)  NULL,
  TOA_LOGIN_TECNICO           VARCHAR(60)   NULL,
  TOA_STATUS_ATIVIDADE        VARCHAR(60)   NULL,
  TOA_AREA_TRABALHO           VARCHAR(80)   NULL,
  TOA_BAIRRO                  VARCHAR(150)  NULL,
  TOA_CATEGORIA_CAPACIDADE    VARCHAR(60)   NULL,
  TOA_RECURSO_PAI             VARCHAR(150)  NULL,
  TOA_DATA                    DATE          NULL,
  TOA_ATRIBUTO                VARCHAR(60)   NULL,

  -- ===== RASTREABILIDADE =====
  NIVEL_MATCH_COMPLEMENTO     VARCHAR(20)   NOT NULL DEFAULT 'N0_SEM_MATCH',
  NIVEL_MATCH_TOA             VARCHAR(20)   NOT NULL DEFAULT 'N0_SEM_MATCH',
  ARQUIVO_ORIGEM_QUEBRA       VARCHAR(120)  NULL,
  ARQUIVO_ORIGEM_COMPL        VARCHAR(120)  NULL,
  ARQUIVO_ORIGEM_TOA          VARCHAR(120)  NULL,
  DT_CARGA                    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

  UNIQUE KEY uk_qb_hash (HASH_REGISTRO),
  KEY idx_qb_mes          (MES_REFERENCIA),
  KEY idx_qb_contrato     (NR_CONTRATO, CD_OPERADORA),
  KEY idx_qb_os           (NR_ORDEM_SERVICO),
  KEY idx_qb_data         (DATA_EVENTO),
  KEY idx_qb_tratamento   (NM_TIPO_TRATAMENTO, MES_REFERENCIA),
  KEY idx_qb_parceira     (TOA_PARCEIRA),
  KEY idx_qb_municipio    (NM_MUNICIPIO_NORM),
  KEY idx_qb_cluster      (NM_CLUSTER)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- FT_SAFRA_HISTORICO
-- Grao: 1 linha da SAFRA = 1 linha do fato. NUNCA multiplicar.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS ft_safra_historico;
CREATE TABLE ft_safra_historico (
  ID_SAFRA                BIGINT AUTO_INCREMENT PRIMARY KEY,
  HASH_REGISTRO           CHAR(64)      NOT NULL,
  ANO_REFERENCIA          SMALLINT      NOT NULL,
  MES_REFERENCIA          CHAR(7)       NOT NULL,

  -- ===== BLOCO SAFRA (integral) =====
  DT_BASE                 DATE          NULL,
  DATA_PEND               DATE          NULL,
  DT_ACAO                 DATE          NULL,
  NM_CIDADE               VARCHAR(100)  NULL,
  NM_CLUSTER              VARCHAR(60)   NULL,
  NM_SUBCLUSTER           VARCHAR(80)   NULL,
  NM_REGIONAL             VARCHAR(60)   NULL,
  DS_MODELO_EQPTO         VARCHAR(150)  NULL,
  DS_SUBTIPO_EQPTO        VARCHAR(80)   NULL,
  DS_TIPO_DESCONEXAO      VARCHAR(60)   NULL,   -- Opcao | Inadimplencia
  DS_TIPO_DESCONEXAO_NORM VARCHAR(30)   NULL,   -- join com meta
  CD_NET                  BIGINT        NULL,   -- = contrato
  CD_OS                   BIGINT        NULL,   -- pode ser NULL
  NR_AGING_OS             INT           NULL,
  NR_DIAS_EM_ABERTO       INT           NULL,
  DS_STATUS_CONTR         VARCHAR(120)  NULL,
  MES_ANO_PEND            VARCHAR(20)   NULL,
  MES_ANO_ACAO            VARCHAR(20)   NULL,
  GRUPO                   VARCHAR(60)   NULL,
  MOVIMENTACAO            TINYINT       NULL,
  PENDENCIA               TINYINT       NULL,   -- *** INDICADOR *** 0=Recup 1=Pend
  SUB_TIPO_EQUIP          VARCHAR(80)   NULL,
  NM_SEGMENTO_MUNICIPIO   VARCHAR(80)   NULL,
  EPO                     VARCHAR(120)  NULL,
  DDD                     VARCHAR(10)   NULL,
  NR_SERIAL               VARCHAR(60)   NULL,
  NR_MAC                  VARCHAR(60)   NULL,
  POSSUI_TEC_DEDICADO     VARCHAR(10)   NULL,
  SAFRA                   VARCHAR(10)   NULL,   -- 1 M | 4 M | 13 M
  ANO_MES                 VARCHAR(10)   NULL,

  -- ===== DERIVADOS DA DIMENSAO =====
  CD_OPERADORA            INT           NULL,
  NM_MUNICIPIO            VARCHAR(100)  NULL,
  NM_MUNICIPIO_NORM       VARCHAR(100)  NULL,
  UF                      CHAR(2)       NULL,

  -- ===== BLOCO QUEBRA REDUZIDO (prefixo QB_) =====
  QB_NR_ORDEM_SERVICO         BIGINT        NULL,
  QB_DT_AGENDA                DATE          NULL,
  QB_STATUS_OS                VARCHAR(60)   NULL,
  QB_TIPO_OS                  VARCHAR(120)  NULL,
  QB_NM_TIPO_TRATAMENTO       VARCHAR(60)   NULL,
  QB_NM_QUEBRA_RESPONSAVEL    VARCHAR(80)   NULL,
  QB_NM_QUEBRA_CENARIO        VARCHAR(80)   NULL,
  QB_NM_MOTIVO_REAGENDA       VARCHAR(255)  NULL,
  QB_CD_CODIGO_BAIXA          VARCHAR(20)   NULL,
  QB_DATA_BAIXA_OS            DATETIME      NULL,
  QTD_OS_CONTRATO             INT           NOT NULL DEFAULT 0,
  QTD_QUEBRAS_CONTRATO        INT           NOT NULL DEFAULT 0,
  QTD_REAGENDAMENTOS_CONTRATO INT           NOT NULL DEFAULT 0,
  DT_PRIMEIRA_AGENDA          DATE          NULL,
  DT_ULTIMA_AGENDA            DATE          NULL,

  -- ===== BLOCO TOA =====
  TOA_PARCEIRA                VARCHAR(100)  NULL,
  TOA_RECURSO                 VARCHAR(200)  NULL,
  TOA_LOGIN_TECNICO           VARCHAR(60)   NULL,
  TOA_STATUS_ATIVIDADE        VARCHAR(60)   NULL,
  TOA_AREA_TRABALHO           VARCHAR(80)   NULL,
  TOA_BAIRRO                  VARCHAR(150)  NULL,
  TOA_DATA                    DATE          NULL,

  -- ===== BLOCO BACKLOG (agregados do log) =====
  BK_POSSUI_BACKLOG               TINYINT(1)    NOT NULL DEFAULT 0,
  BK_SITUACAO_AGENDA              VARCHAR(40)   NULL,   -- AGENDADO | SEM AGENDA
  BK_DT_AGENDA                    DATE          NULL,
  BK_STATUS_OS                    VARCHAR(60)   NULL,
  BK_AGING                        INT           NULL,
  BK_FX_TEMPO_BASE                VARCHAR(60)   NULL,
  BK_MOTIVO_REAG                  VARCHAR(255)  NULL,
  BK_STATUS_CONTRATO              VARCHAR(120)  NULL,
  BK_SEGMENTO_CONTRATO            VARCHAR(80)   NULL,
  BK_TIPO_ASSINANTE               VARCHAR(80)   NULL,
  BK_NM_TECNOLOGIA                VARCHAR(80)   NULL,
  BK_QTD_DIAS_EM_BACKLOG          INT           NOT NULL DEFAULT 0,
  BK_QTD_AGENDAMENTOS             INT           NOT NULL DEFAULT 0,
  BK_QTD_REAGENDAMENTOS           INT           NOT NULL DEFAULT 0,
  BK_PRIMEIRA_APARICAO            DATE          NULL,
  BK_ULTIMA_APARICAO              DATE          NULL,
  BK_MOTIVO_REAG_MAIS_FREQUENTE   VARCHAR(255)  NULL,
  BK_QTDE_EQUIPAMENTOS_TOTAL      INT           NULL,

  -- ===== META (snapshot para performance) =====
  META_VIGENTE            DECIMAL(6,4)  NULL,

  -- ===== RASTREABILIDADE =====
  NIVEL_MATCH_QUEBRA      VARCHAR(20)   NOT NULL DEFAULT 'S0_SEM_MATCH',
  NIVEL_MATCH_TOA         VARCHAR(20)   NOT NULL DEFAULT 'S0_SEM_MATCH',
  NIVEL_MATCH_BACKLOG     VARCHAR(20)   NOT NULL DEFAULT 'S0_SEM_MATCH',
  ARQUIVO_ORIGEM_SAFRA    VARCHAR(120)  NULL,
  DT_CARGA                DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

  UNIQUE KEY uk_sf_hash (HASH_REGISTRO),
  KEY idx_sf_mes         (MES_REFERENCIA),
  KEY idx_sf_contrato    (CD_NET, CD_OPERADORA),
  KEY idx_sf_safra_tipo  (SAFRA, DS_TIPO_DESCONEXAO_NORM, MES_REFERENCIA),
  KEY idx_sf_pendencia   (PENDENCIA, MES_REFERENCIA),
  KEY idx_sf_municipio   (NM_MUNICIPIO_NORM),
  KEY idx_sf_parceira    (TOA_PARCEIRA),
  KEY idx_sf_backlog     (BK_SITUACAO_AGENDA)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- FT_BACKLOG_LOG
-- Grao: CONTRATO + OPERADORA + OS + DT_RELATORIO
-- INSERT incremental. NUNCA apaga. E o log de movimentacao.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS ft_backlog_log;
CREATE TABLE ft_backlog_log (
  ID_BACKLOG              BIGINT AUTO_INCREMENT PRIMARY KEY,
  HASH_REGISTRO           CHAR(64)      NOT NULL,
  DT_RELATORIO            DATE          NOT NULL,
  MES_REFERENCIA          CHAR(7)       NOT NULL,

  CD_OPERADORA            INT           NULL,
  CD_OPERADORA_TI         VARCHAR(20)   NULL,
  CD_CONTRATO             BIGINT        NULL,
  CD_OS                   BIGINT        NULL,
  SOLIC                   BIGINT        NULL,

  -- geografia
  NM_CIDADE               VARCHAR(100)  NULL,
  NM_REGIONAL             VARCHAR(60)   NULL,
  NM_GRUPO                VARCHAR(60)   NULL,
  NM_CLUSTER              VARCHAR(60)   NULL,
  NM_SUBCLUSTER           VARCHAR(80)   NULL,
  NM_OPERADORA            VARCHAR(100)  NULL,
  NM_AREA_GEO             VARCHAR(120)  NULL,
  AREA_DESPACHO           VARCHAR(150)  NULL,
  COD_NODE                VARCHAR(40)   NULL,
  NM_MUNICIPIO            VARCHAR(100)  NULL,
  NM_MUNICIPIO_NORM       VARCHAR(100)  NULL,
  UF                      CHAR(2)       NULL,

  -- agenda (nucleo do log)
  STATUS_OS               VARCHAR(60)   NULL,
  CD_STATUS               VARCHAR(20)   NULL,
  SITUACAO_AGENDA         VARCHAR(40)   NULL,   -- derivado: AGENDADO | SEM AGENDA
  DATA_AGENDAMENTO        DATE          NULL,
  MES_AGENDAMENTO         VARCHAR(20)   NULL,
  DIAS_AGENDAMENTO        INT           NULL,
  PERIODO                 VARCHAR(40)   NULL,
  IMEDIATA                VARCHAR(10)   NULL,
  DT_REAG                 DATE          NULL,
  DIA_REAG                TINYINT       NULL,
  MES_REAGENDAMENTO       VARCHAR(20)   NULL,
  USER_REAG               VARCHAR(80)   NULL,
  MOTIVO_REAG             VARCHAR(255)  NULL,

  -- aging
  AGING                   INT           NULL,
  AGING_REGULATORIO       INT           NULL,
  TEMPO_ABERTURA_DIAS     INT           NULL,
  TEMPO_ABERTURA_SEMANA   VARCHAR(20)   NULL,
  FX_TEMPO_BASE           VARCHAR(60)   NULL,
  DATA_ABERTURA_OS        DATETIME      NULL,
  LOGIN_ABERTURA_OS       VARCHAR(80)   NULL,
  FUNC_ABRIU_OS           VARCHAR(150)  NULL,

  -- contrato
  STATUS_CONTRATO         VARCHAR(120)  NULL,
  SEGMENTO_CONTRATO       VARCHAR(80)   NULL,
  TIPO_CONTRATO           VARCHAR(80)   NULL,
  TIPO_ASSINANTE          VARCHAR(80)   NULL,
  TIPO_CLIENTE            VARCHAR(80)   NULL,
  TP_ASSINATURA           VARCHAR(80)   NULL,
  PERFIL                  VARCHAR(120)  NULL,
  NM_TECNOLOGIA           VARCHAR(80)   NULL,
  STATUS_REGULATORIO      VARCHAR(80)   NULL,
  DOMICILIO               VARCHAR(60)   NULL,
  COMBO                   VARCHAR(80)   NULL,

  -- equipamentos
  QTDE_CABLE_EMTAS        INT           NULL,
  QTDE_CABLE_MODEM        INT           NULL,
  QTDE_DECODER_ANALOG     INT           NULL,
  QTDE_DECODER_DIGITAL    INT           NULL,
  QTDE_EQUIP_TOTAL        INT           NULL,   -- derivado

  -- OS e produto
  TIPO_OS                 VARCHAR(120)  NULL,
  ID_TIPO_OS              INT           NULL,
  TIPO_PRODUTO            VARCHAR(60)   NULL,
  TIPO_PORTFOLIO          VARCHAR(80)   NULL,
  PRODUTO_DE              VARCHAR(150)  NULL,
  PRODUTO_PARA            VARCHAR(150)  NULL,
  PROD_DE                 VARCHAR(150)  NULL,
  CLASSE_OS               VARCHAR(80)   NULL,
  CONSOLIDA_OS            VARCHAR(80)   NULL,
  BACKLOG_PRO             VARCHAR(40)   NULL,
  DS_TP_OCORRENCIA        VARCHAR(120)  NULL,

  -- canal de venda
  CANAL_DE_VENDA_CONTRATO   VARCHAR(150) NULL,
  ID_CANAL_VENDA_SUBGRUPO   VARCHAR(40)  NULL,
  NOVO_CANAL_VENDA_GRUPO    VARCHAR(150) NULL,
  NM_CANAL_VENDA_SUBGRUPO   VARCHAR(150) NULL,
  DS_VENDEDOR               VARCHAR(150) NULL,
  EMPRESA_VENDEDOR          VARCHAR(150) NULL,

  -- perfis
  PERFIL_USER_OS          VARCHAR(150)  NULL,
  PERFIL_USER_OS_AGE      VARCHAR(150)  NULL,
  MES_GERACAO             VARCHAR(20)   NULL,
  GERADA_MES              VARCHAR(20)   NULL,

  -- controle
  ARQUIVO_ORIGEM          VARCHAR(120)  NULL,
  DT_CARGA                DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

  UNIQUE KEY uk_bk_hash (HASH_REGISTRO),
  KEY idx_bk_contrato   (CD_CONTRATO, CD_OPERADORA),
  KEY idx_bk_relatorio  (DT_RELATORIO),
  KEY idx_bk_os         (CD_OS),
  KEY idx_bk_situacao   (SITUACAO_AGENDA, DT_RELATORIO),
  KEY idx_bk_municipio  (NM_MUNICIPIO_NORM),
  KEY idx_bk_motivo     (MOTIVO_REAG),
  KEY idx_bk_mes        (MES_REFERENCIA)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- FT_BACKLOG_ATUAL
-- Derivada do log: ultima posicao por CONTRATO + OPERADORA + OS.
-- Regerada a cada carga (TRUNCATE + INSERT a partir do log).
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS ft_backlog_atual;
CREATE TABLE ft_backlog_atual LIKE ft_backlog_log;
ALTER TABLE ft_backlog_atual
  ADD COLUMN DT_POSICAO DATE NULL AFTER DT_RELATORIO,
  ADD COLUMN QTD_APARICOES INT NOT NULL DEFAULT 0,
  ADD COLUMN QTD_REAGENDAMENTOS INT NOT NULL DEFAULT 0;


-- =====================================================================
-- CAMADA 6 — AUDITORIA
-- =====================================================================

DROP TABLE IF EXISTS tb_auditoria_carga;
CREATE TABLE tb_auditoria_carga (
  ID_CARGA                  BIGINT AUTO_INCREMENT PRIMARY KEY,
  DT_INICIO                 DATETIME      NOT NULL,
  DT_FIM                    DATETIME      NULL,
  DOMINIO                   VARCHAR(20)   NOT NULL,  -- QUEBRA|SAFRA|BACKLOG|TOA|COMPL|METAS
  ARQUIVO                   VARCHAR(200)  NULL,
  MES_REFERENCIA            CHAR(7)       NULL,
  REGISTROS_LIDOS           INT           NOT NULL DEFAULT 0,
  REGISTROS_INSERIDOS       INT           NOT NULL DEFAULT 0,
  REGISTROS_REJEITADOS      INT           NOT NULL DEFAULT 0,
  PCT_MATCH_COMPLEMENTO     DECIMAL(5,2)  NULL,
  PCT_MATCH_TOA             DECIMAL(5,2)  NULL,
  PCT_MATCH_BACKLOG         DECIMAL(5,2)  NULL,
  QTD_N1                    INT           NULL,
  QTD_N2                    INT           NULL,
  QTD_N3                    INT           NULL,
  QTD_SEM_MATCH             INT           NULL,
  TEMPO_PROCESSAMENTO_SEG   INT           NULL,
  STATUS                    VARCHAR(20)   NOT NULL,  -- OK|ERRO|ALERTA
  MENSAGEM                  TEXT          NULL,
  KEY idx_aud_dominio (DOMINIO, MES_REFERENCIA),
  KEY idx_aud_dt (DT_INICIO)
) ENGINE=InnoDB;

DROP TABLE IF EXISTS tb_auditoria_exportacao;
CREATE TABLE tb_auditoria_exportacao (
  ID_EXPORTACAO         BIGINT AUTO_INCREMENT PRIMARY KEY,
  USUARIO               VARCHAR(100)  NOT NULL,
  TIPO_ANALITICO        VARCHAR(40)   NOT NULL,
  FILTROS_JSON          JSON          NULL,
  QUANTIDADE_REGISTROS  INT           NULL,
  FORMATO               VARCHAR(10)   NULL,
  DATA_SOLICITACAO      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  DATA_CONCLUSAO        DATETIME      NULL,
  STATUS                VARCHAR(20)   NOT NULL DEFAULT 'PROCESSANDO',
  MENSAGEM_ERRO         TEXT          NULL,
  KEY idx_exp_usuario (USUARIO),
  KEY idx_exp_data (DATA_SOLICITACAO)
) ENGINE=InnoDB;

DROP TABLE IF EXISTS tb_teste_aceite;
CREATE TABLE tb_teste_aceite (
  ID_TESTE          BIGINT AUTO_INCREMENT PRIMARY KEY,
  ID_CARGA          BIGINT        NULL,
  DT_EXECUCAO       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  NOME_TESTE        VARCHAR(120)  NOT NULL,
  VALOR_ESPERADO    VARCHAR(100)  NULL,
  VALOR_OBTIDO      VARCHAR(100)  NULL,
  RESULTADO         VARCHAR(10)   NOT NULL,  -- PASS | FAIL
  OBSERVACAO        TEXT          NULL,
  KEY idx_teste_carga (ID_CARGA),
  KEY idx_teste_result (RESULTADO)
) ENGINE=InnoDB;

SET FOREIGN_KEY_CHECKS = 1;

-- =====================================================================
-- FIM DO SCRIPT 01
-- Proximo: 02_views_consumo.sql
-- =====================================================================
