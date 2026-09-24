@echo off
REM =====================================================================
REM PORTAL OPERACOES RNO
REM registrar_tarefa.bat - Registra a carga diaria no Agendador
REM =====================================================================
REM
REM EXECUTE UMA UNICA VEZ, COMO ADMINISTRADOR
REM   Clique com o botao direito neste arquivo
REM   Escolha "Executar como administrador"
REM
REM O QUE FAZ
REM   Cria a tarefa "Portal RNO - Backlog Diario" no Agendador de
REM   Tarefas do Windows, configurada para rodar todos os dias as 10h05.
REM
REM PARA REMOVER DEPOIS
REM   schtasks /delete /tn "Portal RNO - Backlog Diario" /f
REM =====================================================================

setlocal

set NOME_TAREFA=Portal RNO - Backlog Diario
set PROJETO=C:\Users\n5996917\OneDrive - Claro SA\INTRANET\OPERACOES_RNO
set SCRIPT=%PROJETO%\etl\agendar_backlog.bat
set HORARIO=10:05

echo.
echo ============================================================
echo   REGISTRO DA TAREFA AGENDADA
echo ============================================================
echo.
echo   Nome    : %NOME_TAREFA%
echo   Script  : %SCRIPT%
echo   Horario : %HORARIO%  (todos os dias)
echo.

REM ---- verifica se o script existe ----
if not exist "%SCRIPT%" (
    echo   ERRO: script nao encontrado
    echo   %SCRIPT%
    echo.
    pause
    exit /b 1
)

REM ---- verifica se ja existe a tarefa ----
schtasks /query /tn "%NOME_TAREFA%" >nul 2>&1
if %errorlevel%==0 (
    echo   A tarefa ja existe. Removendo a versao anterior...
    schtasks /delete /tn "%NOME_TAREFA%" /f >nul 2>&1
    echo.
)

REM ---- cria a tarefa ----
schtasks /create ^
    /tn "%NOME_TAREFA%" ^
    /tr "\"%SCRIPT%\" auto" ^
    /sc daily ^
    /st %HORARIO% ^
    /rl highest ^
    /f

if %errorlevel%==0 (
    echo.
    echo   ============================================================
    echo   TAREFA REGISTRADA COM SUCESSO
    echo   ============================================================
    echo.
    echo   A carga vai rodar automaticamente todos os dias as %HORARIO%
    echo.
    echo   COMANDOS UTEIS:
    echo.
    echo     Ver a tarefa:
    echo       schtasks /query /tn "%NOME_TAREFA%"
    echo.
    echo     Executar agora, sem esperar:
    echo       schtasks /run /tn "%NOME_TAREFA%"
    echo.
    echo     Remover:
    echo       schtasks /delete /tn "%NOME_TAREFA%" /f
    echo.
) else (
    echo.
    echo   FALHA AO REGISTRAR
    echo.
    echo   Verifique se este arquivo foi executado COMO ADMINISTRADOR.
    echo   Clique com o botao direito e escolha
    echo   "Executar como administrador".
    echo.
)

pause
