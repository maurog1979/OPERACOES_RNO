# -*- coding: utf-8 -*-
'''
ATIVAR RETIRADA — V4 FORÇADO E DIAGNÓSTICO
Portal Operações RNO / ADM / Desconexão

Localiza a origem real do card "Retirada de Equipamentos" e força ativação.
Uso:
cd "C:\\Users\\n5996917\\OneDrive - Claro SA\\INTRANET\\OPERACOES_RNO"
python ativar_retirada_forcado_v4.py
'''

from pathlib import Path
from datetime import datetime
import shutil
import re

ROOT = Path(__file__).resolve().parent
ROTA = '/dash/retirada/'
RELATORIO = ROOT / 'relatorio_ativar_retirada_v4.txt'
EXTS = {'.html', '.htm', '.py', '.js', '.json', '.txt'}
IGNORAR = ['.bak', 'backup', '__pycache__', '.git', 'node_modules', 'venv', 'env', 'relatorio_ativar_retirada', 'ativar_retirada_forcado_v4.py', 'fix_completo.py']
MARKER = 'PATCH_V4_RETIRADA_ATIVA'


def agora():
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def norm(txt):
    mapa = str.maketrans({
        'ç':'c','Ç':'C','ã':'a','Ã':'A','á':'a','Á':'A','à':'a','À':'A','â':'a','Â':'A',
        'é':'e','É':'E','ê':'e','Ê':'E','í':'i','Í':'I','ó':'o','Ó':'O','ô':'o','Ô':'O',
        'õ':'o','Õ':'O','ú':'u','Ú':'U'
    })
    return str(txt).translate(mapa).lower()


def read_text(path):
    try:
        return path.read_text(encoding='utf-8'), 'utf-8'
    except UnicodeDecodeError:
        return path.read_text(encoding='latin-1'), 'latin-1'


def write_text(path, txt, enc):
    path.write_text(txt, encoding=enc)


def deve_ignorar(path):
    s = str(path).lower()
    if path.suffix.lower() not in EXTS:
        return True
    return any(x.lower() in s for x in IGNORAR)


def backup(path):
    bkp = path.with_suffix(path.suffix + '.bak_retirada_v4_' + agora())
    shutil.copy2(path, bkp)
    return bkp


def trocar_textos(txt):
    trocas = [
        ('Em desenvolvimento', 'Disponível'), ('EM DESENVOLVIMENTO', 'DISPONÍVEL'), ('em desenvolvimento', 'Disponível'),
        ('EM BREVE', 'ACESSAR'), ('Em breve', 'ACESSAR'), ('em breve', 'ACESSAR'),
        ('Em construção', 'Disponível'), ('EM CONSTRUÇÃO', 'DISPONÍVEL'),
        ('Indisponível', 'Disponível'), ('INDISPONÍVEL', 'DISPONÍVEL')
    ]
    for a, b in trocas:
        txt = txt.replace(a, b)
    return txt


def valor_placeholder(v):
    v2 = norm(str(v).strip())
    return v2 in {'', '#', '/#', 'javascript:void(0)', 'javascript:void(0);', 'javascript:;', 'none', 'null', 'false', 'em breve', 'em_breve', 'em-breve', 'coming soon', 'coming-soon', 'soon', 'em desenvolvimento'}


def corrigir_links(seg):
    original = seg

    def repl_attr(m):
        attr = m.group(1)
        quote = m.group(2)
        val = m.group(3)
        if valor_placeholder(val) or 'retirada' in norm(val):
            return attr + '=' + quote + ROTA + quote
        return m.group(0)

    seg = re.sub(r'\b(href|data-href|data-url|data-link|data-route|data-path)\s*=\s*(["\'])(.*?)(?:\2)', repl_attr, seg, flags=re.I|re.S)

    keys = 'href|url|link|route|rota|path|endpoint|to'

    def repl_key(m):
        prefix = m.group(1)
        quote = m.group(2)
        val = m.group(3)
        if valor_placeholder(val) or 'retirada' in norm(val):
            return prefix + quote + ROTA + quote
        return m.group(0)

    seg = re.sub(r'((?:["\']?(?:' + keys + r')["\']?\s*[:=]\s*)(["\']))(.*?)(?:\2)', repl_key, seg, flags=re.I|re.S)
    return seg, seg != original


def corrigir_flags(seg):
    original = seg
    bloqueios = ['disabled', 'is_disabled', 'bloqueado', 'locked', 'coming_soon', 'comingSoon', 'em_breve', 'emBreve', 'soon', 'development', 'under_development']
    ativos = ['active', 'ativo', 'enabled', 'disponivel', 'available', 'clickable']
    for k in bloqueios:
        seg = re.sub(r'(["\']?' + re.escape(k) + r'["\']?\s*[:=]\s*)true\b', r'\1false', seg, flags=re.I)
        seg = re.sub(r'(["\']?' + re.escape(k) + r'["\']?\s*[:=]\s*)True\b', r'\1False', seg)
        seg = re.sub(r'(["\']?' + re.escape(k) + r'["\']?\s*[:=]\s*)1\b', r'\g<1>0', seg, flags=re.I)
    for k in ativos:
        seg = re.sub(r'(["\']?' + re.escape(k) + r'["\']?\s*[:=]\s*)false\b', r'\1true', seg, flags=re.I)
        seg = re.sub(r'(["\']?' + re.escape(k) + r'["\']?\s*[:=]\s*)False\b', r'\1True', seg)
        seg = re.sub(r'(["\']?' + re.escape(k) + r'["\']?\s*[:=]\s*)0\b', r'\g<1>1', seg, flags=re.I)
    return seg, seg != original


def limpar_bloqueios(seg):
    original = seg
    remover = {'disabled','is-disabled','card-disabled','card-inativo','inativo','soon','coming-soon','em-breve','bloqueado','opacity-50','opacity-60','pointer-events-none','cursor-not-allowed'}

    def repl_class(m):
        quote = m.group(1)
        classes = m.group(2)
        novas = [c for c in classes.split() if c.lower() not in remover]
        return 'class=' + quote + ' '.join(novas) + quote

    seg = re.sub(r'class\s*=\s*(["\'])(.*?)\1', repl_class, seg, flags=re.I|re.S)
    seg = re.sub(r'pointer-events\s*:\s*none\s*;?', '', seg, flags=re.I)
    seg = re.sub(r'cursor\s*:\s*not-allowed\s*;?', 'cursor: pointer;', seg, flags=re.I)
    seg = re.sub(r'opacity\s*:\s*0\.[0-9]+\s*;?', 'opacity: 1;', seg, flags=re.I)
    seg = re.sub(r'\sdisabled\b', '', seg, flags=re.I)
    seg = re.sub(r'\saria-disabled\s*=\s*(["\'])true\1', '', seg, flags=re.I)
    return seg, seg != original


def janelas_retirada(txt):
    linhas = txt.splitlines(keepends=True)
    idxs = []
    for i, linha in enumerate(linhas):
        n = norm(linha)
        if 'retirada de equipamentos' in n or ('retirada' in n and 'equipamento' in n):
            idxs.append(i)
    if not idxs:
        return linhas, []
    janelas = []
    for i in idxs:
        janelas.append([max(0, i - 40), min(len(linhas), i + 80)])
    janelas.sort()
    unidas = []
    for ini, fim in janelas:
        if not unidas or ini > unidas[-1][1]:
            unidas.append([ini, fim])
        else:
            if fim > unidas[-1][1]:
                unidas[-1][1] = fim
    return linhas, unidas


def patch_segmento(seg):
    original = seg
    seg = trocar_textos(seg)
    seg, _ = corrigir_links(seg)
    seg, _ = corrigir_flags(seg)
    seg, _ = limpar_bloqueios(seg)
    return seg, seg != original


def snippet_js():
    return r'''
<style>
/* PATCH_V4_RETIRADA_ATIVA */
.card-retirada-v4-ativo { cursor: pointer !important; pointer-events: auto !important; opacity: 1 !important; filter: none !important; }
.card-retirada-v4-ativo * { pointer-events: auto !important; }
/* FIM_PATCH_V4_RETIRADA_ATIVA */
</style>
<script>
/* PATCH_V4_RETIRADA_ATIVA */
(function(){
    const ROTA = "/dash/retirada/";
    function norm(t){ return String(t||"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, ""); }
    function trocarTextos(root){
        const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
        const nodes = [];
        while(w.nextNode()) nodes.push(w.currentNode);
        nodes.forEach(function(n){
            let t = n.nodeValue || "";
            t = t.replace(/Em desenvolvimento/g,"Disponível").replace(/EM DESENVOLVIMENTO/g,"DISPONÍVEL").replace(/em desenvolvimento/g,"Disponível");
            t = t.replace(/EM BREVE/g,"ACESSAR").replace(/Em breve/g,"ACESSAR").replace(/em breve/g,"ACESSAR");
            n.nodeValue = t;
        });
    }
    function ativar(){
        const todos = Array.from(document.querySelectorAll("a, article, section, div, li"));
        let candidatos = todos.filter(function(el){ return norm(el.textContent).includes("retirada de equipamentos"); })
            .map(function(el){ return {el:el, len:String(el.textContent||"").trim().length}; })
            .filter(function(x){ return x.len >= 20 && x.len <= 1800; });
        if(!candidatos.length) return;
        candidatos.sort(function(a,b){ return a.len - b.len; });
        let card = candidatos[0].el;
        let anc = card.closest("a, article, li, .card, .hub-card, .dash-card, .dashboard-card, .report-card, .menu-card, .portal-card");
        if(anc && norm(anc.textContent).includes("retirada de equipamentos")) card = anc;
        trocarTextos(card);
        card.classList.remove("disabled","is-disabled","card-disabled","card-inativo","inativo","soon","coming-soon","em-breve","bloqueado","pointer-events-none","cursor-not-allowed");
        card.classList.add("card-retirada-v4-ativo");
        card.removeAttribute("disabled"); card.removeAttribute("aria-disabled");
        card.style.pointerEvents = "auto"; card.style.cursor = "pointer"; card.style.opacity = "1"; card.style.filter = "none";
        if(card.tagName && card.tagName.toLowerCase() === "a") { card.href = ROTA; card.removeAttribute("target"); }
        card.querySelectorAll("a").forEach(function(a){ a.href = ROTA; a.removeAttribute("target"); });
        if(!(card.tagName && card.tagName.toLowerCase() === "a")){
            card.setAttribute("role","link"); card.setAttribute("tabindex","0");
            if(!card.dataset.retiradaV4){
                card.dataset.retiradaV4 = "1";
                card.addEventListener("click", function(ev){ if(ev.target && ev.target.closest && ev.target.closest("a")) return; window.location.href = ROTA; });
                card.addEventListener("keydown", function(ev){ if(ev.key === "Enter" || ev.key === " "){ ev.preventDefault(); window.location.href = ROTA; } });
            }
        }
    }
    function run(){ ativar(); setTimeout(ativar,250); setTimeout(ativar,800); setTimeout(ativar,1600); }
    if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", run); else run();
})();
/* FIM_PATCH_V4_RETIRADA_ATIVA */
</script>
'''


def injeta_js_html(txt):
    if MARKER in txt:
        return txt, False
    snip = snippet_js()
    if '{% endblock %}' in txt:
        return txt.replace('{% endblock %}', snip + '\n{% endblock %}', 1), True
    if '</body>' in txt:
        return txt.replace('</body>', snip + '\n</body>', 1), True
    return txt.rstrip() + '\n\n' + snip + '\n', True


def processar(path):
    txt, enc = read_text(path)
    original = txt
    n = norm(txt)
    contem = 'retirada de equipamentos' in n or ('retirada' in n and 'equipamento' in n)
    if not contem:
        return None

    linhas, wins = janelas_retirada(txt)
    for ini, fim in reversed(wins):
        seg = ''.join(linhas[ini:fim])
        novo, mudou = patch_segmento(seg)
        if mudou:
            linhas[ini:fim] = [novo]
    txt = ''.join(linhas)

    if path.suffix.lower() in {'.html', '.htm'}:
        txt, _ = injeta_js_html(txt)

    if txt != original:
        bkp = backup(path)
        write_text(path, txt, enc)
        return {'arquivo': str(path), 'alterado': True, 'backup': str(bkp), 'janelas': len(wins)}
    return {'arquivo': str(path), 'alterado': False, 'backup': '', 'janelas': len(wins)}


def injetar_base():
    base = ROOT / 'templates' / 'base.html'
    if not base.exists():
        return None
    txt, enc = read_text(base)
    if MARKER in txt:
        return {'arquivo': str(base), 'alterado': False, 'backup': '', 'janelas': 'base já tinha patch'}
    novo, mudou = injeta_js_html(txt)
    if mudou and novo != txt:
        bkp = backup(base)
        write_text(base, novo, enc)
        return {'arquivo': str(base), 'alterado': True, 'backup': str(bkp), 'janelas': 'patch global'}
    return {'arquivo': str(base), 'alterado': False, 'backup': '', 'janelas': 'base sem alteração'}


def main():
    print('=' * 72)
    print('ATIVAR RETIRADA — V4 FORÇADO')
    print('=' * 72)
    print('ROOT:', ROOT)
    print('ROTA:', ROTA)
    print('-' * 72)

    resultados = []
    rb = injetar_base()
    if rb:
        resultados.append(rb)

    for p in ROOT.rglob('*'):
        if p.is_file() and not deve_ignorar(p):
            try:
                r = processar(p)
                if r:
                    resultados.append(r)
            except Exception as e:
                resultados.append({'arquivo': str(p), 'alterado': False, 'backup': '', 'janelas': 'ERRO: ' + str(e)})

    linhas = []
    linhas.append('RELATÓRIO ATIVAR RETIRADA V4\n')
    linhas.append('ROOT: ' + str(ROOT) + '\n')
    linhas.append('ROTA: ' + ROTA + '\n')
    linhas.append('=' * 72 + '\n\n')
    for r in resultados:
        linhas.append('Arquivo: ' + str(r.get('arquivo')) + '\n')
        linhas.append('Alterado: ' + ('SIM' if r.get('alterado') else 'NÃO') + '\n')
        linhas.append('Janelas/Obs: ' + str(r.get('janelas')) + '\n')
        if r.get('backup'):
            linhas.append('Backup: ' + str(r.get('backup')) + '\n')
        linhas.append('-' * 72 + '\n')
    if not resultados:
        linhas.append('Nenhum arquivo contendo Retirada de Equipamentos foi encontrado.\n')
    RELATORIO.write_text(''.join(linhas), encoding='utf-8')

    if resultados:
        for r in resultados:
            status = 'ALTERADO' if r.get('alterado') else 'NÃO ALTERADO'
            print('-', status + ':', r.get('arquivo'), '|', r.get('janelas'))
    else:
        print('Nenhum arquivo contendo Retirada de Equipamentos foi encontrado.')

    print('-' * 72)
    print('RELATÓRIO:', RELATORIO)
    print('Depois: pare/suba o Flask e use Ctrl+F5 no Hub.')
    print('Esperado: Retirada de Equipamentos | Disponível | ACESSAR | /dash/retirada/')
    print('=' * 72)


if __name__ == '__main__':
    main()
