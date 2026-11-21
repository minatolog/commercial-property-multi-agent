$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot '.data/server.pid'
if (Test-Path $pidFile) {
    $server = Get-Process -Id ([int](Get-Content $pidFile)) -ErrorAction SilentlyContinue
    if ($server -and $server.ProcessName -eq 'node' -and $server.Path.StartsWith((Join-Path $PSScriptRoot '.runtime'))) {
        Stop-Process -Id $server.Id
        Write-Output 'Flowise stopped.'
    }
    Remove-Item -LiteralPath $pidFile
}
