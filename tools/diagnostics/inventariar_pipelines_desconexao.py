# -*- coding: utf-8 -*-
"""
inventariar_pipelines_desconexao.py
Portal Operacoes RNO - Fase 1: inventario somente leitura

Objetivo:
- localizar o projeto OPERACOES_RNO automaticamente;
- validar/criar apenas a estrutura de pastas aprovada para os analiticos;
- inventariar scripts Python relacionados a SAFRA, BACKLOG_OS, QUEBRA,
  QUEBRA_COMPLEMENTO e TOA;
- identificar caminhos, tabelas, operacoes SQL e riscos de perda de historico;
- gerar relatorios JSON e Markdown sem alterar pipelines ou banco.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

DATASETS = ("SAFRA", "BACKLOG_OS", "QUEBRA", "QUEBRA_COMPLEMENTO", "TOA")
ANALYTICS_ROOT = Path.home() / "OneDrive - Claro SA" / "OPERAÇÕES" / "ADM" / "DESCONEXAO" / "ANALITICOS"
REPORT_DIR_NAME = "reports"
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache", ".pytest_cache"}

DATASET_PATTERNS = {
    "SAFRA": (r"safra",),
    "BACKLOG_OS": (r"backlog[_\s-]*os", r"backlog"),
    "QUEBRA": (r"quebra", r"quebra[_\s-]*total"),
    "QUEBRA_COMPLEMENTO": (r"quebra[_\s-]*complemento", r"complemento[_\s-]*quebra"),
    "TOA": (r"\btoa\b", r"toa_"),
}

RISK_PATTERNS = {
    "TRUNCATE": r"\bTRUNCATE\b",
    "DROP_TABLE": r"\bDROP\s+TABLE\b",
    "DELETE_SEM_WHERE": r"\bDELETE\s+FROM\s+[`\w.]+\s*(?:;|$)",
    "TO_SQL_REPLACE": r"to_sql\s*\([^)]*if_exists\s*=\s*['\"]replace['\"]",
    "IF_EXISTS_REPLACE": r"if_exists\s*=\s*['\"]replace['\"]",
    "CREATE_OR_REPLACE": r"\bCREATE\s+OR\s+REPLACE\b",
}

SQL_PATTERNS = {
    "SELECT": r"\bSELECT\b",
    "INSERT": r"\bINSERT\s+INTO\b",
    "UPDATE": r"\bUPDATE\b",
    "DELETE": r"\bDELETE\s+FROM\b",
    "CREATE_TABLE": r"\bCREATE\s+TABLE\b",
    "ALTER_TABLE": r"\bALTER\s+TABLE\b",
    "TRUNCATE": r"\bTRUNCATE\b",
    "DROP_TABLE": r"\bDROP\s+TABLE\b",
    "TO_SQL": r"\.to_sql\s*\(",
    "READ_SQL": r"read_sql(?:_query|_table)?\s*\(",
}

TABLE_PATTERNS = [
    r"(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+`?([A-Za-z_][A-Za-z0-9_]*)`?",
    r"to_sql\s*\(\s*['\"]([^'\"]+)['\"]",
    r"load_table\s*\(\s*['\"]([^'\"]+)['\"]",
]

PATH_PATTERN = re.compile(r"[A-Za-z]:\\[^\r\n'\"]+", re.IGNORECASE)
DATE_COLUMNS = (
    "ANO", "MES", "MÊS", "DIA", "COMPETENCIA", "COMPETÊNCIA",
    "ANO_COMPETENCIA", "MES_COMPETENCIA", "MÊS/ANO AÇÃO", "DT_ACAO",
    "BKL_DATA_AGENDAMENTO", "DT_AGENDA", "TOA_ULT_DATA",
)


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text_safe(path: Path) -> tuple[str, str]:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding), encoding
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            return "", f"ERRO: {exc}"
    return "", "ERRO: encoding"


def discover_project_root() -> Path:
    explicit = os.environ.get("OPERACOES_RNO_ROOT", "").strip()
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend([
        Path.cwd(),
        Path.home() / "OneDrive - Claro SA" / "INTRANET" / "OPERACOES_RNO",
        Path.home() / "OneDrive - Claro SA" / "OPERACOES_RNO",
    ])
    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if (candidate / "areas" / "adm" / "desconexao").exists() and (candidate / "data" / "db.py").exists():
            return candidate
    one_drive = Path.home() / "OneDrive - Claro SA"
    if one_drive.exists():
        for hit in one_drive.rglob("dash_executivo.py"):
            if any(part in SKIP_DIRS for part in hit.parts):
                continue
            candidate = hit
            while candidate != candidate.parent:
                if (candidate / "areas" / "adm" / "desconexao").exists() and (candidate / "data" / "db.py").exists():
                    return candidate
                candidate = candidate.parent
    raise FileNotFoundError(
        "Projeto OPERACOES_RNO nao localizado. Execute na raiz do projeto ou defina OPERACOES_RNO_ROOT."
    )


def ensure_analytics_structure() -> list[str]:
    created = []
    for dataset in DATASETS:
        for stage in ("ENTRADA", "PROCESSADOS", "REJEITADOS"):
            path = ANALYTICS_ROOT / dataset / stage
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                created.append(str(path))
    for sibling in ("CONFIG", "LOGS", "BACKUPS"):
        path = ANALYTICS_ROOT.parent / sibling
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(str(path))
    return created


def classify_datasets(text: str, filename: str) -> list[str]:
    haystack = f"{filename}\n{text}".lower()
    found = []
    # Complemento antes de Quebra para reduzir falso positivo classificatorio.
    if any(re.search(p, haystack, re.I) for p in DATASET_PATTERNS["QUEBRA_COMPLEMENTO"]):
        found.append("QUEBRA_COMPLEMENTO")
    for dataset in ("SAFRA", "BACKLOG_OS", "TOA"):
        if any(re.search(p, haystack, re.I) for p in DATASET_PATTERNS[dataset]):
            found.append(dataset)
    if any(re.search(p, haystack, re.I) for p in DATASET_PATTERNS["QUEBRA"]):
        found.append("QUEBRA")
    return sorted(set(found))


def parse_python(path: Path, root: Path) -> dict[str, Any]:
    text, encoding = read_text_safe(path)
    rel = str(path.relative_to(root))
    syntax_ok = True
    syntax_error = None
    imports = []
    functions = []
    try:
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                else:
                    imports.append(node.module or "")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
    except SyntaxError as exc:
        syntax_ok = False
        syntax_error = f"linha {exc.lineno}: {exc.msg}"

    upper = text.upper()
    datasets = classify_datasets(text, path.name)
    sql_ops = [name for name, pattern in SQL_PATTERNS.items() if re.search(pattern, text, re.I | re.S)]
    risks = [name for name, pattern in RISK_PATTERNS.items() if re.search(pattern, text, re.I | re.S)]
    tables = set()
    for pattern in TABLE_PATTERNS:
        tables.update(re.findall(pattern, text, re.I))
    paths = sorted(set(PATH_PATTERN.findall(text)))
    date_fields = [column for column in DATE_COLUMNS if column.upper() in upper]
    historico_signals = {
        "competencia": bool(re.search(r"COMPET[ÊE]NCIA", text, re.I)),
        "ano": bool(re.search(r"['\"]?ANO(?:_COMPETENCIA)?['\"]?", text, re.I)),
        "mes": bool(re.search(r"['\"]?M[ÊE]S(?:_COMPETENCIA)?['\"]?|['\"]MES['\"]", text, re.I)),
        "id_carga": bool(re.search(r"ID_CARGA", text, re.I)),
        "arquivo_origem": bool(re.search(r"ARQUIVO_ORIGEM", text, re.I)),
        "hash_arquivo": bool(re.search(r"HASH_ARQUIVO|SHA256", text, re.I)),
        "controle_cargas": bool(re.search(r"CONTROLE_CARGAS", text, re.I)),
        "transaction": bool(re.search(r"BEGIN|COMMIT|ROLLBACK|engine\.begin|connection\.begin", text, re.I)),
    }
    is_candidate = bool(datasets or tables or sql_ops or paths or "pipeline" in path.name.lower() or "import" in path.name.lower())
    return {
        "arquivo": rel,
        "nome": path.name,
        "encoding": encoding,
        "tamanho_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "sintaxe_ok": syntax_ok,
        "erro_sintaxe": syntax_error,
        "datasets": datasets,
        "tabelas": sorted(tables),
        "operacoes": sorted(sql_ops),
        "riscos": sorted(risks),
        "caminhos_fixos": paths,
        "campos_temporais": sorted(set(date_fields)),
        "historico": historico_signals,
        "imports": sorted(set(i for i in imports if i)),
        "funcoes": sorted(set(functions)),
        "candidato": is_candidate,
    }


def scan_project(root: Path) -> list[dict[str, Any]]:
    records = []
    for path in root.rglob("*.py"):
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        records.append(parse_python(path, root))
    return sorted(records, key=lambda item: item["arquivo"].lower())


def status_pipeline(item: dict[str, Any]) -> str:
    h = item["historico"]
    if item["riscos"]:
        return "CRITICO_REVISAR"
    required = (h["competencia"] and h["id_carga"] and h["arquivo_origem"] and h["controle_cargas"])
    if required:
        return "HISTORICO_ESTRUTURADO"
    if h["ano"] and h["mes"]:
        return "TEMPORAL_PARCIAL"
    return "SEM_CONTRATO_HISTORICO"


def make_summary(root: Path, records: list[dict[str, Any]], created: list[str]) -> dict[str, Any]:
    candidates = [r for r in records if r["candidato"]]
    by_dataset = defaultdict(list)
    for item in candidates:
        item["status_pipeline"] = status_pipeline(item)
        for dataset in item["datasets"]:
            by_dataset[dataset].append(item["arquivo"])
    risk_counts = Counter(risk for item in candidates for risk in item["riscos"])
    table_counts = Counter(table for item in candidates for table in item["tabelas"])
    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "modo": "SOMENTE_LEITURA_NO_PROJETO",
        "projeto": str(root),
        "raiz_analiticos": str(ANALYTICS_ROOT),
        "pastas_criadas": created,
        "arquivos_python_lidos": len(records),
        "candidatos_pipeline": len(candidates),
        "datasets": {key: value for key, value in sorted(by_dataset.items())},
        "riscos": dict(risk_counts),
        "tabelas_referenciadas": dict(table_counts.most_common()),
        "arquivos": candidates,
    }


def markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Inventário dos pipelines - ADM / Desconexão",
        "",
        f"- Gerado em: `{summary['gerado_em']}`",
        f"- Projeto: `{summary['projeto']}`",
        f"- Raiz dos analíticos: `{summary['raiz_analiticos']}`",
        f"- Arquivos Python lidos: **{summary['arquivos_python_lidos']}**",
        f"- Candidatos a pipeline ou acesso a dados: **{summary['candidatos_pipeline']}**",
        "",
        "## Estrutura de pastas",
        "",
    ]
    if summary["pastas_criadas"]:
        lines.extend(f"- Criada: `{p}`" for p in summary["pastas_criadas"])
    else:
        lines.append("- Estrutura já existia. Nenhuma pasta foi recriada.")
    lines.extend(["", "## Cobertura por dataset", ""])
    for dataset in DATASETS:
        files = summary["datasets"].get(dataset, [])
        lines.append(f"### {dataset}")
        if files:
            lines.extend(f"- `{f}`" for f in files)
        else:
            lines.append("- Nenhum candidato localizado.")
        lines.append("")
    lines.extend(["## Riscos localizados", ""])
    if summary["riscos"]:
        lines.extend(f"- **{risk}**: {count} arquivo(s)" for risk, count in sorted(summary["riscos"].items()))
    else:
        lines.append("- Nenhum padrão destrutivo reconhecido foi localizado.")
    lines.extend(["", "## Inventário detalhado", ""])
    for item in summary["arquivos"]:
        lines.extend([
            f"### `{item['arquivo']}`",
            f"- Status: **{item['status_pipeline']}**",
            f"- Sintaxe: {'OK' if item['sintaxe_ok'] else 'ERRO: ' + str(item['erro_sintaxe'])}",
            f"- Datasets: {', '.join(item['datasets']) or 'não classificado'}",
            f"- Tabelas: {', '.join(item['tabelas']) or 'não identificadas estaticamente'}",
            f"- Operações: {', '.join(item['operacoes']) or 'não identificadas'}",
            f"- Campos temporais: {', '.join(item['campos_temporais']) or 'não identificados'}",
            f"- Riscos: {', '.join(item['riscos']) or 'nenhum padrão reconhecido'}",
            f"- Caminhos fixos: {', '.join(item['caminhos_fixos']) or 'nenhum'}",
            f"- Histórico: `{json.dumps(item['historico'], ensure_ascii=False)}`",
            "",
        ])
    lines.extend([
        "## Critérios para a próxima fase",
        "",
        "Antes de alterar qualquer pipeline, confirmar para cada dataset:",
        "1. arquivo de entrada e padrão `DATASET_AAAA-MM`;",
        "2. tabela de destino;",
        "3. fonte da competência e validação nome versus conteúdo;",
        "4. chave de negócio e política de recarga;",
        "5. ausência de `TRUNCATE`, `DROP` ou `replace` da tabela histórica completa;",
        "6. transação e rollback;",
        "7. registro em `controle_cargas`;",
        "8. preservação do arquivo processado e seu hash.",
        "",
        "Este relatório não altera scripts, tabelas ou dados do MySQL.",
    ])
    return "\n".join(lines)


def main() -> int:
    print("=" * 72)
    print("PORTAL OPERACOES RNO - INVENTARIO DE PIPELINES DA DESCONEXAO")
    print("Modo: leitura do projeto; criacao apenas da estrutura aprovada")
    print("=" * 72)
    try:
        root = discover_project_root()
        print(f"[OK] Projeto: {root}")
        created = ensure_analytics_structure()
        print(f"[OK] Raiz analiticos: {ANALYTICS_ROOT}")
        print(f"[OK] Pastas novas: {len(created)}")
        records = scan_project(root)
        summary = make_summary(root, records, created)
        report_dir = root / REPORT_DIR_NAME
        report_dir.mkdir(parents=True, exist_ok=True)
        stamp = now_stamp()
        json_path = report_dir / f"inventario_pipelines_desconexao_{stamp}.json"
        md_path = report_dir / f"inventario_pipelines_desconexao_{stamp}.md"
        latest_json = report_dir / "inventario_pipelines_desconexao_latest.json"
        latest_md = report_dir / "inventario_pipelines_desconexao_latest.md"
        json_text = json.dumps(summary, ensure_ascii=False, indent=2)
        md_text = markdown_report(summary)
        for path, content in ((json_path, json_text), (md_path, md_text), (latest_json, json_text), (latest_md, md_text)):
            path.write_text(content, encoding="utf-8")
        print(f"[OK] Python lidos: {summary['arquivos_python_lidos']}")
        print(f"[OK] Candidatos: {summary['candidatos_pipeline']}")
        print(f"[OK] Relatorio: {md_path}")
        print(f"[OK] JSON: {json_path}")
        if summary["riscos"]:
            print(f"[ATENCAO] Riscos reconhecidos: {summary['riscos']}")
        else:
            print("[OK] Nenhum padrao destrutivo reconhecido.")
        print("[CONCLUIDO] Nenhum pipeline ou tabela foi alterado.")
        return 0
    except Exception as exc:
        print(f"[ERRO] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
