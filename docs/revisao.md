# Revisão técnica do portal

Revisão dos 53 arquivos do repositório: aplicação, sete painéis, templates, CSS, documentação e ferramentas. As correções preservam a estrutura visual e os endpoints existentes.

## Correções

- Configuração `.env` carregada e exemplo alinhado com `MYSQL_*`; conexão aceita caracteres especiais na senha, UTF-8 e limites de espera.
- Depuração desativada e execução local limitada a `127.0.0.1` por padrão; `HOST` permite configurar o endereço.
- Registro explícito dos painéis: falhas de importação não são mais ocultadas como rotas inexistentes. Pré-carga opcional, sem banco obrigatório na inicialização.
- Cache compartilhado com expiração e cópias isoladas; liberação de conexões mesmo em caso de erro. Falhas de leitura não são armazenadas como dados vazios.
- Colunas de motivos e responsáveis do LOG incluídas na consulta otimizada.
- Valores nulos em categorias tratados antes dos filtros; Executivo reconhece recuperação numérica e textual; Backlog calcula aging também em bases pequenas.
- Datas ISO e brasileiras interpretadas sem inverter dia e mês. Quebras por dia/mês em ordem cronológica; valores de representatividade usam a mesma base do gráfico.
- Figuras de versões recentes de Plotly.py convertidas em listas compatíveis com Plotly.js 2.x.
- Safra: percentuais calculados pelos volumes, separação dos níveis de agregação, matriz acumulada por período em vez de sobrescrita, filtro de dia aplicado ao acumulado diário e necessidade diária somada por dimensão no período mais recente. GAP exibido com a chave correta.
- Links de retorno corrigidos; rótulos de filtros tratados como texto; matriz Safra escapa HTML e ignora respostas antigas. Carregamento deixa de bloquear a tela em caso de erro.
- Diagnósticos detalhados desativados por padrão; mensagens de falha não expõem rastreamentos e detalhes de conexão ao navegador.
- Retirada exige a coluna `TEM_TOA` para não incluir contratos fora do universo definido e não repete a execução de uma rota que falhe com `AttributeError`.
- Ferramentas de diagnóstico usam a configuração do portal e caminhos relativos ao repositório. Backup/restauração usam argumentos separados, sem shell, e a restauração exige comando e confirmação explícitos. Patches históricos que alteram templates exigem `--apply-legacy-patch`.

## Validação e limites

Validação concluída: 34 testes automatizados passaram, usando dados sintéticos e conexões simuladas. Cobrem navegação, APIs, nulos, cache, falhas de banco, cálculos, datas, JavaScript dos templates e rotinas de manutenção. O teste de JavaScript requer Node.js e é pulado quando não está instalado. Não executam operações no banco real.

No navegador Microsoft Edge, os sete painéis renderizaram os 40 gráficos esperados, sem erros de JavaScript; foi selecionado um filtro em cada painel. Uma resposta HTTP 503 simulada na Safra exibiu a falha e removeu a camada de carregamento. Foram removidos patches antigos da tela de Retirada que continham JavaScript inválido e alteravam links indevidamente.

O repositório não inclui DDL, migrações, ETL nem amostra anonimizada do MySQL. É necessário validar em homologação os nomes/tipos das colunas, os tempos de consulta e os indicadores contra o banco real. Na Safra, o cálculo considera `meta_qtd` uma quantidade e `meta_percentual` em escala de 0 a 100; usa um único nível geográfico por período/safra/tipo, priorizando CIDADE, depois UF e RNO. A completude desses níveis precisa ser conferida com o responsável pelos dados.

Autenticação completa continua como funcionalidade pendente do projeto; o nome exibido na barra não representa um usuário autenticado. Publicação, criação de usuários e alterações no banco não fazem parte desta revisão. Recursos de gráficos, filtros e fontes ainda dependem de CDNs.
