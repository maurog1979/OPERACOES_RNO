# Instalação

Use Python 3.10+ e instale `requirements.txt` em ambiente virtual. Copie `.env.example` para `.env` e configure `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD` e `MYSQL_DATABASE`. Use uma `SECRET_KEY` aleatória e estável no servidor.

Execute `python run.py` e acesse http://127.0.0.1:5000. Para acesso pela rede local, defina `HOST=0.0.0.0` explicitamente. Não habilite `FLASK_DEBUG` em ambientes compartilhados.

O arquivo `.env` é lido a partir da raiz do projeto, independentemente do diretório corrente. Ele não deve ser versionado. A ausência de MySQL não impede a navegação; as consultas aos painéis precisam das tabelas listadas no README. DDL, ETL e dados de produção não estão incluídos.

Para validar o código: `python -m pip install -r requirements-dev.txt` e `python -m pytest -q`.
