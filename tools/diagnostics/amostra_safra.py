from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import Config
import pymysql
import pandas as pd

conn = pymysql.connect(**Config.db_config_pymysql())

for tabela in [
    'safra_resumo_mensal',
    'safra_resumo_diario'
]:
    print("\n" + "="*100)
    print(tabela.upper())
    print("="*100)

    df = pd.read_sql(
        f"SELECT * FROM {tabela} LIMIT 20",
        conn
    )

    print(df)

conn.close()
