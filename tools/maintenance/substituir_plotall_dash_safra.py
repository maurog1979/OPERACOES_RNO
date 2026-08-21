#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pathlib import Path
import shutil
from datetime import datetime

ARQ = Path(
    r"areas\adm\desconexao\templates\dash_safra.html"
)

if not ARQ.exists():

    print("ERRO")
    print("Arquivo não encontrado:")
    print(ARQ)

    raise SystemExit()

# ==================================================
# BACKUP
# ==================================================

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

backup = ARQ.with_name(
    f"{ARQ.stem}_backup_plotall_{timestamp}.html"
)

shutil.copy2(
    ARQ,
    backup
)

print("Backup criado:")
print(backup)

# ==================================================
# LEITURA
# ==================================================

html = ARQ.read_text(
    encoding="utf-8",
    errors="ignore"
)

inicio = html.find(
    "function plotAll(j){"
)

fim = html.find(
    "function td("
)

if inicio == -1:

    print("ERRO")
    print("plotAll não encontrado")
    raise SystemExit()

if fim == -1:

    print("ERRO")
    print("function td não encontrada")
    raise SystemExit()

print()
print("plotAll encontrado")
print("Posição inicial:", inicio)
print("Posição final:", fim)

# ==================================================
# NOVA FUNÇÃO
# ==================================================

novo_plotall = r"""
function plotAll(j){

    Plotly.newPlot(
        'g_meta',
        [{
            type:'bar',

            x:[
                'Recuperado',
                'Meta'
            ],

            y:[
                j.kpis.rec,
                Math.round(
                    j.kpis.desc *
                    j.kpis.meta / 100
                )
            ],

            text:[
                fmt(j.kpis.rec),
                fmt(
                    Math.round(
                        j.kpis.desc *
                        j.kpis.meta / 100
                    )
                )
            ],

            textposition:'outside',

            marker:{
                color:[
                    '#e60000',
                    '#111827'
                ]
            }
        }],
        {
            height:220,

            margin:{
                t:40,
                l:45,
                r:15,
                b:40
            }
        },
        {
            displayModeBar:false
        }
    );

    const rank =
        (j.ranking || [])
        .slice(0,10)
        .reverse();

    Plotly.newPlot(
        'g_rank',
        [{
            type:'bar',

            orientation:'h',

            y:
                rank.map(
                    x => x.cidade
                ),

            x:
                rank.map(
                    x => x.pct
                ),

            text:
                rank.map(
                    x => x.pct.toFixed(1)+'%'
                ),

            textposition:'outside',

            marker:{
                color:'#e60000'
            }
        }],
        {
            height:220,

            margin:{
                t:20,
                l:140,
                r:20,
                b:20
            },

            xaxis:{
                range:[0,100],
                ticksuffix:'%'
            }
        },
        {
            displayModeBar:false
        }
    );

    renderExecutiveCards(j);
}

function renderExecutiveCards(j){

    const ordem = {
        '1 MES':1,
        '4 MESES':2,
        '13 MESES':3
    };

    const classes = {
        '1 MES':'safra1',
        '4 MESES':'safra4',
        '13 MESES':'safra13'
    };

    const cardsSafra =
        (j.comparativo || [])
        .sort(
            (a,b)=>
                ordem[a.safra]-ordem[b.safra]
        );

    document.getElementById(
        'g_safra'
    ).innerHTML = `
        <div class="exec-cards">

        ${cardsSafra.map(x=>`

            <div class="exec-card ${classes[x.safra]}">

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

    document.getElementById(
        'g_tipo'
    ).innerHTML = `
        <div class="exec-cards-2">

        ${(j.tipos || []).map(x=>`

            <div class="exec-card">

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

"""

# ==================================================
# SUBSTITUIR
# ==================================================

html = (
    html[:inicio]
    + novo_plotall
    + html[fim:]
)

ARQ.write_text(
    html,
    encoding="utf-8"
)

print()
print("=" * 60)
print("PLOTALL SUBSTITUIDO COM SUCESSO")
print("=" * 60)
print()
print("Reinicie o Flask")
print("Depois execute CTRL+F5")