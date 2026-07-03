# -*- coding: utf-8 -*-
"""
VALIDADOR AUTOMÁTICO — DASH_LOG

Objetivo:
- Validar o dashboard /dash/log/
- Validar APIs:
  - /dash/log/api/options
  - /dash/log/api/data
- Validar estrutura dos arquivos:
  - areas/adm/desconexao/dash_log.py
  - areas/adm/desconexao/templates/dash_log.html
- Gerar relatório resumido em TXT.

Uso:
1) Abra um terminal e rode o Flask:
   python run.py

2) Em outro terminal, na raiz OPERACOES_RNO, rode:
   python validar_dash_log.py

Saída:
- relatorio_validacao_dash_log.txt
"""

from pathlib import Path
from datetime import datetime
import json
import sys
import traceback
import urllib.request
import urllib.error


ROOT_FIXO = Path(r"C:\Users\n5996917\OneDrive - Claro SA\INTRANET\OPERACOES_RNO")
ROOT = ROOT_FIXO if ROOT_FIXO.exists() else Path.cwd()

BASE_URL = "http://localhost:5000"

URL_PAGE = BASE_URL + "/dash/log/"
URL_OPTIONS = BASE_URL + "/dash/log/api/options"
URL_DATA = BASE_URL + "/dash/log/api/data"

PY_FILE = ROOT / "areas" / "adm" / "desconexao" / "dash_log.py"
HTML_FILE = ROOT / "areas" / "adm" / "desconexao" / "templates" / "dash_log.html"
REPORT_FILE = ROOT / "relatorio_validacao_dash_log.txt"

AGORA = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def http_get(url, timeout=20):
    """
    Faz GET simples sem depender de requests.
    Retorna:
    {
      ok,
      status,
      content_type,
      text,
      json,
      error
    }
    """
    result = {
        "ok": False,
        "status": None,
        "content_type": "",
        "text": "",
        "json": None,
        "error": "",
    }

    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
                "User-Agent": "ValidadorDashLog/1.0",
            },
            method="GET",
        )

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")

            result["ok"] = 200 <= status < 300
            result["status"] = status
            result["content_type"] = content_type
            result["text"] = text

            if "application/json" in content_type.lower():
                try:
                    result["json"] = json.loads(text)
                except Exception as e:
                    result["error"] = "Falha ao converter resposta JSON: " + str(e)

    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""

        result["ok"] = False
        result["status"] = e.code
        result["content_type"] = e.headers.get("Content-Type", "") if e.headers else ""
        result["text"] = body
        result["error"] = "HTTPError: " + str(e)

    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)

    return result


def status_txt(ok):
    return "OK" if ok else "FALHA"


def check(condition, description, details=""):
    return {
        "ok": bool(condition),
        "description": description,
        "details": details,
    }


def safe_get(dct, path, default=None):
    cur = dct
    for key in path:
        if not isinstance(cur, dict):
            return default
        if key not in cur:
            return default
        cur = cur[key]
    return cur


def validar_arquivos():
    py = read_text(PY_FILE)
    html = read_text(HTML_FILE)

    checks = []

    checks.append(check(PY_FILE.exists(), "Arquivo dash_log.py existe", str(PY_FILE)))
    checks.append(check(HTML_FILE.exists(), "Arquivo dash_log.html existe", str(HTML_FILE)))

    checks.append(check('url_prefix="/dash/log"' in py or "url_prefix='/dash/log'" in py,
                        "Blueprint possui url_prefix /dash/log"))

    checks.append(check('@bp.route("/")' in py,
                        "Rota principal / declarada no dash_log.py"))

    checks.append(check('@bp.route("/api/options")' in py,
                        "Rota /api/options declarada no dash_log.py"))

    checks.append(check('@bp.route("/api/data")' in py,
                        "Rota /api/data declarada no dash_log.py"))

    checks.append(check('"charts": montar_charts' in py or "'charts': montar_charts" in py,
                        "API /api/data retorna charts via montar_charts"))

    checks.append(check('"kpis": montar_kpis' in py or "'kpis': montar_kpis" in py,
                        "API /api/data retorna kpis via montar_kpis"))

    checks.append(check("def count_col_fallback" in py,
                        "count_col_fallback presente no backend"))

    checks.append(check("is_fallback_empty" in py,
                        "Controle is_fallback_empty presente no backend"))

    checks.append(check('"FAIXA_LOG", "Distribuição por Faixa LOG"' not in py,
                        "G3 não usa FAIXA_LOG como fallback indevido"))

    checks.append(check('"NM_CIDADE", "Cidades com Maior Volume"' not in py and '"NM_CIDADE", "Cidades com maior volume"' not in py,
                        "G4 não usa NM_CIDADE como fallback indevido"))

    checks.append(check("plotly-2.35.2.min.js" in html,
                        "HTML usa Plotly.js 2.35.2"))

    checks.append(check("choices.min.js" in html and "choices.min.css" in html,
                        "HTML possui Choices.js CSS e JS"))

    checks.append(check("/area/adm/desconexao/" in html,
                        "Botão Voltar aponta para /area/adm/desconexao/"))

    checks.append(check("charts.g1_faixa_log" in html,
                        "Frontend renderiza charts.g1_faixa_log"))

    checks.append(check("charts.g2_com_sem_log" in html,
                        "Frontend renderiza charts.g2_com_sem_log"))

    checks.append(check("charts.g3_motivos" in html,
                        "Frontend renderiza charts.g3_motivos"))

    checks.append(check("charts.g4_responsaveis" in html,
                        "Frontend renderiza charts.g4_responsaveis"))

    checks.append(check("charts.g5_tipo_log" in html,
                        "Frontend renderiza charts.g5_tipo_log"))

    checks.append(check("charts.g6_cidades_log" in html,
                        "Frontend renderiza charts.g6_cidades_log"))

    checks.append(check("is_fallback_empty" in html,
                        "Frontend trata is_fallback_empty"))

    return checks


def validar_http_page(page_result):
    checks = []

    checks.append(check(page_result["ok"], "Página /dash/log/ responde HTTP 2xx",
                        "status=" + str(page_result["status"])))

    checks.append(check("text/html" in page_result["content_type"].lower(),
                        "Página /dash/log/ retorna HTML",
                        page_result["content_type"]))

    text = page_result.get("text") or ""

    checks.append(check("LOG" in text.upper(),
                        "HTML da página contém referência a LOG"))

    checks.append(check("/dash/log/api/data" in text,
                        "HTML contém chamada para /dash/log/api/data"))

    checks.append(check("/dash/log/api/options" in text,
                        "HTML contém chamada para /dash/log/api/options"))

    return checks


def validar_options(options_result):
    checks = []

    checks.append(check(options_result["ok"], "API /dash/log/api/options responde HTTP 2xx",
                        "status=" + str(options_result["status"])))

    checks.append(check("application/json" in options_result["content_type"].lower(),
                        "API /api/options retorna application/json",
                        options_result["content_type"]))

    data = options_result.get("json")

    checks.append(check(isinstance(data, dict),
                        "JSON de /api/options é objeto/dicionário"))

    if isinstance(data, dict):
        for key in ["SAFRA", "DS_TIPO_DESCONEXAO", "NM_CIDADE", "PENDENCIA"]:
            checks.append(check(key in data,
                                f"Options contém filtro {key}"))
            checks.append(check(isinstance(data.get(key), list),
                                f"Options {key} é lista"))

    return checks


def validar_data(data_result):
    checks = []
    data = data_result.get("json")

    checks.append(check(data_result["ok"], "API /dash/log/api/data responde HTTP 2xx",
                        "status=" + str(data_result["status"])))

    checks.append(check("application/json" in data_result["content_type"].lower(),
                        "API /api/data retorna application/json",
                        data_result["content_type"]))

    checks.append(check(isinstance(data, dict),
                        "JSON de /api/data é objeto/dicionário"))

    if not isinstance(data, dict):
        return checks

    checks.append(check(data.get("ok") is True,
                        "Payload possui ok=true",
                        "ok=" + str(data.get("ok"))))

    checks.append(check("kpis" in data and isinstance(data.get("kpis"), dict),
                        "Payload possui kpis"))

    checks.append(check("charts" in data and isinstance(data.get("charts"), dict),
                        "Payload possui charts"))

    kpis = data.get("kpis") or {}
    charts = data.get("charts") or {}

    for key in ["total", "com_log", "sem_log", "criticos", "pct_log"]:
        checks.append(check(key in kpis,
                            f"KPI presente: {key}",
                            str(kpis.get(key))))

    total = kpis.get("total")
    com_log = kpis.get("com_log")
    sem_log = kpis.get("sem_log")
    criticos = kpis.get("criticos")

    checks.append(check(isinstance(total, int) and total >= 0,
                        "KPI total é inteiro >= 0",
                        str(total)))

    checks.append(check(isinstance(com_log, int) and com_log >= 0,
                        "KPI com_log é inteiro >= 0",
                        str(com_log)))

    checks.append(check(isinstance(sem_log, int) and sem_log >= 0,
                        "KPI sem_log é inteiro >= 0",
                        str(sem_log)))

    checks.append(check(isinstance(criticos, int) and criticos >= 0,
                        "KPI criticos é inteiro >= 0",
                        str(criticos)))

    if isinstance(total, int) and isinstance(com_log, int) and isinstance(sem_log, int):
        checks.append(check(com_log + sem_log <= total,
                            "Validação lógica: com_log + sem_log <= total",
                            f"com_log={com_log}, sem_log={sem_log}, total={total}"))

    expected_charts = [
        "g1_faixa_log",
        "g2_com_sem_log",
        "g3_motivos",
        "g4_responsaveis",
        "g5_tipo_log",
        "g6_cidades_log",
    ]

    for key in expected_charts:
        checks.append(check(key in charts,
                            f"Chart presente: {key}"))

    # G1
    g1 = charts.get("g1_faixa_log") or {}
    checks.append(check(isinstance(g1.get("labels"), list),
                        "G1 labels é lista"))
    checks.append(check(isinstance(g1.get("values"), list),
                        "G1 values é lista"))

    # G2
    g2 = charts.get("g2_com_sem_log") or {}
    checks.append(check(isinstance(g2.get("labels"), list),
                        "G2 labels é lista"))
    checks.append(check(isinstance(g2.get("values"), list),
                        "G2 values é lista"))

    # G3
    g3 = charts.get("g3_motivos") or {}
    checks.append(check(isinstance(g3.get("labels"), list),
                        "G3 labels é lista"))
    checks.append(check(isinstance(g3.get("values"), list),
                        "G3 values é lista"))
    checks.append(check("title" in g3,
                        "G3 possui title",
                        str(g3.get("title"))))
    checks.append(check("source_col" in g3,
                        "G3 possui source_col",
                        str(g3.get("source_col"))))
    checks.append(check("is_fallback_empty" in g3,
                        "G3 possui is_fallback_empty",
                        str(g3.get("is_fallback_empty"))))

    g3_source = g3.get("source_col")
    checks.append(check(g3_source != "FAIXA_LOG",
                        "G3 não caiu em FAIXA_LOG",
                        str(g3_source)))

    # G4
    g4 = charts.get("g4_responsaveis") or {}
    checks.append(check(isinstance(g4.get("labels"), list),
                        "G4 labels é lista"))
    checks.append(check(isinstance(g4.get("values"), list),
                        "G4 values é lista"))
    checks.append(check("title" in g4,
                        "G4 possui title",
                        str(g4.get("title"))))
    checks.append(check("source_col" in g4,
                        "G4 possui source_col",
                        str(g4.get("source_col"))))
    checks.append(check("is_fallback_empty" in g4,
                        "G4 possui is_fallback_empty",
                        str(g4.get("is_fallback_empty"))))

    g4_source = g4.get("source_col")
    checks.append(check(g4_source != "NM_CIDADE",
                        "G4 não caiu em NM_CIDADE",
                        str(g4_source)))

    # G5
    g5 = charts.get("g5_tipo_log") or {}
    checks.append(check(isinstance(g5.get("labels"), list),
                        "G5 labels é lista"))
    checks.append(check(isinstance(g5.get("series"), dict),
                        "G5 series é dicionário"))

    # G6
    g6 = charts.get("g6_cidades_log") or {}
    checks.append(check(isinstance(g6.get("labels"), list),
                        "G6 labels é lista"))
    checks.append(check(isinstance(g6.get("values"), list),
                        "G6 values é lista"))

    # Linhas
    checks.append(check("total_linhas_cache" in data,
                        "Payload possui total_linhas_cache",
                        str(data.get("total_linhas_cache"))))

    checks.append(check("total_linhas_filtrado" in data,
                        "Payload possui total_linhas_filtrado",
                        str(data.get("total_linhas_filtrado"))))

    return checks


def format_checks(title, checks):
    lines = []
    lines.append("")
    lines.append("## " + title)

    ok_count = sum(1 for c in checks if c["ok"])
    total = len(checks)

    lines.append(f"Resultado: {ok_count}/{total} OK")
    lines.append("")

    for c in checks:
        line = f"- {status_txt(c['ok'])} | {c['description']}"
        if c.get("details"):
            line += f" | {c['details']}"
        lines.append(line)

    return lines


def gerar_resumo_api(data_result):
    data = data_result.get("json")

    lines = []
    lines.append("")
    lines.append("## RESUMO DA API /dash/log/api/data")

    if not isinstance(data, dict):
        lines.append("- API não retornou JSON válido.")
        return lines

    kpis = data.get("kpis") or {}
    charts = data.get("charts") or {}

    lines.append(f"- ok: {data.get('ok')}")
    lines.append(f"- total_linhas_cache: {data.get('total_linhas_cache')}")
    lines.append(f"- total_linhas_filtrado: {data.get('total_linhas_filtrado')}")
    lines.append("")
    lines.append("### KPIs")
    lines.append(f"- total: {kpis.get('total')}")
    lines.append(f"- com_log: {kpis.get('com_log')}")
    lines.append(f"- sem_log: {kpis.get('sem_log')}")
    lines.append(f"- criticos: {kpis.get('criticos')}")
    lines.append(f"- pct_log: {kpis.get('pct_log')}%")

    lines.append("")
    lines.append("### G3 — Motivos")
    g3 = charts.get("g3_motivos") or {}
    lines.append(f"- title: {g3.get('title')}")
    lines.append(f"- source_col: {g3.get('source_col')}")
    lines.append(f"- is_fallback_empty: {g3.get('is_fallback_empty')}")
    lines.append(f"- qtd_labels: {len(g3.get('labels') or [])}")

    labels_g3 = g3.get("labels") or []
    values_g3 = g3.get("values") or []

    for i, label in enumerate(labels_g3[:5]):
        value = values_g3[i] if i < len(values_g3) else ""
        lines.append(f"  - {label}: {value}")

    lines.append("")
    lines.append("### G4 — Responsáveis")
    g4 = charts.get("g4_responsaveis") or {}
    lines.append(f"- title: {g4.get('title')}")
    lines.append(f"- source_col: {g4.get('source_col')}")
    lines.append(f"- is_fallback_empty: {g4.get('is_fallback_empty')}")
    lines.append(f"- qtd_labels: {len(g4.get('labels') or [])}")

    labels_g4 = g4.get("labels") or []
    values_g4 = g4.get("values") or []

    for i, label in enumerate(labels_g4[:5]):
        value = values_g4[i] if i < len(values_g4) else ""
        lines.append(f"  - {label}: {value}")

    return lines


def main():
    report = []
    report.append("# RELATÓRIO DE VALIDAÇÃO — DASH_LOG")
    report.append(f"Data/hora: {AGORA}")
    report.append(f"ROOT: {ROOT}")
    report.append(f"Página: {URL_PAGE}")
    report.append(f"API Options: {URL_OPTIONS}")
    report.append(f"API Data: {URL_DATA}")

    try:
        file_checks = validar_arquivos()

        page_result = http_get(URL_PAGE)
        options_result = http_get(URL_OPTIONS)
        data_result = http_get(URL_DATA)

        page_checks = validar_http_page(page_result)
        options_checks = validar_options(options_result)
        data_checks = validar_data(data_result)

        all_checks = file_checks + page_checks + options_checks + data_checks
        ok_total = sum(1 for c in all_checks if c["ok"])
        total = len(all_checks)

        report.append("")
        report.append("## STATUS GERAL")
        report.append(f"- Resultado geral: {ok_total}/{total} validações OK")

        if ok_total == total:
            report.append("- Status: APROVADO")
        else:
            report.append("- Status: ATENÇÃO — existem validações com FALHA")

        report.extend(format_checks("VALIDAÇÃO DOS ARQUIVOS", file_checks))
        report.extend(format_checks("VALIDAÇÃO DA PÁGINA /dash/log/", page_checks))
        report.extend(format_checks("VALIDAÇÃO DA API /api/options", options_checks))
        report.extend(format_checks("VALIDAÇÃO DA API /api/data", data_checks))
        report.extend(gerar_resumo_api(data_result))

        # Salva JSON bruto da API data para inspeção, se existir.
        if isinstance(data_result.get("json"), dict):
            json_file = ROOT / "validacao_dash_log_api_data.json"
            json_file.write_text(
                json.dumps(data_result["json"], ensure_ascii=False, indent=2),
                encoding="utf-8",
                newline="\n",
            )
            report.append("")
            report.append("## ARQUIVO JSON GERADO")
            report.append(f"- {json_file}")

    except Exception:
        report.append("")
        report.append("## ERRO INESPERADO")
        report.append(traceback.format_exc())

    REPORT_FILE.write_text("\n".join(report), encoding="utf-8", newline="\n")

    print("\n".join(report))
    print("")
    print("✅ Relatório gerado em:")
    print(REPORT_FILE)


if __name__ == "__main__":
    main()