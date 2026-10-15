@echo off
REM PILOTO DE MEDICAO — 07/10/2026, 12:15, horario de almoco.
REM
REM Sincroniza apenas os ultimos 2 dias para medir quanto tempo custa por
REM conversa, e com isso estimar a duracao da rodada noturna completa.
REM
REM Tres cuidados especificos deste teste:
REM
REM  --sem-marca   NAO grava a marca d'agua. Sem isso, um piloto que terminasse
REM                normalmente moveria a marca para hoje e a rodada da noite
REM                pularia 09/09 a 05/10 em silencio.
REM  SINC_MINUTOS  teto de 25 minutos. Acaba antes de a equipe voltar do almoco,
REM                de qualquer jeito.
REM  SINC_RITMO    o MESMO da noite (0,75s). Se mudasse, a medicao nao serviria
REM                para estimar coisa nenhuma.
REM
REM Para cancelar antes das 12:15:
REM     schtasks /delete /tn "QuestorCS-Piloto" /f
REM Para interromper durante:
REM     crie o arquivo D:\Projeto\QuestorCS\dados\PARE

cd /d D:\Projeto\QuestorCS
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

REM janela so deste teste; o guarda confere a cada chamada
set SINC_INICIO=13:06
set SINC_FIM=13:20
set SINC_MINUTOS=13
set SINC_RITMO=0.75

"C:\Users\cristian.andrioli\AppData\Local\Python\pythoncore-3.14-64\python.exe" src\noturno.py --agora --desde 2026-10-07 --sem-marca >> dados\piloto-detalhe.log 2>&1
exit /b %ERRORLEVEL%
