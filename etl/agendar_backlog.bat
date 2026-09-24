@echo off
REM =====================================================================
REM PORTAL OPERACOES RNO - DATA MART DESCONEXAO
REM agendar_backlog.bat - Executa a carga diaria do Backlog
REM =====================================================================
REM
REM O QUE FAZ
REM   Chama o etl_backlog_diario.py, que le o BACKLOG_OS.csv e acumula
REM   a foto do dia no ft_backlog_log.
REM
REM QUANDO RODA
REM   Todos os dias as 10h05, via Agendador de Tarefas do Windows.
REM   O arquivo e atualizado as 10h, entao damos 5 minutos de folga.
REM
REM COMO REGISTRAR NO AGENDADOR
REM   Execute uma vez, como administrador:
REM       registrar_tarefa.bat
REM
REM   Ou manualmente:
REM       1. Abra o Agendador de Tarefas
REM       2. Criar Tarefa Basica
REM       3. Nome: Portal RNO - Backlog Diario
REM       4. Disparador: Diariamente, 10:05
REM       5. Acao: Iniciar um programa
REM       6. Programa: caminho completo deste .bat
REM
REM TESTE MANUAL
REM   Basta dar duplo clique neste arquivo.
REM =====================================================================

setlocal

REM ---- caminho do projeto ----
set PROJETO=C:\Users\n5996917\OneDrive - Claro SA\INTRANET\OPERACOES_RNO
set PASTA_ETL=%PROJETO%\etl

REM ---- vai para a pasta do ETL ----
cd /d "%PASTA_ETL%"

if errorlevel 1 (
    echo ERRO: pasta nao encontrada
    echo %PASTA_ETL%
    exit /b 1
)

REM ---- executa ----
echo.
echo ============================================================
echo   CARGA DIARIA DO BACKLOG
echo   %date% %time%
echo ============================================================
echo.

python etl_backlog_diario.py

set RESULTADO=%errorlevel%

echo.
if %RESULTADO%==0 (
    echo CONCLUIDO COM SUCESSO
) else if %RESULTADO%==2 (
    echo AVISO: arquivo BACKLOG_OS.csv nao encontrado
) else (
    echo ERRO na execucao - codigo %RESULTADO%
    echo Consulte a pasta logs para detalhes
)

echo.

REM ---- quando executado manualmente, mantem a janela aberta ----
if "%1"=="" (
    if not defined TAREFA_AGENDADA pause
)

exit /b %RESULTADO%
