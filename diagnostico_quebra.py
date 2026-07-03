# -*- coding: utf-8 -*-
# =============================================================
# diagnostico_quebra.py
# Detecta schema real da tabela quebra_total antes de gerar dash
# =============================================================

from sqlalchemy import create_engine, text
import pandas as pd

DB = "mysql+pymysql://root:@localhost:3306/safra"

COLS_ESPERADAS = [
    "NR_CONTRATO", "NM_CIDADE", "UF", "DT_AGENDA",
    "ANO", "MES", "DIA",
    "NM_TIPO_TRATAMENTO", "NM_MOTIVO_REAGENDA",
    "NM_QUEBRA_RESPONSAVEL", "NM_QUEBRA_CENARIO",
    "PARCEIRA", "PARCEIRA_NOME",
]

print("=" * 70)
print("DIAGNOSTICO quebra_total - Portal Operacoes RNO")
print("=" * 70)

try:
    engine = create_engine(DB)

    # 1. DESCRIBE
    print("\n[1] ESTRUTURA DA TABELA (DESCRIBE quebra_total)")
    print("-" * 70)
    desc = pd.read_sql("DESCRIBE quebra_total", engine)
    print(desc.to_string(index=False))

    cols_reais = set(desc["Field"].str.upper().tolist())

    # 2. Checar colunas esperadas
    print("\n[2] CHECK DE COLUNAS ESPERADAS")
    print("-" * 70)
    faltando = []
    for c in COLS_ESPERADAS:
        ok = c.upper() in cols_reais
        marca = "OK " if ok else "FALTA"
        print(f"  [{marca}] {c}")
        if not ok:
            faltando.append(c)

    # 3. Tipo da DT_AGENDA
    print("\n[3] TIPO DA COLUNA DT_AGENDA")
    print("-" * 70)
    tipo_dt = desc[desc["Field"].str.upper() == "DT_AGENDA"]
    if not tipo_dt.empty:
        print(f"  Tipo MySQL: {tipo_dt['Type'].values[0]}")
    else:
        print("  DT_AGENDA NAO ENCONTRADA")

    # 4. Total de linhas
    print("\n[4] TOTAL DE LINHAS")
    print("-" * 70)
    total = pd.read_sql("SELECT COUNT(*) AS n FROM quebra_total", engine)
    print(f"  Total: {total['n'].values,} linhas")

    # 5. Amostra das colunas-chave
    print("\n[5] AMOSTRA (3 linhas) das colunas-chave")
    print("-" * 70)
    cols_disp = [c for c in COLS_ESPERADAS if c.upper() in cols_reais]
    if cols_disp:
        sample = pd.read_sql(
            f"SELECT {', '.join(cols_disp)} FROM quebra_total LIMIT 3",
            engine,
        )
        for i, row in sample.iterrows():
            print(f"\n  Linha {i+1}:")
            for c in cols_disp:
                v = row[c]
                print(f"    {c:25s} = {repr(v)[:80]}")

    # 6. Valores distintos das chaves
    print("\n[6] VALORES DISTINTOS (top 10)")
    print("-" * 70)
    for col in ["UF", "PARCEIRA_NOME", "NM_TIPO_TRATAMENTO", "ANO", "MES"]:
        if col.upper() in cols_reais:
            try:
                q = f"SELECT {col}, COUNT(*) AS n FROM quebra_total " \
                    f"GROUP BY {col} ORDER BY n DESC LIMIT 10"
                d = pd.read_sql(q, engine)
                print(f"\n  >> {col}:")
                for _, r in d.iterrows():
                    print(f"     {repr(r[col])[:40]:40s} -> {r['n']:,}")
            except Exception as e:
                print(f"  {col}: erro -> {e}")

    # 7. Amostra de DT_AGENDA (formato real)
    print("\n[7] FORMATO REAL DA DT_AGENDA (5 amostras)")
    print("-" * 70)
    if "DT_AGENDA" in cols_reais:
        try:
            d = pd.read_sql(
                "SELECT DT_AGENDA FROM quebra_total "
                "WHERE DT_AGENDA IS NOT NULL LIMIT 5", engine
            )
            for v in d["DT_AGENDA"].tolist():
                print(f"  -> {repr(v)} (tipo Python: {type(v).__name__})")
        except Exception as e:
            print(f"  Erro: {e}")

    # 8. Diagnostico final
    print("\n" + "=" * 70)
    print("DIAGNOSTICO FINAL")
    print("=" * 70)
    if not faltando:
        print("  [OK] Tabela quebra_total tem TODAS as colunas necessarias")
        print("  [OK] enriquecer_quebra.py JA FOI executado")
    else:
        print(f"  [ATENCAO] FALTAM {len(faltando)} colunas:")
        for c in faltando:
            print(f"     - {c}")
        print("\n  >> PRECISA rodar enriquecer_quebra.py ANTES do dash")

    engine.dispose()
    print("\n[FIM] Cole esse output completo no chat.\n")

except Exception as e:
    print(f"\n[ERRO FATAL] {e}")
    print("Verifique: Laragon ligado? MySQL na porta 3306? Tabela existe?")