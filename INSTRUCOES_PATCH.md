# 🚀 PATCH FASE 2A — Dash Executivo em Flask + Plotly.js

## Como aplicar

1. **Pare o Flask** se estiver rodando (Ctrl+C no terminal)
2. **Extraia este ZIP** por cima da pasta `OPERACOES_RNO/` existente:
   - 🔄 SUBSTITUI: `app.py`, `requirements.txt`, `static/css/operacoes-rno.css`, `areas/adm/desconexao/__init__.py`
   - ➕ ADICIONA: `data/db.py`, `templates/hub_desconexao.html`, `areas/adm/desconexao/dash_executivo.py`, `areas/adm/desconexao/templates/dash_executivo.html`
3. **Instale as novas dependências:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Garanta que o MySQL (Laragon) está rodando** com a tabela `safra_final` disponível.
5. **Rode o portal:**
   ```bash
   python run.py
   ```
6. **Acesse:** http://localhost:5000

## 🧪 Fluxo de teste

1. Home → clica em **ADM**
2. ADM → clica em **Desconexão** → vai para `/area/adm/desconexao/`
3. Hub Desconexão (6 cards) → clica em **Visão Executiva**
4. Carrega `/dash/executivo/` com KPIs + 6 gráficos
5. Brinca com os filtros (Safra, Tipo, Cidade, Status)

## 🔗 Endpoints novos

| URL | Função |
|---|---|
| `/area/adm/desconexao/` | Hub dos 6 dashboards do setor |
| `/dash/executivo/` | Dashboard Visão Executiva |
| `/dash/executivo/api/data?safra=...&tipo=...` | API JSON dos KPIs + figuras |

## 🧰 Stack

- **Backend:** Flask Blueprint (sem Dash)
- **Dados:** Pandas + SQLAlchemy + PyMySQL
- **Cache:** dicionário global em `data/db.py` (carrega 1x no primeiro acesso)
- **Gráficos:** Plotly Python (`px`/`go`) → JSON via `to_json()` → Plotly.js no front
- **Filtros:** Choices.js (CDN) com multi-seleção + busca + tags vermelhas
- **Loading:** overlay full-screen com spinner CSS
- **Debounce:** 250ms em mudanças de filtro pra não disparar requests demais

## 🔍 Se der erro

- **"Dados não disponíveis"**: verifique se `safra_final` existe no MySQL e tem dados
- **`ModuleNotFoundError: No module named 'pandas'`**: rode `pip install -r requirements.txt`
- **Gráficos em branco**: abra Console (F12) e veja se Plotly.js carregou (precisa internet)
- **Choices.js sem efeito**: idem, precisa de internet pro CDN funcionar
- **MySQL não conecta**: confirme que Laragon está com MySQL ativo e DB_URL em `data/db.py` está correto

## 🎯 Próximos passos

Se a POC ficar boa:
- ✅ **Aprovamos a Opção C** → seguimos pra FASE 2B (converter outros 5 dashboards)
- ❌ Se algo travar → voltamos pra estratégia A (DispatcherMiddleware com Dash)

Ordem sugerida da FASE 2B:
1. ~~dash_executivo~~ ✅ (esta POC)
2. dash_log
3. dash_parceiras
4. dash_backlog
5. dash_quebra
6. dash_retirada (por último, é o mais complexo)
