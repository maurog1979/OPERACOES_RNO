# Rotas

| Página | Endereço |
|---|---|
| Home | `/` |
| Área | `/area/<area_slug>` |
| Setor | `/area/<area_slug>/<setor_slug>` |
| Hub | `/area/adm/desconexao/` |
| Construção | `/area/<area_slug>/em-construcao` |

As áreas e setores desconhecidos retornam HTTP 404.

| Painel | Página | API |
|---|---|---|
| Executivo | `/dash/executivo/` | `api/options`, `api/data` |
| LOG | `/dash/log/` | `api/options`, `api/data` |
| Parceiras | `/dash/parceiras/` | `api/refresh` |
| Backlog | `/dash/backlog/` | `api/refresh` |
| Quebra | `/dash/quebra/` | `api/refresh`, `api/status` |
| Retirada | `/dash/retirada/` | `api/dados`, `api/reload` |
| Safra | `/dash/safra/` | `api/options`, `api/data`, `api/diagnostico` |

Os caminhos de API são relativos à página do painel. Endpoints `api/debug` de Backlog, Parceiras e Quebra exigem `ENABLE_DIAGNOSTICS=1`; a opção não implementa autenticação e deve ficar desativada em ambientes acessíveis a terceiros.
