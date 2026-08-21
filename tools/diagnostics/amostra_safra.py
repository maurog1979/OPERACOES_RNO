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