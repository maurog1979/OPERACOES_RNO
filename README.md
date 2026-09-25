# Portal Operações RNO

Portal Flask de indicadores operacionais da Regional Norte, com oito áreas de navegação e sete painéis disponíveis em ADM → Desconexão.

## Executar localmente

Requer Python 3.10 ou superior e um MySQL com as tabelas da operação.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Preencha MYSQL_* e SECRET_KEY no .env.
python run.py
```

Abra http://127.0.0.1:5000. O portal carrega `.env` automaticamente; variáveis existentes no ambiente têm prioridade. As páginas abrem sem pré-carregar o banco, e os painéis informam falhas ao consultar os dados.

## Painéis e dados

| Painel | Endereço | Fonte |
|---|---|---|
| Executivo | `/dash/executivo/` | `safra_final` |
| LOG | `/dash/log/` | `safra_enriquecida` |
| Parceiras | `/dash/parceiras/` | `safra_enriquecida`, `cidades_uf` quando UF estiver ausente |
| Backlog | `/dash/backlog/` | `safra_enriquecida` |
| Quebra | `/dash/quebra/` | `quebra_total` |
| Retirada | `/dash/retirada/` | `safra_enriquecida`, somente `TEM_TOA = SIM` |
| Safra | `/dash/safra/` | `safra_resumo_mensal`, `safra_resumo_diario` |

O repositório não inclui criação nem carga dessas tabelas. Veja [instalação](docs/installation.md), [rotas](docs/routes.md) e [revisão técnica](docs/revisao.md).

## Testes

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Os testes usam dados sintéticos e não acessam o MySQL real.

## Configuração

- `CACHE_TTL_SECONDS=300`: validade do cache em segundos; `0` desativa sua reutilização.
- `PRELOAD_DATA=0`: permite iniciar o portal sem consultar o banco; `1` ativa pré-carga.
- `FLASK_DEBUG=0`: depuração desativada por padrão.
- `HOST=127.0.0.1` e `PORT=5000`: endereço de desenvolvimento.
- `ENABLE_DIAGNOSTICS=0`: mantém endpoints de diagnóstico detalhado indisponíveis.

Autenticação e implantação de produção ainda são etapas pendentes. O nome na barra superior é configuração visual, sem autenticação de usuário. Os recursos visuais dependem de CDNs. Para publicar, configure autenticação/controle de acesso e um servidor WSGI; `run.py` é o ponto de entrada para desenvolvimento.
