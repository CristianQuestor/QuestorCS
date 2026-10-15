@echo off
REM ===================================================================
REM  SINCRONIZACAO DE 1 SEMANA — disparo MANUAL, com voce presente.
REM
REM  Nao existe tarefa agendada. Nada aqui roda sozinho: so executa se
REM  alguem abrir este arquivo.
REM
REM  Traz do Q-Desk o que mudou nos ultimos 7 dias (corte em 30/09 12:00),
REM  para medir quanto tempo custa uma semana. Com esse numero voce decide
REM  se vale rodar as outras tres.
REM
REM  --sem-marca  A marca d'agua NAO avanca. Isto e essencial: sem ela,
REM               sincronizar so a ultima semana moveria a marca para hoje
REM               e o periodo de 09/09 a 30/09 ficaria perdido, em silencio.
REM               Com ela, a base continua sabendo que deve 09/09 em diante.
REM
REM  Freios ativos: janela 20:00-05:30, ritmo de 0,75s entre chamadas,
REM  parada automatica se a instancia ficar lenta, e o arquivo dados\PARE.
REM
REM  PARA INTERROMPER a qualquer momento:
REM     feche esta janela, ou crie o arquivo D:\Projeto\QuestorCS\dados\PARE
REM  Parar e seguro em qualquer ponto: nada se perde e nada fica pela metade.
REM ===================================================================

cd /d D:\Projeto\QuestorCS
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

set SINC_INICIO=20:00
set SINC_FIM=05:30
set SINC_RITMO=0.75

echo.
echo  Sincronizando 1 semana (30/09 a hoje). Acompanhe abaixo.
echo  Para interromper: feche esta janela ou crie dados\PARE
echo.

powershell -NoProfile -Command "& { & 'C:\Users\cristian.andrioli\AppData\Local\Python\pythoncore-3.14-64\python.exe' src\noturno.py --desde 2026-10-02 --sem-marca 2>&1 | Tee-Object -FilePath dados\sincronizacao-detalhe.log -Append }"

echo.
echo  ===== terminou. O resumo acima tem o tempo e o que foi trazido. =====
echo  O registro completo fica em dados\sincronizacao-detalhe.log
pause
