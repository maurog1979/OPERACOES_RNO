# corrigir_dash_safra_conexao_safra_v4.py
# FASE 2C — Correção definitiva da conexão do Painel Safra
# Baseado no relatorio_localizar_origem_safra_v3.txt:
# - A origem correta das tabelas é database='safra', host='localhost', user='root', port=3306.
# - O ambiente atual acusou ModuleNotFoundError: No module named 'mysql'.
# - Este script regrava dash_safra.py para tentar PyMySQL primeiro, mysql.connector depois,
#   e retornar erro explícito na API caso nenhum driver esteja instalado.
#
# Execute na raiz do projeto:
# cd "C:\Users\n5996917\OneDrive - Claro SA\INTRANET\OPERACOES_RNO"
# python corrigir_dash_safra_conexao_safra_v4.py

from pathlib import Path
from datetime import datetime

ROOT = Path.cwd()
PADRAO = Path(r"C:\Users\n5996917\OneDrive - Claro SA\INTRANET\OPERACOES_RNO")
if not (ROOT / "areas" / "adm" / "desconexao").exists() and PADRAO.exists():
    ROOT = PADRAO

DASH = ROOT / "areas" / "adm" / "desconexao" / "dash_safra.py"
REL = ROOT / "relatorio_corrigir_dash_safra_conexao_safra_v4.txt"

DASH_CODE = r