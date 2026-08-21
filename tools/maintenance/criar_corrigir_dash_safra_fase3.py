#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pathlib import Path
from datetime import datetime
import shutil

ARQ = Path(
    r"areas\adm\desconexao\templates\dash_safra_v9_visual.html"
)

if not ARQ.exists():

    print("Arquivo não encontrado:")
    print(ARQ)
    raise SystemExit()

# ========================================================
# BACKUP
# ========================================================

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

backup = ARQ.with_name(
    f"{ARQ.stem}_backup_{timestamp}.html"
)

shutil.copy2(
    ARQ,
    backup
)

print(f"Backup criado: {backup}")

html = ARQ.read_text(
    encoding="utf-8"
)

# ========================================================
# INJETA CSS EXECUTIVO
# ========================================================

css = """

<style id="executive_v10">

.exec-cards{
    display:grid;
    grid-template-columns:repeat(3,1fr);
    gap:14px;
    margin-top:12px;
}

.exec-cards-2{
    display:grid;
    grid-template-columns:repeat(2,1fr);
    gap:14px;
    margin-top:12px;
}

.exec-card{

    border-radius:18px;

    padding:18px;

    text-align:center;

    border:1px solid #d1d5db;

    box-shadow:
        0 3px 10px rgba(0,0,0,.05);

    transition:.2s;
}

.exec-card:hover{
    transform:translateY(-2px);
}

.exec-card .titulo{

    font-size:15px;

    font-weight:900;

    letter-spacing:.04em;

    margin-bottom:10px;
}

.exec-card .valor{

    font-size:36px;

    font-weight:900;
}

.safra1{
    background:#fff1f2;
    border-left:8px solid #dc2626;
}

.safra4{
    background:#fff7ed;
    border-left:8px solid #f97316;
}

.safra13{
    background:#f0fdf4;
    border-left:8px solid #16a34a;
}

.tipo-inad{
    background:#fef2f2;
    border-left:8px solid #991b1b;
}

.tipo-opcao{
    background:#ecfeff;
    border-left:8px solid #0891b2;
}

.card,
.kpi,
.matrix,
.safra-filters{

    border:1px solid #d1d5db !important;

    box-shadow:
        0 3px 10px rgba(0,0,0,.06) !important;
}

</style>

"""

if "executive_v10" not in html:

    html = html.replace(
        "</head>",
        css + "\n</head>"
    )

# ========================================================
# INJETA JS
# ========================================================

js = """

<script id="executive_cards_v10">

function renderExecutiveCards(j){

    const ordem = {
        '1 MES':1,
        '4 MESES':2,
        '13 MESES':3
    };

    const comparativo =
        (j.comparativo || [])
        .sort(
            (a,b) =>
            ordem[a.safra] -
            ordem[b.safra]
        );

    const mapaSafra = {
        '1 MES':'safra1',
        '4 MESES':'safra4',
        '13 MESES':'safra13'
    };

    const gSafra =
        document.getElementById('g_safra');

    if(gSafra){

        gSafra.innerHTML = `
            <div class="exec-cards">

                ${comparativo.map(x => `

                    <div class="exec-card ${mapaSafra[x.safra]}">

                        <div class="titulo">

                            ${x.safra}

                        </div>

                        <div class="valor">

                            ${x.pct.toFixed(1)}%

                        </div>

                    </div>

                `).join('')}

            </div>
        `;
    }

    const gTipo =
        document.getElementById('g_tipo');

    if(gTipo){

        gTipo.innerHTML = `
            <div class="exec-cards-2">

                ${(j.tipos || []).map(x => `

                    <div class="exec-card ${x.tipo.toUpperCase().includes('INAD') ? 'tipo-inad':'tipo-opcao'}">

                        <div class="titulo">

                            ${x.tipo}

                        </div>

                        <div class="valor">

                            ${x.pct.toFixed(1)}%

                        </div>

                    </div>

                `).join('')}

            </div>
        `;
    }
}

</script>

"""

if "executive_cards_v10" not in html:

    html = html.replace(
        "</body>",
        js + "\n</body>"
    )

# ========================================================
# ACOPLA NO LOADDATA
# ========================================================

if "renderExecutiveCards(j);" not in html:

    html = html.replace(

        "renderMatrix(j.matriz)",

        """
renderMatrix(j.matriz);
renderExecutiveCards(j);
"""
    )

ARQ.write_text(
    html,
    encoding="utf-8"
)

print()
print("="*60)
print("SAFRA V10 EXECUTIVO APLICADO")
print("="*60)
print()
print("✔ Cards Safra")
print("✔ Ordem 1M → 4M → 13M")
print("✔ Cards Tipo")
print("✔ Cores executivas")
print("✔ Bordas em painéis")
print("✔ Backup criado")
print()
print("Pressione CTRL+F5 após reiniciar o Flask.")