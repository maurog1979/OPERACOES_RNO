# Ferramentas

Execute os comandos a partir da raiz do projeto. Diagnósticos leem as credenciais de `.env`, igual ao portal.

```powershell
python tools/maintenance/sincronizar_projeto.py --status
python tools/maintenance/sincronizar_projeto.py --backup
python tools/maintenance/sincronizar_projeto.py --restore --file caminho/backup.sql
```

Sem argumentos, o comando mostra ajuda e não altera o banco. A restauração pede que seja digitado `RESTAURAR`; `--yes` só pode ser usado junto de `--restore` para confirmação explícita em automação. Não há mais seleção automática por nome de computador, sincronização implícita com OneDrive ou restauração na inicialização.

`mysql` e `mysqldump` devem estar no PATH, ou podem ser informados por `--mysql`/`--mysqldump` ou `MYSQL_BIN`/`MYSQLDUMP_BIN`. `--backup-dir` configura o destino; padrão: `database/dumps`. O último backup só é substituído após sucesso. A operação usa as credenciais `MYSQL_*` do portal.

Os scripts `criar_corrigir_dash_safra_fase3.py` e `substituir_plotall_dash_safra.py` são patches históricos. Não são necessários para instalar a versão atual e exigem `--apply-legacy-patch` para alterar arquivos. Prefira atualizar por Git. `dash_safra.html` é um template histórico; a rota ativa usa `dash_safra_v9_visual.html`.
