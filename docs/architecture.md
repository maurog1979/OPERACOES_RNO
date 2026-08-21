# Arquitetura do Portal Operacoes RNO

## Modelo funcional

```text
Portal
+-- Area
    +-- Setor
        +-- Dashboard
```

## Componentes

- `app.py`: criacao e configuracao da aplicacao Flask.
- `run.py`: inicializacao local.
- `areas/`: modulos por area e setor.
- `routes/`: navegacao geral.
- `data/`: conexoes, cache e acesso a dados.
- `templates/`: templates globais.
- `static/`: CSS, JavaScript e imagens globais.
- `tools/`: diagnosticos, migracoes, instaladores, manutencao e validadores.
- `reports/`: relatorios oficiais e gerados.
- `tests/`: testes automatizados.

A branch `main` deve conter somente codigo validado.
