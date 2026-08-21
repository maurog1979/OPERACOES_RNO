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

    q = f'''
    SELECT
        nivel,
        safra,
        ds_tipo_desconexao
    FROM {tabela}
    LIMIT 50
    '''

    print(pd.read_sql(q, conn))

conn.close()
