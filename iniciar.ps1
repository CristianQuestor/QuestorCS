<#
    Sobe o painel CS Questor em http://localhost:8050

    Regera a pagina antes de servir, para nao publicar uma versao velha sem
    perceber. Se as metricas ainda nao existirem, avisa e para: e melhor falhar
    aqui do que servir um painel vazio.

    Uso:
        .\iniciar.ps1              regera e sobe
        .\iniciar.ps1 -Rapido      sobe sem regerar
        .\iniciar.ps1 -Porta 8060  outra porta
#>
param(
    [switch]$Rapido,
    [int]$Porta = 8050
)

$ErrorActionPreference = "Stop"
$raiz = $PSScriptRoot

function Certo($m) { Write-Host "  [v] $m" -ForegroundColor Green }
function Falha($m) { Write-Host "  [x] $m" -ForegroundColor Red; exit 1 }

Write-Host "`n== Painel CS Questor ==`n"

if (-not $Rapido) {
    if (-not (Test-Path (Join-Path $raiz "dados\dashboard.json"))) {
        Falha "dados\dashboard.json nao existe. Rode antes: python src\metricas.py"
    }
    python (Join-Path $raiz "src\painel.py")
    if ($LASTEXITCODE -ne 0) { Falha "a geracao do painel falhou" }
    Certo "painel regerado"
}

$ocupada = Get-NetTCPConnection -LocalPort $Porta -State Listen -ErrorAction SilentlyContinue
if ($ocupada) {
    Falha "a porta $Porta ja esta em uso pelo PID $($ocupada[0].OwningProcess)"
}

Certo "abrindo http://localhost:$Porta/"
python (Join-Path $raiz "servidor.py") --porta $Porta
