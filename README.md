# Portal Operações RNO

Plataforma de inteligência operacional da Regional Norte da Claro.

## Como rodar

```bash
pip install -r requirements.txt
python run.py
```

Acesse: http://localhost:5000

## Arquitetura em 3 níveis

- **Nível 1 (Home)**: escolha de ÁREA (8 áreas)
- **Nível 2 (Área)**: escolha de SETOR (quando existir)
- **Nível 3 (Setor)**: dashboards específicos

## Rotas

| Rota | Descrição |
|---|---|
| `/` | Home com 8 áreas |
| `/area/<area>` | Página da área (setores ou construção) |
| `/area/<area>/<setor>` | Setor específico |
| `/area/<area>/em-construcao` | Placeholder |
| `/dash/executivo/` | Dashboard Executivo (Desconexão) |
| `/dash/log/` | Dashboard Log (Desconexão) |
| `/dash/parceiras/` | Dashboard Parceiras (Desconexão) |
| `/dash/backlog/` | Dashboard Backlog (Desconexão) |
| `/dash/quebra/` | Dashboard Quebra (Desconexão) |
| `/dash/retirada/` | Dashboard Retirada |
| `/dash/safra/` | Painel Safra |

## Configuração de Banco

As credenciais do MySQL são lidas de variáveis de ambiente (com fallback para dev):

```
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=safra
SECRET_KEY=...
```

## 8 Áreas

1. **ADM** (ATIVO) — Administrativo · 2 setores (Desconexão, Segurança)
2. OMR — Operação e Monitoramento de Rede
3. INFRA — Infraestrutura de rede e datacenter
4. IMPLANTAÇÃO — Projetos e implantações
5. REDE EXTERNA — Planta externa
6. RESIDENCIAL — Clientes residenciais
7. EMPRESARIAL — Clientes corporativos
8. BACKBONE — Espinha dorsal da rede

## Fases

- [x] **FASE 1**: Arquitetura navegável (esta entrega)
- [ ] **FASE 2**: Migrar 6 dashboards do PORTAL_DESCONEXAO para `areas/adm/desconexao/`
- [ ] **FASE 3**: Autenticação (Flask-Login)
- [ ] **FASE 4**: Hospedagem VPS + domínio operacoesrno.com.br
- [ ] **FASE 5**: Arquivar PORTAL_DESCONEXAO antigo