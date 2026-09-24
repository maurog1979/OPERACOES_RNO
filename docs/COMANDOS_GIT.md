# Sincronização do Data Mart Desconexão

Sequência de comandos para versionar o trabalho pendente.
Execute na raiz do projeto, um bloco por vez.

```
cd /d "C:\Users\n5996917\OneDrive - Claro SA\INTRANET\OPERACOES_RNO"
```

---

## Passo 1 — Substituir o .gitignore

Baixe o `.gitignore` corrigido e substitua o atual.

**O que muda:** a regra `*.sql` estava bloqueando o DDL do Data Mart.
Agora há exceção para `database/` e `docs/database/`, que são código.
Também removi três blocos duplicados.

Confirme que o DDL passou a ser visto:

```cmd
git status --short docs/database/
```

Deve aparecer `?? docs/database/01_ddl_desconexao_rno.sql`.
Se não aparecer, o `.gitignore` não foi substituído.

---

## Passo 2 — Mover os diagnósticos para tools/

Três scripts estão soltos na raiz. O lugar deles é `tools/`.

```cmd
git mv diagnosticar_pipelines_escrita_mysql.py tools\diagnostics\ 2>nul || move diagnosticar_pipelines_escrita_mysql.py tools\diagnostics\
move inventariar_pipelines_desconexao.py tools\diagnostics\
move diag_03_engenharia_reversa.py tools\diagnostics\
```

Os diagnósticos do ETL ficam junto do ETL, que é onde são usados:

```cmd
move etl\diag_01_perfilar.py tools\diagnostics\
move etl\diag_02_datas_quebra.py tools\diagnostics\
```

---

## Passo 3 — Remover os patches temporários

Já cumpriram o papel. O `.gitignore` novo bloqueia `patch_*.py`,
mas os arquivos ainda existem no disco.

```cmd
del areas\adm\desconexao\templates\patch_altura_graficos.py
del areas\adm\desconexao\templates\patch_safra_todas.py
del data\patch_filtros.py
```

---

## Passo 4 — Commit do .gitignore

Primeiro isolado, para as regras valerem nos commits seguintes.

```cmd
git add .gitignore
git commit -m "chore: corrige gitignore que bloqueava DDL do banco"
```

---

## Passo 5 — Commit do ETL

Toda a camada de carga do Data Mart.

```cmd
git add etl/etl_config.py
git add etl/etl_02_carga_staging.py
git add etl/etl_04_carga_fatos.py
git add etl/etl_backlog_diario.py
git add etl/agendar_backlog.bat
git add etl/registrar_tarefa.bat

git commit -m "feat(etl): pipeline do Data Mart desconexao_rno

- carga de staging com deteccao de encoding e mapeamento de colunas
- carga dos fatos com validacao anti-multiplicacao e rollback
- carga diaria do backlog com protecao contra duplicidade
- agendador para execucao automatica as 10h05"
```

---

## Passo 6 — Commit do banco

Scripts de estrutura e views.

```cmd
git add docs/database/
git commit -m "feat(db): DDL e views do Data Mart desconexao_rno"
```

---

## Passo 7 — Commit da camada de dados

```cmd
git add data/db_desconexao.py
git commit -m "feat(data): conexao com o Data Mart desconexao_rno

Engine proprio, separado do banco legado, para coexistencia.
Cache com TTL e tratamento de collation nas comparacoes."
```

---

## Passo 8 — Commit dos dashboards novos

```cmd
git add areas/adm/desconexao/dash_safra_painel.py
git add areas/adm/desconexao/templates/dash_safra_painel.html
git add areas/adm/desconexao/dash_backlog_rno.py
git add areas/adm/desconexao/templates/dash_backlog_rno.html

git commit -m "feat(dash): painel Safra e Backlog sobre o Data Mart

Painel Safra replica a planilha executiva com ICG e farol 65/60.
Backlog mostra os contratos da Safra distribuidos na agenda."
```

---

## Passo 9 — Commit do registro no app

```cmd
git add app.py
git commit -m "feat(app): registra blueprints dos dashboards novos"
```

---

## Passo 10 — Commit dos utilitários de parceira

```cmd
git add areas/adm/desconexao/partner_key_utils.py
git add areas/adm/desconexao/toa_partner_mapping.py
git commit -m "feat: utilitarios de normalizacao de parceiras"
```

---

## Passo 11 — Commit do layout

Alterações visuais que estavam pendentes.

```cmd
git add templates/
git add static/css/
git add static/js/
git add static/img/

git commit -m "style: ajustes de layout e assets do portal"
```

---

## Passo 12 — Commit das alterações do legado

```cmd
git add areas/adm/desconexao/dash_executivo.py
git add areas/adm/desconexao/templates/dash_backlog.html
git add areas/adm/desconexao/templates/dash_executivo.html
git add data/db.py

git commit -m "fix: ajustes nos dashboards legados"
```

---

## Passo 13 — Remover o arquivo deletado

```cmd
git rm INSTRUCOES_PATCH.md
git commit -m "chore: remove instrucoes de patch obsoletas"
```

---

## Passo 14 — Conferir antes de enviar

```cmd
git status
```

Deve mostrar a árvore limpa, sem nada pendente.
Se sobrar algo, avalie caso a caso antes de adicionar.

```cmd
git log --oneline -12
```

Confirma os commits criados, do mais recente ao mais antigo.

---

## Passo 15 — Enviar

```cmd
git push origin feature/layout-executivo
```

---

## Depois: merge para main

Quando validar que está tudo certo:

```cmd
git checkout main
git pull origin main
git merge feature/layout-executivo
git push origin main
```

Ou abra um Pull Request no GitHub, que é o caminho recomendado
por deixar registro da revisão.

---

## Comandos de conferência

```cmd
git status --short
```
Visão compacta do que mudou.

```cmd
git diff --stat
```
Quantas linhas foram alteradas em cada arquivo.

```cmd
git check-ignore -v caminho/do/arquivo
```
Mostra qual regra do `.gitignore` está bloqueando um arquivo.
Útil se algo que deveria ser versionado não aparecer.

```cmd
git log --oneline --graph -15
```
Histórico com ramificações.

---

## Se algo der errado

Desfazer um `git add` antes do commit:

```cmd
git restore --staged caminho/do/arquivo
```

Desfazer o último commit mantendo as alterações:

```cmd
git reset --soft HEAD~1
```

Ver o que um commit mudou:

```cmd
git show <hash>
```
