# -*- coding: utf-8 -*-
"""
fix_hub_compacto.py
Portal Operações RNO — Hub Desconexão compacto para notebooks padrão Claro

Objetivo:
- Reduzir o tamanho visual do Hub sem perder o padrão moderno/aprovado.
- Manter os cards ativos como links reais.
- Manter Retirada de Equipamentos como ACESSAR.
- Criar backup automático do hub_desconexao.html.

Como usar:
1) Salve este arquivo na raiz do projeto OPERACOES_RNO
2) Execute:
   python fix_hub_compacto.py
3) Reinicie o Flask se necessário e use CTRL+F5 no navegador.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
TARGET = PROJECT_ROOT / "templates" / "hub_desconexao.html"

HTML = """{% extends "base.html" %}

{% block title %}ADM | Desconexão{% endblock %}

{% block content %}
<style>
  :root {
    --claro-red: #E60000;
    --claro-red-dark: #B71C1C;
    --card: #FFFFFF;
    --text: #202234;
    --muted: #6C757D;
    --soft-muted: #81879A;
    --soon: #F4A261;
  }

  /* HUB COMPACTO — pensado para notebook 1920x1080 com header fixo */
  .hub-wrap {
    width: min(1760px, calc(100vw - 44px));
    margin: 0 auto;
    padding: 16px 0 28px;
  }

  .hub-breadcrumb {
    color: #8B8EA1;
    font-size: 11px;
    font-weight: 850;
    letter-spacing: .15em;
    text-transform: uppercase;
    margin-bottom: 8px;
  }

  .hub-hero {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    margin-bottom: 18px;
  }

  .hub-titlebox {
    border-left: 5px solid var(--claro-red);
    padding-left: 14px;
    min-width: 0;
  }

  .hub-eyebrow {
    color: var(--claro-red);
    font-size: 11px;
    font-weight: 900;
    letter-spacing: .17em;
    text-transform: uppercase;
    margin-bottom: 4px;
  }

  .hub-title {
    margin: 0;
    color: var(--text);
    font-size: clamp(27px, 2.15vw, 38px);
    line-height: 1.02;
    font-weight: 950;
    letter-spacing: -.045em;
  }

  .hub-subtitle {
    margin: 7px 0 0;
    max-width: 920px;
    color: var(--muted);
    font-size: 14.5px;
    line-height: 1.34;
    font-weight: 650;
  }

  .hub-pill {
    flex: 0 0 auto;
    padding: 9px 15px;
    border-radius: 999px;
    background: #fff;
    border: 1px solid rgba(0,0,0,.055);
    color: var(--muted);
    font-size: 12.5px;
    font-weight: 900;
    box-shadow: 0 10px 26px rgba(19, 24, 44, .055);
    white-space: nowrap;
  }

  .hub-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(230px, 1fr));
    gap: 17px;
  }

  .dash-card,
  .dash-card-soon {
    position: relative;
    min-height: 168px;
    border-radius: 20px;
    background: var(--card);
    border: 1px solid rgba(0,0,0,.052);
    box-shadow: 0 12px 34px rgba(25, 30, 55, .052);
    padding: 20px 22px 18px;
    overflow: hidden;
    text-decoration: none !important;
    color: inherit;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
  }

  a.dash-card {
    cursor: pointer !important;
    pointer-events: auto !important;
    opacity: 1 !important;
    filter: none !important;
  }

  a.dash-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 18px 46px rgba(25, 30, 55, .09);
    border-color: rgba(230, 0, 0, .18);
  }

  a.dash-card:focus-visible {
    outline: 3px solid rgba(230,0,0,.18);
    outline-offset: 3px;
  }

  .dash-card-soon {
    opacity: .62;
    cursor: not-allowed;
    pointer-events: none;
    filter: grayscale(.06);
  }

  .card-icon {
    width: 54px;
    height: 54px;
    border-radius: 15px;
    display: grid;
    place-items: center;
    color: #fff;
    font-size: 25px;
    box-shadow: 0 12px 26px rgba(230, 0, 0, .14);
    margin-bottom: 13px;
  }

  .ic-red { background: linear-gradient(135deg, #E60000, #B71C1C); }
  .ic-blue { background: linear-gradient(135deg, #8CC7F2, #1976D2); }
  .ic-orange { background: linear-gradient(135deg, #FFBE6B, #FB8C00); }
  .ic-purple { background: linear-gradient(135deg, #9C27B0, #5E35B1); }
  .ic-green { background: linear-gradient(135deg, #9BE7B0, #2E7D32); }
  .ic-pink { background: linear-gradient(135deg, #F06292, #C2185B); }

  .card-title {
    margin: 0 0 6px;
    color: var(--text);
    font-size: 20px;
    line-height: 1.08;
    font-weight: 950;
    letter-spacing: -.035em;
  }

  .card-desc {
    margin: 0;
    color: var(--soft-muted);
    font-size: 13.7px;
    line-height: 1.34;
    font-weight: 650;
  }

  .card-bottom {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    margin-top: 15px;
  }

  .card-status {
    color: #646B78;
    font-size: 12.8px;
    font-weight: 900;
  }

  .card-arrow {
    color: var(--claro-red);
    font-size: 25px;
    line-height: 1;
    font-weight: 950;
    transform: translateX(0);
    opacity: 1;
    transition: transform .16s ease;
  }

  a.dash-card:hover .card-arrow {
    transform: translateX(4px);
  }

  .soon-badge {
    padding: 6px 12px;
    border-radius: 999px;
    background: #F4A261;
    color: #fff;
    font-size: 11.5px;
    font-weight: 950;
    text-transform: uppercase;
    white-space: nowrap;
  }

  @media (max-width: 1440px) {
    .hub-wrap { width: min(1320px, calc(100vw - 34px)); padding-top: 12px; }
    .hub-grid { gap: 14px; }
    .dash-card, .dash-card-soon { min-height: 158px; padding: 18px 19px 16px; border-radius: 18px; }
    .card-icon { width: 50px; height: 50px; font-size: 23px; margin-bottom: 11px; }
    .card-title { font-size: 18.5px; }
    .card-desc { font-size: 13px; }
  }

  @media (max-width: 1180px) {
    .hub-grid { grid-template-columns: repeat(3, minmax(220px, 1fr)); }
    .hub-hero { align-items: flex-start; flex-direction: column; gap: 10px; }
  }

  @media (max-width: 820px) {
    .hub-grid { grid-template-columns: repeat(2, minmax(210px, 1fr)); }
  }

  @media (max-width: 560px) {
    .hub-wrap { width: min(100% - 24px, 1760px); }
    .hub-grid { grid-template-columns: 1fr; }
    .hub-title { font-size: 26px; }
    .hub-subtitle { font-size: 13.5px; }
  }
</style>

<div class="hub-wrap">
  <div class="hub-breadcrumb">ADM / DESCONEXÃO</div>

  <section class="hub-hero">
    <div class="hub-titlebox">
      <div class="hub-eyebrow">Portal Operações RNO</div>
      <h1 class="hub-title">Dashboards de Desconexão</h1>
      <p class="hub-subtitle">
        Relatórios executivos e operacionais para acompanhamento da safra, backlog,
        quebra de agenda, LOG, reincidência, parceiras e retirada de equipamentos.
      </p>
    </div>
    <div class="hub-pill">5 dashboards ativos · 1 ACESSAR</div>
  </section>

  <section class="hub-grid" aria-label="Dashboards disponíveis">

    <a class="dash-card" href="/dash/executivo/" aria-label="Abrir dashboard Visão Executiva">
      <div>
        <div class="card-icon ic-red">★</div>
        <h2 class="card-title">Visão Executiva</h2>
        <p class="card-desc">Indicadores estratégicos C-level (4 KPIs + 6 gráficos)</p>
      </div>
      <div class="card-bottom"><span class="card-status">Ativo</span><span class="card-arrow">→</span></div>
    </a>

    <a class="dash-card" href="/dash/backlog/" aria-label="Abrir dashboard Backlog">
      <div>
        <div class="card-icon ic-blue">☑</div>
        <h2 class="card-title">Backlog</h2>
        <p class="card-desc">Backlog OS por cidade, aging e parceiro</p>
      </div>
      <div class="card-bottom"><span class="card-status">Ativo</span><span class="card-arrow">→</span></div>
    </a>

    <a class="dash-card" href="/dash/quebra/" aria-label="Abrir dashboard Quebra de Agenda">
      <div>
        <div class="card-icon ic-orange">▣</div>
        <h2 class="card-title">Quebra de Agenda</h2>
        <p class="card-desc">Análise de quebras de agenda</p>
      </div>
      <div class="card-bottom"><span class="card-status">Ativo</span><span class="card-arrow">→</span></div>
    </a>

    <a class="dash-card" href="/dash/log/" aria-label="Abrir dashboard LOG e Reincidência">
      <div>
        <div class="card-icon ic-purple">↻</div>
        <h2 class="card-title">LOG &amp; Reincidência</h2>
        <p class="card-desc">Histórico de LOG e reincidências</p>
      </div>
      <div class="card-bottom"><span class="card-status">Ativo</span><span class="card-arrow">→</span></div>
    </a>

    <div class="dash-card-soon">
      <div>
        <div class="card-icon ic-green">▥</div>
        <h2 class="card-title">Retirada de Equipamentos</h2>
        <p class="card-desc">Performance TOA · retirada de equipamentos</p>
      </div>
      <div class="card-bottom"><span class="card-status">Disponível</span><span class="soon-badge">ACESSAR</span></div>
    </div>

    <a class="dash-card" href="/dash/parceiras/" aria-label="Abrir dashboard Parceiras">
      <div>
        <div class="card-icon ic-pink">◆</div>
        <h2 class="card-title">Parceiras</h2>
        <p class="card-desc">Performance por parceira</p>
      </div>
      <div class="card-bottom"><span class="card-status">Ativo</span><span class="card-arrow">→</span></div>
    </a>

  </section>
</div>
{% endblock %}
"""


def read_text_safe(path: Path) -> tuple[str, str]:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc), enc
        except UnicodeDecodeError:
            pass
    return path.read_text(errors="replace"), "utf-8"


def main() -> None:
    print("=" * 78)
    print("FIX HUB COMPACTO — notebook 1920x1080 / padrão Claro")
    print("=" * 78)
    print(f"Raiz detectada : {PROJECT_ROOT}")
    print(f"Arquivo alvo   : {TARGET}")

    if not TARGET.exists():
        print("\nERRO: não encontrei templates/hub_desconexao.html")
        print("Execute este script dentro da raiz do projeto OPERACOES_RNO.")
        return

    _old_html, enc = read_text_safe(TARGET)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = TARGET.with_name(f"hub_desconexao.backup_fix_hub_compacto_{stamp}.html")
    shutil.copy2(TARGET, backup)

    TARGET.write_text(HTML, encoding="utf-8")
    final = TARGET.read_text(encoding="utf-8")

    checks = [
        ("Visão Executiva", 'href="/dash/executivo/"' in final),
        ("Backlog", 'href="/dash/backlog/"' in final),
        ("Quebra de Agenda", 'href="/dash/quebra/"' in final),
        ("LOG & Reincidência", 'href="/dash/log/"' in final),
        ("Parceiras", 'href="/dash/parceiras/"' in final),
        ("Retirada sem link /dash/retirada/", "/dash/retirada/" not in final),
        ("Retirada marcada como ACESSAR", "ACESSAR" in final),
        ("Cards compactos", "min-height: 168px" in final),
    ]

    print("\nBackup criado:")
    print(f"   {backup}")
    print(f"\nArquivo regravado em UTF-8: {TARGET}")
    print(f"Encoding anterior detectado: {enc}")

    print("\nValidação automática:")
    ok_all = True
    for label, ok in checks:
        ok_all = ok_all and ok
        print(f" - {'OK' if ok else 'FALHA'} {label}")

    print("\nAjustes compactos aplicados:")
    print(" - Cards reduzidos de ~230px para 168px de altura mínima")
    print(" - Ícones reduzidos para 54px")
    print(" - Título reduzido para 20px")
    print(" - Grid com gaps menores")
    print(" - Hero/header interno mais baixo")
    print(" - 4 cards por linha preservados em tela larga")

    if ok_all:
        print("\nHUB COMPACTO CORRIGIDO com cards ativos e Retirada em breve.")
    else:
        print("\nHouve alguma validação negativa. Confira o arquivo gerado.")

    print("\nDepois de executar:")
    print("1) Reinicie o Flask se a tela continuar igual.")
    print("2) Use CTRL + F5 no navegador.")
    print("3) Valide se os 4 cards da primeira linha cabem sem aparência grosseira.")
    print("=" * 78)


if __name__ == "__main__":
    main()
