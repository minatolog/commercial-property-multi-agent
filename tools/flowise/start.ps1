param([int]$Port = 3000)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$runtime = (Get-ChildItem "$PSScriptRoot/.runtime" -Directory -Filter 'node-v*-win-x64' | Select-Object -First 1).FullName
if (!$runtime -or !(Test-Path 'node_modules/flowise/bin/run')) { throw 'Flowise runtime is not installed.' }
$env:PATH = "$runtime;$env:PATH"
New-Item -ItemType Directory -Force "$PSScriptRoot/.runtime/temp" | Out-Null
$env:TEMP = Join-Path $PSScriptRoot '.runtime/temp'
$env:TMP = $env:TEMP
$data = Join-Path $PSScriptRoot '.data'
New-Item -ItemType Directory -Force $data | Out-Null
$env:PORT = "$Port"
$env:HOST = '127.0.0.1'
$env:DATABASE_PATH = $data
$env:APIKEY_PATH = $data
$env:SECRETKEY_PATH = $data
$env:LOG_PATH = Join-Path $data 'logs'
$env:BLOB_STORAGE_PATH = Join-Path $data 'storage'
$env:DISABLE_FLOWISE_TELEMETRY = 'true'
if (Test-Path "$data/server.pid") {
    $existing = Get-Process -Id ([int](Get-Content "$data/server.pid")) -ErrorAction SilentlyContinue
    if ($existing -and $existing.ProcessName -eq 'node') { throw "Flowise process $($existing.Id) is already running." }
}
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $Port is already in use." }
$process = Start-Process -FilePath "$runtime/node.exe" -ArgumentList @('node_modules/flowise/bin/run', 'start') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$data/stdout.log" -RedirectStandardError "$data/stderr.log"
$process.Id | Set-Content "$data/server.pid"
Write-Output "Flowise PID $($process.Id): http://localhost:$Port"
