@echo off
REM Sincronizacao noturna com o Q-Desk. Disparada pelo Agendador de Tarefas
REM do Windows as 20:00. Os freios estao em src\guarda.py: janela de horario,
REM ritmo folgado, freio de latencia, teto de chamadas e o arquivo dados\PARE.
REM
REM Para cancelar a execucao de hoje, antes das 20h:
REM     schtasks /delete /tn "QuestorCS-Sincronizacao" /f
REM Para interromper durante a madrugada, de qualquer lugar:
REM     crie o arquivo D:\Projeto\QuestorCS\dados\PARE
REM
REM Dois registros, de proposito:
REM   dados\sincronizacao.log          o essencial: inicio, freios, fim, motivo
REM   dados\sincronizacao-detalhe.log  a saida completa, pagina a pagina
REM O primeiro e escrito pelo proprio programa e nao depende deste arquivo.

cd /d D:\Projeto\QuestorCS
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
"C:\Users\cristian.andrioli\AppData\Local\Python\pythoncore-3.14-64\python.exe" src\noturno.py >> dados\sincronizacao-detalhe.log 2>&1
exit /b %ERRORLEVEL%
