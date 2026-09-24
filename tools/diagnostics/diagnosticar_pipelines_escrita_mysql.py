# -*- coding: utf-8 -*-
"""
diagnosticar_pipelines_escrita_mysql.py
Portal Operacoes RNO - ADM / Desconexao

Diagnostico direcionado, somente leitura:
- ignora legacy, reports, dashboards, templates, static e ambientes virtuais;
- localiza scripts ativos que leem arquivos e/ou escrevem no MySQL;
- identifica tabelas, pastas, formatos, metodos de escrita e riscos historicos;
- consulta somente metadados do MySQL (SHOW TABLES / SHOW COLUMNS / contagens);
- nao executa INSERT, UPDATE, DELETE, TRUNCATE, DROP, ALTER ou CREATE;
- gera relatorios Markdown e JSON completos.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
import traceback
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_MARKERS = (Path("areas/adm/desconexao"), Path("data/db.py"))
ANALYTICS_ROOT = Path.home() / "OneDrive - Claro SA" / "OPERAÇÕES" / "ADM" / "DESCONEXAO" / "ANALITICOS"
DATASETS = ("SAFRA", "BACKLOG_OS", "QUEBRA", "QUEBRA_COMPLEMENTO", "TOA")

SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", "legacy", "reports", "static",
    "templates", "docs", "backups", "backup", "snapshots",
}
SKIP_FILES = {
    "inventariar_pipelines_desconexao.py",
    "diagnosticar_pipelines_escrita_mysql.py",
}
DASHBOARD_PREFIXES = ("dash_",)

FILE_READ_PATTERNS = {
    "READ_EXCEL": r"(?:pd\.)?read_excel\s*\(",
    "READ_CSV": r"(?:pd\.)?read_csv\s*\(",
    "READ_PARQUET": r"(?:pd\.)?read_parquet\s*\(",
    "READ_JSON": r"(?:pd\.)?read_json\s*\(",
    "OPENPYXL": r"openpyxl|load_workbook\s*\(",
    "GLOB": r"\.glob\s*\(|\.rglob\s*\(|glob\.glob\s*\(",
    "LISTDIR": r"os\.listdir\s*\(|os\.scandir\s*\(",
}
DB_WRITE_PATTERNS = {
    "TO_SQL": r"\.to_sql\s*\(",
    "INSERT": r"\bINSERT\s+INTO\b",
    "UPDATE": r"\bUPDATE\s+[`A-Za-z_]",
    "DELETE": r"\bDELETE\s+FROM\b",
    "TRUNCATE": r"\bTRUNCATE\s+(?:TABLE\s+)?",
    "DROP_TABLE": r"\bDROP\s+TABLE\b",
    "ALTER_TABLE": r"\bALTER\s+TABLE\b",
    "CREATE_TABLE": r"\bCREATE\s+TABLE\b",
    "EXECUTEMANY": r"\.executemany\s*\(",
    "EXECUTE": r"\.execute\s*\(",
}
DB_READ_PATTERNS = {
    "READ_SQL": r"(?:pd\.)?read_sql(?:_query|_table)?\s*\(",
    "SELECT": r"\bSELECT\b",
    "LOAD_TABLE": r"load_table\s*\(",
}
RISK_PATTERNS = {
    "TRUNCATE": r"\bTRUNCATE\s+(?:TABLE\s+)?",
    "DROP_TABLE": r"\bDROP\s+TABLE\b",
    "IF_EXISTS_REPLACE": r"if_exists\s*=\s*['\"]replace['\"]",
    "TO_SQL_REPLACE": r"to_sql\s*\([\s\S]{0,500}?if_exists\s*=\s*['\"]replace['\"]",
    "DELETE_SEM_FILTRO_COMPETENCIA": r"\bDELETE\s+FROM\s+[`A-Za-z_][`A-Za-z0-9_.]*\s*(?:;|['\"]|$)",
}
HISTORY_PATTERNS = {
    "competencia": r"COMPET[ÊE]NCIA",
    "ano_competencia": r"ANO_COMPETENCIA",
    "mes_competencia": r"MES_COMPETENCIA",
    "id_carga": r"ID_CARGA",
    "data_carga": r"DATA_CARGA",
    "arquivo_origem": r"ARQUIVO_ORIGEM",
    "hash_arquivo": r"HASH_ARQUIVO|SHA256",
    "controle_cargas": r"CONTROLE_CARGAS",
    "transaction": r"\bBEGIN\b|\bCOMMIT\b|\bROLLBACK\b|engine\.begin\s*\(|connection\.begin\s*\(",
}
DATASET_PATTERNS = {
    "QUEBRA_COMPLEMENTO": (r"quebra[_\s-]*complemento", r"complemento[_\s-]*quebra"),
    "BACKLOG_OS": (r"backlog[_\s-]*os", r"bkl_", r"backlog"),
    "QUEBRA": (r"quebra[_\s-]*total", r"\bquebra\b", r"dt_agenda"),
    "TOA": (r"\btoa\b", r"toa_"),
    "SAFRA": (r"safra_final", r"safra_enriquecida", r"\bsafra\b"),
}
TABLE_PATTERNS = (
    r"(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+`?([A-Za-z_][A-Za-z0-9_]*)`?",
    r"to_sql\s*\(\s*['\"]([^'\"]+)['\"]",
    r"load_table\s*\(\s*['\"]([^'\"]+)['\"]",
    r"read_sql_table\s*\(\s*['\"]([^'\"]+)['\"]",
)
PATH_RE = re.compile(r"[A-Za-z]:\\[^\r\n'\"]+", re.I)
EXT_RE = re.compile(r"\.(xlsx|xls|xlsb|csv|parquet|json)\b", re.I)


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def discover_root() -> Path:
    offered = []
    env_root = os.environ.get("OPERACOES_RNO_ROOT", "").strip()
    if env_root:
        offered.append(Path(env_root))
    offered.extend([
        Path.cwd(),
        Path.home() / "OneDrive - Claro SA" / "INTRANET" / "OPERACOES_RNO",
        Path.home() / "OneDrive - Claro SA" / "OPERACOES_RNO",
    ])
    for candidate in offered:
        candidate = candidate.expanduser().resolve()
        if all((candidate / marker).exists() for marker in PROJECT_MARKERS):
            return candidate
    raise FileNotFoundError("Raiz OPERACOES_RNO nao localizada. Execute o script na raiz do projeto.")


def read_text(path: Path) -> tuple[str, str]:
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc), enc
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace"), "utf-8-replace"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def excluded(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if path.name in SKIP_FILES:
        return True
    if any(part.lower() in SKIP_DIRS for part in rel.parts[:-1]):
        return True
    if path.name.lower().startswith(DASHBOARD_PREFIXES):
        return True
    return False


def matches(patterns: dict[str, str], text: str) -> list[str]:
    return sorted(name for name, pat in patterns.items() if re.search(pat, text, re.I | re.S))


def datasets_for(text: str, filename: str) -> list[str]:
    hay = filename + "\n" + text
    return sorted({name for name, pats in DATASET_PATTERNS.items() if any(re.search(p, hay, re.I) for p in pats)})


def tables_for(text: str) -> list[str]:
    values = set()
    for pattern in TABLE_PATTERNS:
        values.update(re.findall(pattern, text, re.I))
    blacklist = {"if", "in", "for", "from", "data", "flask", "pathlib", "datetime", "sqlalchemy"}
    return sorted(v for v in values if v.lower() not in blacklist)


def syntax_info(text: str, path: Path) -> tuple[bool, str | None, list[str]]:
    try:
        tree = ast.parse(text, filename=str(path))
        funcs = sorted({n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))})
        return True, None, funcs
    except SyntaxError as exc:
        return False, f"linha {exc.lineno}: {exc.msg}", []


def classify(item: dict[str, Any]) -> str:
    if item["riscos"]:
        return "CRITICO_REVISAR"
    hist = item["historico"]
    if all(hist[k] for k in ("competencia", "id_carga", "arquivo_origem", "hash_arquivo", "controle_cargas", "transaction")):
        return "HISTORICO_ESTRUTURADO"
    if item["escritas_mysql"] and (hist["competencia"] or (hist["ano_competencia"] and hist["mes_competencia"])):
        return "ESCRITA_COM_COMPETENCIA_PARCIAL"
    if item["escritas_mysql"]:
        return "ESCRITA_SEM_CONTRATO_HISTORICO"
    if item["leituras_arquivo"] and item["leituras_mysql"]:
        return "TRANSFORMADOR_SEM_ESCRITA_DETECTADA"
    if item["leituras_arquivo"]:
        return "LEITOR_DE_ARQUIVO"
    return "NAO_CLASSIFICADO"


def inspect_script(path: Path, root: Path) -> dict[str, Any]:
    text, encoding = read_text(path)
    ok, err, funcs = syntax_info(text, path)
    histories = {key: bool(re.search(pattern, text, re.I)) for key, pattern in HISTORY_PATTERNS.items()}
    item = {
        "arquivo": str(path.relative_to(root)),
        "sha256": sha256(path),
        "encoding": encoding,
        "tamanho_bytes": path.stat().st_size,
        "sintaxe_ok": ok,
        "erro_sintaxe": err,
        "funcoes": funcs,
        "datasets": datasets_for(text, path.name),
        "leituras_arquivo": matches(FILE_READ_PATTERNS, text),
        "leituras_mysql": matches(DB_READ_PATTERNS, text),
        "escritas_mysql": matches(DB_WRITE_PATTERNS, text),
        "riscos": matches(RISK_PATTERNS, text),
        "historico": histories,
        "tabelas": tables_for(text),
        "caminhos_fixos": sorted(set(PATH_RE.findall(text))),
        "formatos": sorted({m.lower() for m in EXT_RE.findall(text)}),
    }
    item["status"] = classify(item)
    return item


def scan(root: Path) -> list[dict[str, Any]]:
    result = []
    for path in root.rglob("*.py"):
        if excluded(path, root):
            continue
        item = inspect_script(path, root)
        relevant = bool(item["leituras_arquivo"] or item["escritas_mysql"])
        if relevant:
            result.append(item)
    return sorted(result, key=lambda x: x["arquivo"].lower())


def mysql_metadata() -> dict[str, Any]:
    result: dict[str, Any] = {"consultado": False, "erro": None, "banco": None, "tabelas": {}}
    try:
        project_root = discover_root()
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from config import Config  # type: ignore
        from sqlalchemy import create_engine, inspect, text  # type: ignore

        engine = create_engine(Config.db_url(), pool_pre_ping=True)
        inspector = inspect(engine)
        result["consultado"] = True
        result["banco"] = str(engine.url).rsplit("@", 1)[-1]
        target_tokens = ("safra", "quebra", "backlog", "toa", "controle_cargas")
        names = [n for n in inspector.get_table_names() if any(t in n.lower() for t in target_tokens)]
        with engine.connect() as conn:
            for table in sorted(names):
                columns = [c["name"] for c in inspector.get_columns(table)]
                entry: dict[str, Any] = {
                    "colunas": columns,
                    "tem_competencia": any(c.upper() in {"COMPETENCIA", "ANO_COMPETENCIA", "MES_COMPETENCIA"} for c in columns),
                    "tem_auditoria": any(c.upper() in {"ID_CARGA", "DATA_CARGA", "ARQUIVO_ORIGEM", "HASH_ARQUIVO"} for c in columns),
                    "linhas": None,
                }
                try:
                    safe = table.replace("`", "``")
                    entry["linhas"] = int(conn.execute(text(f"SELECT COUNT(*) FROM `{safe}`")).scalar() or 0)
                except Exception as exc:
                    entry["erro_contagem"] = str(exc)
                result["tabelas"][table] = entry
        engine.dispose()
    except Exception as exc:
        result["erro"] = f"{type(exc).__name__}: {exc}"
    return result


def build_summary(root: Path, scripts: list[dict[str, Any]], db: dict[str, Any]) -> dict[str, Any]:
    status = Counter(i["status"] for i in scripts)
    risks = Counter(r for i in scripts for r in i["riscos"])
    datasets = defaultdict(list)
    for item in scripts:
        for ds in item["datasets"]:
            datasets[ds].append(item["arquivo"])
    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "modo": "DIAGNOSTICO_SOMENTE_LEITURA",
        "projeto": str(root),
        "raiz_analiticos": str(ANALYTICS_ROOT),
        "exclusoes": sorted(SKIP_DIRS),
        "scripts_relevantes": len(scripts),
        "status": dict(status),
        "riscos": dict(risks),
        "datasets": {d: datasets.get(d, []) for d in DATASETS},
        "scripts": scripts,
        "mysql": db,
    }


def to_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Diagnóstico direcionado dos pipelines de escrita MySQL",
        "",
        f"- Gerado em: `{data['gerado_em']}`",
        f"- Projeto: `{data['projeto']}`",
        f"- Analíticos: `{data['raiz_analiticos']}`",
        f"- Scripts realmente relevantes: **{data['scripts_relevantes']}**",
        "- Modo: **somente leitura**",
        "",
        "## Resumo por status",
        "",
    ]
    if data["status"]:
        lines.extend(f"- **{k}**: {v}" for k, v in sorted(data["status"].items()))
    else:
        lines.append("- Nenhum script ativo de leitura de arquivo ou escrita MySQL foi localizado.")
    lines.extend(["", "## Riscos", ""])
    if data["riscos"]:
        lines.extend(f"- **{k}**: {v}" for k, v in sorted(data["riscos"].items()))
    else:
        lines.append("- Nenhum padrão destrutivo reconhecido nos candidatos ativos.")
    lines.extend(["", "## Cobertura por dataset", ""])
    for ds in DATASETS:
        lines.append(f"### {ds}")
        files = data["datasets"].get(ds, [])
        lines.extend(f"- `{f}`" for f in files) if files else lines.append("- Nenhum pipeline ativo localizado.")
        lines.append("")
    lines.extend(["## Scripts ativos identificados", ""])
    for item in data["scripts"]:
        lines.extend([
            f"### `{item['arquivo']}`",
            f"- Status: **{item['status']}**",
            f"- Sintaxe: {'OK' if item['sintaxe_ok'] else item['erro_sintaxe']}",
            f"- Datasets: {', '.join(item['datasets']) or 'não classificado'}",
            f"- Leitura de arquivos: {', '.join(item['leituras_arquivo']) or 'não detectada'}",
            f"- Leitura MySQL: {', '.join(item['leituras_mysql']) or 'não detectada'}",
            f"- Escrita MySQL: {', '.join(item['escritas_mysql']) or 'não detectada'}",
            f"- Tabelas: {', '.join(item['tabelas']) or 'não identificadas estaticamente'}",
            f"- Formatos: {', '.join(item['formatos']) or 'não identificados'}",
            f"- Caminhos fixos: {', '.join(item['caminhos_fixos']) or 'nenhum'}",
            f"- Riscos: {', '.join(item['riscos']) or 'nenhum padrão reconhecido'}",
            f"- Contrato histórico: `{json.dumps(item['historico'], ensure_ascii=False)}`",
            "",
        ])
    lines.extend(["## Metadados MySQL", ""])
    mysql = data["mysql"]
    if not mysql["consultado"]:
        lines.append(f"- Metadados não consultados: `{mysql['erro']}`")
    else:
        lines.append(f"- Banco identificado: `{mysql['banco']}`")
        for table, meta in mysql["tabelas"].items():
            lines.extend([
                f"### `{table}`",
                f"- Linhas: {meta.get('linhas')}",
                f"- Competência persistida: {'SIM' if meta.get('tem_competencia') else 'NÃO'}",
                f"- Auditoria de carga: {'SIM' if meta.get('tem_auditoria') else 'NÃO'}",
                f"- Colunas: {', '.join(meta.get('colunas', []))}",
                "",
            ])
    lines.extend([
        "## Próxima decisão baseada neste diagnóstico",
        "",
        "O primeiro pipeline piloto deve ser escolhido entre os scripts ativos que:",
        "1. leem arquivo de origem;",
        "2. escrevem no MySQL;",
        "3. possuem tabela de destino identificada;",
        "4. podem ser adaptados para competência, transação e controle de cargas.",
        "",
        "Nenhuma tabela, pipeline ou dashboard foi alterado por este diagnóstico.",
    ])
    return "\n".join(lines)


def main() -> int:
    print("=" * 76)
    print("DIAGNOSTICO DIRECIONADO - PIPELINES DE ESCRITA MYSQL")
    print("Modo somente leitura | legacy e dashboards excluidos")
    print("=" * 76)
    try:
        root = discover_root()
        print(f"[OK] Projeto: {root}")
        scripts = scan(root)
        print(f"[OK] Scripts relevantes: {len(scripts)}")
        db = mysql_metadata()
        if db["consultado"]:
            print(f"[OK] Metadados MySQL consultados: {len(db['tabelas'])} tabela(s)")
        else:
            print(f"[ATENCAO] Metadados MySQL indisponiveis: {db['erro']}")
        summary = build_summary(root, scripts, db)
        out = root / "reports"
        out.mkdir(parents=True, exist_ok=True)
        suffix = stamp()
        targets = {
            out / f"diagnostico_pipelines_mysql_{suffix}.json": json.dumps(summary, ensure_ascii=False, indent=2),
            out / f"diagnostico_pipelines_mysql_{suffix}.md": to_markdown(summary),
            out / "diagnostico_pipelines_mysql_latest.json": json.dumps(summary, ensure_ascii=False, indent=2),
            out / "diagnostico_pipelines_mysql_latest.md": to_markdown(summary),
        }
        for path, content in targets.items():
            path.write_text(content, encoding="utf-8")
        print(f"[OK] Relatorio: {out / 'diagnostico_pipelines_mysql_latest.md'}")
        print(f"[OK] JSON: {out / 'diagnostico_pipelines_mysql_latest.json'}")
        if summary["riscos"]:
            print(f"[ATENCAO] Riscos ativos: {summary['riscos']}")
        print("[CONCLUIDO] Nenhuma tabela, pipeline ou dashboard foi alterado.")
        return 0
    except Exception as exc:
        print(f"[ERRO] {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
