# -*- coding: utf-8 -*-
from __future__ import annotations
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "areas" / "adm" / "desconexao" / "dash_quebra.py"

EXCLUDE_MAP_CODE = """EXCLUDE_MAP = {
    \"g1\": \"dias\",
    \"g2\": \"meses\",
    \"g3\": \"cids\",
    \"g4\": None,
    \"g5\": \"parcs\",
    \"g6\": None,
}
"""

HELPERS = r"""

def _filters_without(filters: dict[str, list[str]], *keys: str) -> dict[str, list[str]]:
    out = {k: list(v) for k, v in (filters or {}).items()}
    for key in keys:
        out[key] = []
    return out

def _masks_without(df: pd.DataFrame, masks: dict[str, np.ndarray], *keys: str) -> dict[str, np.ndarray]:
    out = {k: v.copy() for k, v in (masks or {}).items()}
    for key in keys:
        out[key] = np.ones(len(df), dtype=bool)
    return out
"""

def backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bkp = path.with_name(f"{path.stem}.backup_fix15_g3_forcado_{stamp}{path.suffix}")
    shutil.copy2(path, bkp)
    return bkp

def main() -> None:
    print("=" * 78)
    print("FIX15 QUEBRA — G3 CIDADE LIVRE FORÇADO")
    print("=" * 78)
    print(f"Arquivo alvo: {TARGET}")
    if not TARGET.exists():
        print("ERRO: dash_quebra.py não encontrado. Execute na raiz OPERACOES_RNO.")
        return
    text = TARGET.read_text(encoding="utf-8")
    bkp = backup(TARGET)
    logs = []

    map_pat = re.compile(r"EXCLUDE_MAP\s*=\s*\{.*?\}\s*", re.S)
    if map_pat.search(text):
        text = map_pat.sub(EXCLUDE_MAP_CODE + "\n\n", text, count=1)
        logs.append("OK: EXCLUDE_MAP reforçado")
    else:
        logs.append("AVISO: EXCLUDE_MAP não localizado")

    if "def _filters_without(" not in text:
        pos = text.find("@bp_quebra.route")
        if pos != -1:
            text = text[:pos] + HELPERS + "\n" + text[pos:]
            logs.append("OK: helpers inseridos")
        else:
            logs.append("FALHA: @bp_quebra.route não localizado")
    else:
        logs.append("OK: helpers já existiam")

    replacements = [
        ('"g3": _chart_data_from_masks(df, masks, "g3", "CIDADE", "Top 10 Cidades com Quebra", mode, top=10, sort_desc=True)',
         '"g3": _chart_data_from_masks(df, _masks_without(df, masks, "cids"), "g3", "CIDADE", "Top 10 Cidades com Quebra", mode, top=10, sort_desc=True)'),
        ('"g3": _chart_data(df, filters, "g3", "CIDADE", "Top 10 Cidades com Quebra", mode, top=10, sort_desc=True)',
         '"g3": _chart_data(df, _filters_without(filters, "cids"), "g3", "CIDADE", "Top 10 Cidades com Quebra", mode, top=10, sort_desc=True)'),
    ]
    changed_g3 = False
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new, 1)
            changed_g3 = True
            logs.append("OK: chamada G3 corrigida diretamente")
    if not changed_g3 and "_masks_without(df, masks, \"cids\")" not in text and "_filters_without(filters, \"cids\")" not in text:
        text, n = re.subn(r'"g3"\s*:\s*_chart_data_from_masks\(\s*df\s*,\s*masks\s*,\s*"g3"\s*,\s*"CIDADE"',
                          '"g3": _chart_data_from_masks(df, _masks_without(df, masks, "cids"), "g3", "CIDADE"', text, count=1, flags=re.S)
        if n:
            changed_g3 = True
            logs.append("OK: chamada G3 corrigida via regex masks")
        else:
            text, n2 = re.subn(r'"g3"\s*:\s*_chart_data\(\s*df\s*,\s*filters\s*,\s*"g3"\s*,\s*"CIDADE"',
                              '"g3": _chart_data(df, _filters_without(filters, "cids"), "g3", "CIDADE"', text, count=1, flags=re.S)
            if n2:
                changed_g3 = True
                logs.append("OK: chamada G3 corrigida via regex filters")
    if not changed_g3:
        logs.append("AVISO: não encontrei chamada G3 antiga; verifique se já estava corrigida")

    try:
        compile(text, str(TARGET), "exec")
    except SyntaxError as exc:
        print("ERRO: alteração geraria SyntaxError. Nada foi salvo.")
        print(exc)
        print(f"Backup preservado em: {bkp}")
        return
    TARGET.write_text(text, encoding="utf-8")
    final = TARGET.read_text(encoding="utf-8")
    checks = [
        ("EXCLUDE_MAP g3=cids", '"g3": "cids"' in final),
        ("helpers", "def _filters_without" in final and "def _masks_without" in final),
        ("G3 remove cids", '_masks_without(df, masks, "cids")' in final or '_filters_without(filters, "cids")' in final),
        ("sem load_table", "load_table" not in final),
        ("select direto", "FROM quebra_total" in final),
    ]
    print(f"\nBackup criado: {bkp}")
    print("\nResumo:")
    for log in logs:
        print(" - " + log)
    print("\nValidação:")
    for label, ok in checks:
        print(f" - {'OK' if ok else 'FALHA'} {label}")
    print("\nTeste esperado:")
    print(" - Filtrar CIDADE=Belém")
    print(" - KPI deve continuar mostrando somente Belém")
    print(" - G3 deve mostrar Top 10 cidades, e não somente Belém")
    print("\nDepois de executar:")
    print("1) Reinicie o Flask: python run.py")
    print("2) Use CTRL+F5")
    print("3) Teste CIDADE novamente")
    print("=" * 78)

if __name__ == "__main__":
    main()