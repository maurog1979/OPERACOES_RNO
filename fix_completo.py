# -*- coding: utf-8 -*-
"""
CORREÇÃO V3 — DASH_LOG MOTIVOS E RESPONSÁVEIS SEM FALLBACK INDEVIDO

Problema anterior:
- G3 caiu em FAIXA_LOG, duplicando a seção Distribuição do LOG.
- G4 caiu em NM_CIDADE, duplicando a seção Cidades.
- Visualmente preencheu, mas conceitualmente ficou errado.

Objetivo:
- Corrigir SOMENTE o dash_log.
- G3 usa apenas colunas relacionadas a motivo/cenário/tratamento.
- G4 usa responsável; se vazio, mostra "Sem preenchimento no analítico".
- Evita usar FAIXA_LOG e NM_CIDADE dentro da seção MOTIVOS E RESPONSÁVEIS.

Arquivos alterados:
- areas/adm/desconexao/dash_log.py
- areas/adm/desconexao/templates/dash_log.html

Não mexe em:
- dash_retirada
- Hub
- base.html
- outros dashboards
"""

from pathlib import Path
from datetime import datetime
import shutil
import re
import sys

ROOT_FIXO = Path(r"C:\Users\n5996917\OneDrive - Claro SA\INTRANET\OPERACOES_RNO")
ROOT = ROOT_FIXO if ROOT_FIXO.exists() else Path.cwd()

PY_FILE = ROOT / "areas" / "adm" / "desconexao" / "dash_log.py"
HTML_FILE = ROOT / "areas" / "adm" / "desconexao" / "templates" / "dash_log.html"
REPORT_FILE = ROOT / "relatorio_corrigir_dash_log_motivos_responsaveis_v3.txt"

AGORA = datetime.now().strftime("%Y%m%d_%H%M%S")


def backup(path: Path):
    if path.exists():
        bkp = path.with_suffix(path.suffix + f".bak_motivos_resp_v3_{AGORA}")
        shutil.copy2(path, bkp)
        return bkp
    return None


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str):
    path.write_text(text, encoding="utf-8", newline="\n")


def replace_js_function(text: str, function_name: str, new_function: str):
    """
    Substitui uma função JavaScript inteira usando contagem de chaves.
    """
    start = text.find("function " + function_name)

    if start < 0:
        return text, False

    brace_start = text.find("{", start)
    if brace_start < 0:
        return text, False

    depth = 0
    end = None
    in_string = None
    escape = False

    for i in range(brace_start, len(text)):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_string:
                in_string = None
            continue

        if ch in ("'", '"', "`"):
            in_string = ch
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end is None:
        return text, False

    return text[:start] + new_function.strip() + text[end:], True


COUNT_COL_FALLBACK_V3 = r'''
def count_col_fallback(df, candidatos, top=12, empty_title="Sem preenchimento no analítico"):
    """
    Tenta montar um gráfico usando a primeira coluna candidata com dados reais.

    Importante:
    - Esta função NÃO deve receber colunas genéricas como FAIXA_LOG ou NM_CIDADE
      quando estiver alimentando a seção MOTIVOS E RESPONSÁVEIS.
    - Se nenhuma coluna candidata tiver dados, retorna uma barra cinza informativa,
      em vez de duplicar gráficos de outras seções.

    Retorno:
    {
      "title": "...",
      "source_col": "...",
      "labels": [...],
      "values": [...],
      "is_fallback_empty": true/false
    }
    """
    valores_invalidos = {
        "",
        "nan",
        "none",
        "null",
        "na",
        "n/a",
        "não informado",
        "nao informado",
        "sem informação",
        "sem informacao",
        "sem dados",
        "sem analitico",
        "sem analítico",
    }

    for col, titulo in candidatos:
        if df is None or df.empty or col not in df.columns:
            continue

        s = df[col].fillna("").astype(str).str.strip()
        s_valid = s[~s.str.lower().isin(valores_invalidos)]

        if s_valid.empty:
            continue

        vc = s_valid.value_counts().head(top)

        labels = vc.index.astype(str).tolist()
        values = [int(x) for x in vc.values.tolist()]

        if labels and values:
            return {
                "title": titulo,
                "source_col": col,
                "labels": labels,
                "values": values,
                "is_fallback_empty": False,
            }

    total = int(len(df)) if df is not None else 0

    return {
        "title": empty_title,
        "source_col": "",
        "labels": ["Sem preenchimento no analítico"],
        "values": [total],
        "is_fallback_empty": True,
    }
'''


MONTAR_CHARTS_V3 = r'''
def montar_charts(df):
    return {
        "g1_faixa_log": count_col(
            df,
            "FAIXA_LOG",
            keep_order=ORDEM_FAIXA_LOG,
        ),
        "g2_com_sem_log": chart_com_sem_log(df),

        # G3 — Motivos/Cenários/Tratamento.
        # Não usar FAIXA_LOG aqui para não duplicar a seção Distribuição do LOG.
        "g3_motivos": count_col_fallback(
            df,
            [
                ("ANL_MOTIVO_REAGENDA", "Motivos de Reagenda"),
                ("ANL_QUEBRA_CENARIO", "Cenários de Quebra"),
                ("ANL_TIPO_TRATAMENTO", "Tipos de Tratamento"),
                ("LOG_ULT_TIPO_OS", "Último Tipo de OS LOG"),
            ],
            top=12,
            empty_title="Motivos — sem preenchimento no analítico",
        ),

        # G4 — Responsáveis.
        # Não usar NM_CIDADE aqui para não duplicar a seção de Cidades.
        "g4_responsaveis": count_col_fallback(
            df,
            [
                ("ANL_QUEBRA_RESPONSAVEL", "Responsáveis pela Quebra"),
            ],
            top=12,
            empty_title="Responsáveis — sem preenchimento no analítico",
        ),

        "g5_tipo_log": chart_tipo_log(df),
        "g6_cidades_log": chart_cidades_com_log(df, top=15),
    }
'''


RENDER_CHARTS_V3 = r'''
function renderCharts(charts) {
    charts = charts || {};

    barVertical("g1", charts.g1_faixa_log, "Distribuição por Faixa LOG", CORES_LOG);
    donut("g2", charts.g2_com_sem_log, "Com LOG x Sem LOG", CORES_STATUS);

    const g3Empty = charts.g3_motivos && charts.g3_motivos.is_fallback_empty;
    const g4Empty = charts.g4_responsaveis && charts.g4_responsaveis.is_fallback_empty;

    hbar(
      "g3",
      charts.g3_motivos,
      (charts.g3_motivos && charts.g3_motivos.title) ? charts.g3_motivos.title : "Motivos de Reagenda",
      g3Empty ? "#9E9E9E" : "#F57C00"
    );

    hbar(
      "g4",
      charts.g4_responsaveis,
      (charts.g4_responsaveis && charts.g4_responsaveis.title) ? charts.g4_responsaveis.title : "Responsáveis pela Quebra",
      g4Empty ? "#9E9E9E" : "#E60000"
    );

    stackedTipo("g5", charts.g5_tipo_log, "LOG por Tipo de Desconexão");
    hbar("g6", charts.g6_cidades_log, "Cidades com Maior Volume de LOG", "#E60000");

    setTimeout(resizeCharts, 120);
  }
'''


def patch_python(py: str):
    original = py
    alteracoes = []

    # 1) Remove count_col_fallback existente, se houver.
    if "def count_col_fallback" in py:
        py_new = re.sub(
            r"\ndef count_col_fallback\(df, candidatos, top=12.*?(?=\n\ndef montar_charts\(df\):)",
            "\n",
            py,
            flags=re.S,
        )

        if py_new != py:
            py = py_new
            alteracoes.append("count_col_fallback antigo removido")

    # 2) Insere count_col_fallback V3 antes de montar_charts.
    if "def count_col_fallback" not in py:
        marker = "def montar_charts(df):"
        if marker in py:
            py = py.replace(marker, COUNT_COL_FALLBACK_V3.strip() + "\n\n" + marker, 1)
            alteracoes.append("count_col_fallback V3 inserido")
        else:
            alteracoes.append("FALHA: não encontrei def montar_charts(df) para inserir fallback V3")

    # 3) Substitui montar_charts inteira.
    pattern = r"def montar_charts\(df\):.*?(?=\n\n@bp\.route\()"
    if re.search(pattern, py, flags=re.S):
        py = re.sub(pattern, MONTAR_CHARTS_V3.strip() + "\n", py, count=1, flags=re.S)
        alteracoes.append("montar_charts substituída por versão V3")
    else:
        alteracoes.append("FALHA: não consegui substituir montar_charts por regex")

    return py, alteracoes, py != original


def patch_html(html: str):
    original = html
    alteracoes = []

    html, ok = replace_js_function(html, "renderCharts", RENDER_CHARTS_V3)

    if ok:
        alteracoes.append("renderCharts substituída por versão V3")
    else:
        alteracoes.append("FALHA: não encontrei function renderCharts no HTML")

    return html, alteracoes, html != original


def validar():
    py = read_text(PY_FILE) if PY_FILE.exists() else ""
    html = read_text(HTML_FILE) if HTML_FILE.exists() else ""

    checks = [
        ("dash_log.py existe", PY_FILE.exists()),
        ("dash_log.html existe", HTML_FILE.exists()),
        ("count_col_fallback V3 presente", "is_fallback_empty" in py and "valores_invalidos" in py),
        ("G3 não usa FAIXA_LOG como fallback", '"FAIXA_LOG", "Distribuição por Faixa LOG"' not in py),
        ("G4 não usa NM_CIDADE como fallback", '"NM_CIDADE", "Cidades com Maior Volume"' not in py and '"NM_CIDADE", "Cidades com maior volume"' not in py),
        ("G3 usa ANL_MOTIVO_REAGENDA", "ANL_MOTIVO_REAGENDA" in py),
        ("G3 usa ANL_QUEBRA_CENARIO", "ANL_QUEBRA_CENARIO" in py),
        ("G4 usa ANL_QUEBRA_RESPONSAVEL", "ANL_QUEBRA_RESPONSAVEL" in py),
        ("HTML usa is_fallback_empty", "is_fallback_empty" in html),
        ("HTML renderCharts V3 presente", "const g3Empty" in html and "const g4Empty" in html),
    ]

    return checks


def main():
    linhas = []
    linhas.append("# RELATÓRIO — CORRIGIR DASH_LOG MOTIVOS E RESPONSÁVEIS V3")
    linhas.append(f"ROOT: {ROOT}")
    linhas.append(f"PY_FILE: {PY_FILE}")
    linhas.append(f"HTML_FILE: {HTML_FILE}")
    linhas.append("")

    if not ROOT.exists():
        print("ERRO: raiz do projeto não encontrada.")
        print(ROOT)
        sys.exit(1)

    if not PY_FILE.exists():
        print("ERRO: dash_log.py não encontrado.")
        print(PY_FILE)
        sys.exit(1)

    if not HTML_FILE.exists():
        print("ERRO: dash_log.html não encontrado.")
        print(HTML_FILE)
        sys.exit(1)

    py_bkp = backup(PY_FILE)
    html_bkp = backup(HTML_FILE)

    py_original = read_text(PY_FILE)
    html_original = read_text(HTML_FILE)

    py_final, alt_py, changed_py = patch_python(py_original)
    html_final, alt_html, changed_html = patch_html(html_original)

    if changed_py:
        write_text(PY_FILE, py_final)

    if changed_html:
        write_text(HTML_FILE, html_final)

    linhas.append("BACKUPS:")
    linhas.append(f"- PY backup: {py_bkp}")
    linhas.append(f"- HTML backup: {html_bkp}")
    linhas.append("")

    linhas.append("ALTERAÇÕES PYTHON:")
    for a in alt_py:
        linhas.append(f"- {a}")

    linhas.append("")
    linhas.append("ALTERAÇÕES HTML:")
    for a in alt_html:
        linhas.append(f"- {a}")

    linhas.append("")
    linhas.append("VALIDAÇÕES:")
    for nome, ok in validar():
        linhas.append(f"- {'OK' if ok else 'FALHA'} | {nome}")

    linhas.append("")
    linhas.append("TESTE:")
    linhas.append("1) Pare o Flask com CTRL+C.")
    linhas.append("2) Rode: python run.py")
    linhas.append("3) Abra: http://localhost:5000/dash/log/")
    linhas.append("4) Pressione Ctrl+F5.")
    linhas.append("5) Teste direto: http://localhost:5000/dash/log/api/data")
    linhas.append("")
    linhas.append("RESULTADO ESPERADO:")
    linhas.append("- G3 não deve mais cair em Distribuição por Faixa LOG.")
    linhas.append("- G4 não deve mais cair em Cidades com Maior Volume.")
    linhas.append("- Se as colunas analíticas estiverem vazias, aparece barra cinza indicando sem preenchimento.")
    linhas.append("- Se houver dados em ANL_MOTIVO_REAGENDA, ANL_QUEBRA_CENARIO, ANL_TIPO_TRATAMENTO ou LOG_ULT_TIPO_OS, G3 usa esses dados.")
    linhas.append("- Se houver dados em ANL_QUEBRA_RESPONSAVEL, G4 usa esses dados.")

    write_text(REPORT_FILE, "\n".join(linhas))

    print("\n".join(linhas))
    print("\n✅ Correção V3 aplicada: fallback conceitual ajustado.")


if __name__ == "__main__":
    main()