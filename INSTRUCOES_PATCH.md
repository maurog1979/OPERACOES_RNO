# Atualização do portal

As antigas instruções de extração de ZIP descreviam uma fase de migração já concluída. Os sete painéis estão registrados em `app.py`.

1. Atualize o código pela alteração revisada no GitHub.
2. Instale `requirements.txt` no ambiente virtual.
3. Confira `.env` usando `.env.example` como referência, sem substituir suas credenciais.
4. Execute os testes de `requirements-dev.txt` e reinicie o serviço.
5. Confira os sete painéis em homologação, com o banco da operação, antes da implantação.

Consulte [a revisão](docs/revisao.md) para correções, hipóteses dos indicadores e limitações de validação. Não reaplique os antigos scripts de substituição de templates sobre a versão atual.
