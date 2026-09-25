# -*- coding: utf-8 -*-
"""
=====================================================================
PORTAL OPERACOES RNO
Diagnostico comparativo de performance: dash_quebra x dash_quebra_rno
=====================================================================

OBJETIVO
  Medir, sem alterar os dashboards:
    - tempo total de cada endpoint;
    - tempo e quantidade das consultas SQL do novo Quebra RNO;
    - linhas retornadas por consulta;
    - tempo fora do SQL (Python, agregacao e JSON);
    - primeira execucao e execucoes aquecidas;
    - diferenca entre troca de modo Quantidade/Taxa/Representatividade;
    - comparacao com o dash_quebra legado.

COMO EXECUTAR
  Salve este arquivo na raiz do projeto e rode:

      python diagnosticar_performance_quebra.py

SAIDAS
  reports/performance_quebra_YYYYMMDD_HHMMSS.json
  reports/performance_quebra_YYYYMMDD_HHMMSS.md
  reports/performance_quebra_latest.json
  reports/performance_quebra_latest.md

SEGURANCA
  - Somente leitura.
  - Nao altera banco, dashboard, cache ou configuracao.
  - Usa o test_client do Flask, sem precisar abrir navegador.
  - Restaura as funcoes instrumentadas ao final.
=====================================================================
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shutil
import statistics
import sys
import time
import traceback
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

# Repeticoes aquecidas. A primeira chamada e medida separadamente.
WARM_RUNS = 3

# Endpoints conhecidos. O script valida a existencia antes de chamar.
CENARIOS = [
    {
        "nome": "legado_quantidade",
        "dashboard": "dash_quebra",
        "rota": "/dash/quebra/api/refresh",
        "query": "mode=quantidade",
        "tipo": "legado",
    },
    {
        "nome": "rno_quantidade",
        "dashboard": "dash_quebra_rno",
        "rota": "/dash/quebra-rno/api/refresh",
        "query": "mode=quantidade",
        "tipo": "rno",
    },
    {
        "nome": "rno_taxa",
        "dashboard": "dash_quebra_rno",
        "rota": "/dash/quebra-rno/api/refresh",
        "query": "mode=taxa",
        "tipo": "rno",
    },
    {
        "nome": "rno_representatividade",
        "dashboard": "dash_quebra_rno",
        "rota": "/dash/quebra-rno/api/refresh",
        "query": "mode=representatividade",
        "tipo": "rno",
    },
]


@dataclass
class SQLCall:
    ordem: int
    duracao_ms: float
    linhas: int | None
    cache_key: str | None
    sql_hash: str
    sql_resumo: str
    erro: str | None = None


@dataclass
class RequestRun:
    execucao: str
    status_http: int
    duracao_total_ms: float
    tamanho_bytes: int
    sql_total_ms: float
    sql_qtd: int
    fora_sql_ms: float
    sql_calls: list[dict[str, Any]]
    erro_api: str | None = None


def agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ms(segundos: float) -> float:
    return round(segundos * 1000.0, 2)


def normalizar_sql(sql: Any, limite: int = 330) -> str:
    texto = str(sql or "")
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto if len(texto) <= limite else texto[:limite] + " ..."


def hash_sql(sql: Any) -> str:
    texto = re.sub(r"\s+", " ", str(sql or "")).strip()
    return hashlib.sha1(texto.encode("utf-8", errors="replace")).hexdigest()[:12]


def qtd_linhas(resultado: Any) -> int | None:
    if resultado is None:
        return 0
    try:
        return int(len(resultado))
    except Exception:
        return None


def descobrir_rotas(app) -> set[str]:
    return {str(rule) for rule in app.url_map.iter_rules()}


class QueryProfiler:
    """Instrumenta funcoes query importadas diretamente pelos blueprints."""

    def __init__(self):
        self.calls: list[SQLCall] = []
        self._restores: list[tuple[Any, str, Any]] = []

    def reset(self) -> None:
        self.calls = []

    def instalar(self) -> None:
        # O novo blueprint importa query com:
        # from data.db_desconexao import query
        # Portanto e necessario trocar o simbolo no proprio modulo.
        alvos = [
            ("areas.adm.desconexao.dash_quebra_rno", ["query"]),
        ]

        for modulo_nome, nomes in alvos:
            try:
                modulo = importlib.import_module(modulo_nome)
            except Exception as exc:
                print(f"[AVISO] Nao foi possivel importar {modulo_nome}: {exc}")
                continue

            for nome in nomes:
                original = getattr(modulo, nome, None)
                if not callable(original):
                    continue
                wrapped = self._criar_wrapper(original)
                self._restores.append((modulo, nome, original))
                setattr(modulo, nome, wrapped)

    def restaurar(self) -> None:
        for modulo, nome, original in reversed(self._restores):
            setattr(modulo, nome, original)
        self._restores.clear()

    def _criar_wrapper(self, original: Callable) -> Callable:
        profiler = self

        def wrapped(sql, *args, **kwargs):
            inicio = time.perf_counter()
            erro = None
            resultado = None
            try:
                resultado = original(sql, *args, **kwargs)
                return resultado
            except Exception as exc:
                erro = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                duracao = ms(time.perf_counter() - inicio)
                cache_key = kwargs.get("cache_key")
                profiler.calls.append(SQLCall(
                    ordem=len(profiler.calls) + 1,
                    duracao_ms=duracao,
                    linhas=qtd_linhas(resultado),
                    cache_key=str(cache_key) if cache_key is not None else None,
                    sql_hash=hash_sql(sql),
                    sql_resumo=normalizar_sql(sql),
                    erro=erro,
                ))

        wrapped.__name__ = getattr(original, "__name__", "query_instrumentada")
        wrapped.__doc__ = getattr(original, "__doc__", None)
        return wrapped


@contextmanager
def profiler_instalado():
    profiler = QueryProfiler()
    profiler.instalar()
    try:
        yield profiler
    finally:
        profiler.restaurar()


def extrair_erro_api(response) -> str | None:
    try:
        payload = response.get_json(silent=True)
        if isinstance(payload, dict):
            return payload.get("error") or payload.get("erro")
    except Exception:
        pass
    return None


def executar_request(client, profiler: QueryProfiler, url: str,
                      nome_execucao: str) -> RequestRun:
    profiler.reset()
    inicio = time.perf_counter()
    response = client.get(url)
    duracao_total = ms(time.perf_counter() - inicio)

    calls = [asdict(c) for c in profiler.calls]
    sql_total = round(sum(c["duracao_ms"] for c in calls), 2)
    fora_sql = round(max(0.0, duracao_total - sql_total), 2)

    return RequestRun(
        execucao=nome_execucao,
        status_http=int(response.status_code),
        duracao_total_ms=duracao_total,
        tamanho_bytes=len(response.data or b""),
        sql_total_ms=sql_total,
        sql_qtd=len(calls),
        fora_sql_ms=fora_sql,
        sql_calls=calls,
        erro_api=extrair_erro_api(response),
    )


def resumo_cenario(runs: list[RequestRun]) -> dict[str, Any]:
    cold = runs[0]
    warm = runs[1:]
    warm_t = [r.duracao_total_ms for r in warm]
    warm_sql = [r.sql_total_ms for r in warm]
    warm_qtd = [r.sql_qtd for r in warm]

    return {
        "cold_total_ms": cold.duracao_total_ms,
        "cold_sql_ms": cold.sql_total_ms,
        "cold_sql_qtd": cold.sql_qtd,
        "cold_fora_sql_ms": cold.fora_sql_ms,
        "warm_total_media_ms": round(statistics.mean(warm_t), 2) if warm_t else None,
        "warm_total_min_ms": round(min(warm_t), 2) if warm_t else None,
        "warm_total_max_ms": round(max(warm_t), 2) if warm_t else None,
        "warm_sql_media_ms": round(statistics.mean(warm_sql), 2) if warm_sql else None,
        "warm_sql_qtd_media": round(statistics.mean(warm_qtd), 2) if warm_qtd else None,
        "status_ok": all(r.status_http == 200 and not r.erro_api for r in runs),
    }


def formatar_ms(valor: Any) -> str:
    if valor is None:
        return "-"
    return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def gerar_markdown(relatorio: dict[str, Any]) -> str:
    linhas: list[str] = []
    linhas.append("# Diagnóstico de Performance: Quebra Legado x Quebra RNO")
    linhas.append("")
    linhas.append(f"Gerado em: **{relatorio['gerado_em']}**")
    linhas.append("")
    linhas.append("## Resumo executivo")
    linhas.append("")
    linhas.append("| Cenário | 1ª execução | Média aquecida | SQL aquecido | Consultas SQL | Fora do SQL | Status |")
    linhas.append("|---|---:|---:|---:|---:|---:|---|")

    for nome, dados in relatorio["cenarios"].items():
        r = dados["resumo"]
        linhas.append(
            f"| {nome} | {formatar_ms(r['cold_total_ms'])} ms | "
            f"{formatar_ms(r['warm_total_media_ms'])} ms | "
            f"{formatar_ms(r['warm_sql_media_ms'])} ms | "
            f"{r['warm_sql_qtd_media']} | "
            f"{formatar_ms(max(0, (r['warm_total_media_ms'] or 0) - (r['warm_sql_media_ms'] or 0)))} ms | "
            f"{'OK' if r['status_ok'] else 'ERRO'} |"
        )

    linhas.append("")
    linhas.append("## Interpretação automática")
    linhas.append("")

    legado = relatorio["cenarios"].get("legado_quantidade", {}).get("resumo")
    rno = relatorio["cenarios"].get("rno_quantidade", {}).get("resumo")

    if legado and rno and legado.get("warm_total_media_ms"):
        fator = (rno.get("warm_total_media_ms") or 0) / legado["warm_total_media_ms"]
        linhas.append(
            f"- O fluxo RNO aquecido levou **{fator:.1f}x** o tempo do fluxo legado."
        )
    if rno:
        total = rno.get("warm_total_media_ms") or 0
        sql = rno.get("warm_sql_media_ms") or 0
        pct = (sql / total * 100) if total else 0
        linhas.append(
            f"- No RNO, as consultas SQL representam aproximadamente **{pct:.1f}%** do tempo aquecido."
        )
        linhas.append(
            f"- O endpoint RNO executou em média **{rno.get('warm_sql_qtd_media')} consultas SQL** por atualização."
        )

    taxa = relatorio["cenarios"].get("rno_taxa", {}).get("resumo")
    repr_ = relatorio["cenarios"].get("rno_representatividade", {}).get("resumo")
    if rno and taxa and repr_:
        linhas.append(
            "- Quantidade, Taxa e Representatividade acionam o mesmo fluxo pesado no backend. "
            "Se os tempos e a quantidade de SQL forem semelhantes, a troca de modo deve ser movida para o navegador."
        )

    linhas.append("")
    linhas.append("## Detalhamento por cenário")

    for nome, dados in relatorio["cenarios"].items():
        linhas.append("")
        linhas.append(f"### {nome}")
        linhas.append("")
        linhas.append(f"Rota: `{dados['url']}`")
        linhas.append("")

        for run in dados["execucoes"]:
            linhas.append(
                f"- **{run['execucao']}**: total {formatar_ms(run['duracao_total_ms'])} ms; "
                f"SQL {formatar_ms(run['sql_total_ms'])} ms; "
                f"fora do SQL {formatar_ms(run['fora_sql_ms'])} ms; "
                f"{run['sql_qtd']} consultas; HTTP {run['status_http']}."
            )

        # Mostra as consultas da primeira execucao, ordenadas por tempo.
        calls = dados["execucoes"][0]["sql_calls"] if dados["execucoes"] else []
        if calls:
            linhas.append("")
            linhas.append("Consultas da primeira execução, da mais lenta para a mais rápida:")
            linhas.append("")
            linhas.append("| # | Tempo | Linhas | Cache key | SQL |")
            linhas.append("|---:|---:|---:|---|---|")
            for call in sorted(calls, key=lambda x: x["duracao_ms"], reverse=True):
                sql = call["sql_resumo"].replace("|", "\\|")
                linhas.append(
                    f"| {call['ordem']} | {formatar_ms(call['duracao_ms'])} ms | "
                    f"{call['linhas'] if call['linhas'] is not None else '-'} | "
                    f"{call['cache_key'] or '-'} | `{sql}` |"
                )
        else:
            linhas.append("")
            linhas.append(
                "Nenhuma chamada SQL instrumentada no request. Isso normalmente indica que o fluxo usa "
                "dados já carregados em memória ou outra função de acesso não vinculada ao blueprint."
            )

    linhas.append("")
    linhas.append("## Critérios para decisão")
    linhas.append("")
    linhas.append("1. Se o legado tiver `sql_qtd = 0`, o ganho vem do DataFrame/cache compartilhado em memória.")
    linhas.append("2. Se o RNO executar 14 consultas, separar as opções em cascata da atualização principal.")
    linhas.append("3. Se Taxa e Representatividade repetirem as mesmas consultas, trocar o modo apenas em JavaScript.")
    linhas.append("4. Se uma ou duas consultas dominarem o tempo, consolidar ou materializar especificamente essas agregações.")
    linhas.append("5. Validar os números antes e depois de qualquer otimização.")
    linhas.append("")

    return "\n".join(linhas)


def main() -> int:
    print("=" * 76)
    print(" DIAGNOSTICO DE PERFORMANCE - QUEBRA LEGADO x QUEBRA RNO")
    print("=" * 76)
    print(f"Inicio: {agora()}")
    print(f"Raiz: {ROOT}")

    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    try:
        from app import create_app
    except Exception:
        print("\nERRO ao importar create_app():")
        traceback.print_exc()
        return 1

    try:
        app = create_app()
        app.config.update(TESTING=True)
        rotas = descobrir_rotas(app)
    except Exception:
        print("\nERRO ao criar a aplicacao:")
        traceback.print_exc()
        return 1

    disponiveis = []
    ignorados = []
    for c in CENARIOS:
        if c["rota"] in rotas:
            disponiveis.append(c)
        else:
            ignorados.append({"nome": c["nome"], "rota": c["rota"]})

    if not disponiveis:
        print("\nNenhuma rota de benchmark foi encontrada.")
        return 1

    print("\nRotas encontradas:")
    for c in disponiveis:
        print(f"  [OK] {c['rota']}")
    for c in ignorados:
        print(f"  [IGNORADA] {c['rota']}")

    relatorio: dict[str, Any] = {
        "gerado_em": agora(),
        "python": sys.version,
        "warm_runs": WARM_RUNS,
        "rotas_ignoradas": ignorados,
        "cenarios": {},
    }

    with app.test_client() as client, profiler_instalado() as profiler:
        for c in disponiveis:
            url = c["rota"] + ("?" + c["query"] if c["query"] else "")
            print(f"\nCenario: {c['nome']}")
            print(f"URL: {url}")

            runs: list[RequestRun] = []

            # Primeira execucao.
            run = executar_request(client, profiler, url, "cold_1")
            runs.append(run)
            print(
                f"  cold: {run.duracao_total_ms:,.2f} ms | "
                f"SQL {run.sql_total_ms:,.2f} ms | {run.sql_qtd} consultas | "
                f"HTTP {run.status_http}"
            )

            # Execucoes aquecidas.
            for i in range(1, WARM_RUNS + 1):
                run = executar_request(client, profiler, url, f"warm_{i}")
                runs.append(run)
                print(
                    f"  warm {i}: {run.duracao_total_ms:,.2f} ms | "
                    f"SQL {run.sql_total_ms:,.2f} ms | {run.sql_qtd} consultas | "
                    f"HTTP {run.status_http}"
                )

            relatorio["cenarios"][c["nome"]] = {
                "dashboard": c["dashboard"],
                "tipo": c["tipo"],
                "url": url,
                "resumo": resumo_cenario(runs),
                "execucoes": [asdict(r) for r in runs],
            }

    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = REPORTS / f"performance_quebra_{carimbo}.json"
    md_path = REPORTS / f"performance_quebra_{carimbo}.md"
    latest_json = REPORTS / "performance_quebra_latest.json"
    latest_md = REPORTS / "performance_quebra_latest.md"

    json_path.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(gerar_markdown(relatorio), encoding="utf-8")
    shutil.copy2(json_path, latest_json)
    shutil.copy2(md_path, latest_md)

    print("\n" + "=" * 76)
    print("RESULTADOS")
    print(f"JSON: {json_path}")
    print(f"MD:   {md_path}")
    print("=" * 76)

    # Resumo final no console.
    for nome, dados in relatorio["cenarios"].items():
        r = dados["resumo"]
        print(
            f"{nome:28} | cold {formatar_ms(r['cold_total_ms']):>10} ms | "
            f"warm {formatar_ms(r['warm_total_media_ms']):>10} ms | "
            f"SQL {formatar_ms(r['warm_sql_media_ms']):>10} ms | "
            f"queries {r['warm_sql_qtd_media']}"
        )

    print("\nEnvie o conteudo de reports/performance_quebra_latest.md para analise.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
