# -*- coding: utf-8 -*-
"""
Teste funcional e de performance do cache do dash_quebra_rno.

Executa com Flask test_client:
- limpa o cache;
- mede cold miss;
- mede warm hit;
- valida headers X-Cache;
- valida identidade do JSON;
- valida reducao de tempo;
- valida isolamento entre modos;
- valida rota de status;
- grava relatorio JSON e Markdown em reports/.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

def localizar_raiz_projeto() -> Path:
    """Sobe na arvore ate encontrar app.py e a pasta areas/."""
    atual = Path(__file__).resolve().parent
    candidatos = [atual, *atual.parents]
    for pasta in candidatos:
        if (pasta / "app.py").is_file() and (pasta / "areas").is_dir():
            return pasta
    raise RuntimeError(
        "Raiz do projeto nao encontrada. Esperado app.py e areas/ "
        "em algum diretorio pai do teste."
    )


ROOT = localizar_raiz_projeto()
REPORTS = ROOT / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

URL_QTD = "/dash/quebra-rno/api/refresh?mode=quantidade"
URL_TAXA = "/dash/quebra-rno/api/refresh?mode=taxa"
URL_STATUS = "/dash/quebra-rno/api/cache/status"
URL_CLEAR = "/dash/quebra-rno/api/cache/clear"


def medir(client, url: str) -> dict:
    inicio = time.perf_counter()
    response = client.get(url)
    elapsed_ms = round((time.perf_counter() - inicio) * 1000.0, 2)
    return {
        "url": url,
        "status": response.status_code,
        "elapsed_ms": elapsed_ms,
        "x_cache": response.headers.get("X-Cache"),
        "x_cache_age_ms": response.headers.get("X-Cache-Age-Ms"),
        "x_cache_key": response.headers.get("X-Cache-Key"),
        "bytes": len(response.data or b""),
        "json": response.get_json(silent=True),
    }


def sem_meta(payload):
    # Atualmente o cache nao altera o JSON. Mantem helper para evolucao.
    return payload


def main() -> int:
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)

    print("=" * 76)
    print(" TESTE DO CACHE - DASH QUEBRA RNO")
    print("=" * 76)

    with app.test_client() as client:
        clear = client.post(URL_CLEAR)
        assert clear.status_code == 200, "Falha ao limpar cache"
        print("Cache limpo.")

        cold = medir(client, URL_QTD)
        print(f"Cold quantidade: {cold['elapsed_ms']:,.2f} ms | {cold['x_cache']}")
        assert cold["status"] == 200
        assert cold["x_cache"] == "MISS", cold

        warm_runs = [medir(client, URL_QTD) for _ in range(3)]
        for i, run in enumerate(warm_runs, 1):
            print(f"Warm quantidade {i}: {run['elapsed_ms']:,.2f} ms | {run['x_cache']}")
            assert run["status"] == 200
            assert run["x_cache"].startswith("HIT"), run
            assert sem_meta(run["json"]) == sem_meta(cold["json"])

        warm_media = round(statistics.mean(r["elapsed_ms"] for r in warm_runs), 2)
        speedup = round(cold["elapsed_ms"] / warm_media, 2) if warm_media else None

        # Modo local: URLs antigas com mode=taxa reutilizam a mesma base.
        # A primeira chamada de Taxa deve ser HIT imediato, com a mesma
        # chave e o mesmo JSON-base de Quantidade.
        taxa_cold = medir(client, URL_TAXA)
        taxa_warm = medir(client, URL_TAXA)
        print(f"Taxa apos Quantidade: {taxa_cold['elapsed_ms']:,.2f} ms | {taxa_cold['x_cache']}")
        print(f"Taxa repetida: {taxa_warm['elapsed_ms']:,.2f} ms | {taxa_warm['x_cache']}")
        assert taxa_cold["x_cache"].startswith("HIT")
        assert taxa_warm["x_cache"].startswith("HIT")
        assert taxa_cold["x_cache_key"] == cold["x_cache_key"]
        assert taxa_cold["json"] == cold["json"]

        status = client.get(URL_STATUS)
        status_json = status.get_json()
        assert status.status_code == 200
        assert status_json["cache"]["hits"] >= 5
        assert status_json["cache"]["misses"] == 1
        assert status_json["cache"]["entries"] == 1

    # Criterios de aceite realistas para ambiente local.
    criterios = {
        "warm_abaixo_1000ms": warm_media < 1000,
        "speedup_minimo_10x": bool(speedup and speedup >= 10),
        "json_identico": all(r["json"] == cold["json"] for r in warm_runs),
        "headers_corretos": (
            cold["x_cache"] == "MISS"
            and all(r["x_cache"].startswith("HIT") for r in warm_runs)
        ),
        "modo_reutiliza_mesma_base": (
            taxa_cold["x_cache_key"] == cold["x_cache_key"]
            and taxa_cold["x_cache"].startswith("HIT")
        ),
    }

    resultado = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "cold_quantidade": cold,
        "warm_quantidade": warm_runs,
        "warm_media_ms": warm_media,
        "speedup": speedup,
        "cold_taxa": taxa_cold,
        "warm_taxa": taxa_warm,
        "cache_status": status_json,
        "criterios": criterios,
        "aprovado": all(criterios.values()),
    }

    # Remove payload JSON volumoso do relatorio persistido.
    for key in ["cold_quantidade", "cold_taxa", "warm_taxa"]:
        resultado[key].pop("json", None)
    for run in resultado["warm_quantidade"]:
        run.pop("json", None)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = REPORTS / f"teste_cache_quebra_rno_{stamp}.json"
    md_path = REPORTS / f"teste_cache_quebra_rno_{stamp}.md"
    latest_json = REPORTS / "teste_cache_quebra_rno_latest.json"
    latest_md = REPORTS / "teste_cache_quebra_rno_latest.md"

    json_text = json.dumps(resultado, ensure_ascii=False, indent=2)
    json_path.write_text(json_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")

    md = [
        "# Teste de Cache - Quebra RNO",
        "",
        f"Gerado em: **{resultado['gerado_em']}**",
        "",
        "## Tempos",
        "",
        f"- Cold Quantidade: **{cold['elapsed_ms']:,.2f} ms**",
        f"- Warm Quantidade médio: **{warm_media:,.2f} ms**",
        f"- Ganho: **{speedup}x**",
        f"- Taxa após Quantidade: **{taxa_cold['elapsed_ms']:,.2f} ms**",
        f"- Warm Taxa: **{taxa_warm['elapsed_ms']:,.2f} ms**",
        "",
        "## Critérios",
        "",
    ]
    for nome, ok in criterios.items():
        md.append(f"- {'OK' if ok else 'FALHA'}: `{nome}`")
    md += [
        "",
        f"## Resultado: {'APROVADO' if resultado['aprovado'] else 'REPROVADO'}",
        "",
        "## Estatísticas do cache",
        "",
        "```json",
        json.dumps(status_json, ensure_ascii=False, indent=2),
        "```",
    ]
    md_text = "\n".join(md)
    md_path.write_text(md_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")

    print("-" * 76)
    for nome, ok in criterios.items():
        print(f"{'OK' if ok else 'FALHA':6} {nome}")
    print(f"\nRESULTADO: {'APROVADO' if resultado['aprovado'] else 'REPROVADO'}")
    print(f"Relatorio: {latest_md}")
    print("=" * 76)

    return 0 if resultado["aprovado"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
