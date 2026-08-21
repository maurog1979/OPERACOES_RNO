import pymysql
import pandas as pd

conn = pymysql.connect(
    host='localhost',
    user='root',
    password='',
    database='safra',
    charset='utf8mb4'
)

for tabela in [
    'safra_resumo_mensal',
    'safra_resumo_diario',
    'safra_metas'
]:
    print("\n" + "=" * 80)
    print(tabela.upper())
    print("=" * 80)

    df = pd.read_sql(f"SHOW COLUMNS FROM {tabela}", conn)
    print(df[['Field', 'Type']])

conn.close()