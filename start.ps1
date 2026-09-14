param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$satRoot = $PSScriptRoot
$satUrl = 'http://127.0.0.1:8765'
try {
    $satHealth = Invoke-RestMethod -Uri "$satUrl/api/meta" -TimeoutSec 2
    if ($satHealth.domains.Count -eq 4) {
        if (-not $NoBrowser) { Start-Process $satUrl }
        exit 0
    }
} catch { }
$satPython = $null
$satCandidates = @('py', 'python', (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'))
foreach ($satCandidate in $satCandidates) {
    $satCommand = Get-Command $satCandidate -ErrorAction SilentlyContinue
    if ($satCommand) {
        try {
            & $satCommand.Source -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { $satPython = $satCommand.Source; break }
        } catch { }
    }
}
if (-not $satPython) { throw 'Install Python 3.10 or newer from https://www.python.org/downloads/, then open Start SAT again.' }
Start-Process -FilePath $satPython -ArgumentList @('"' + (Join-Path $satRoot 'server.py') + '"') -WorkingDirectory $satRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $satRoot 'server.log') -RedirectStandardError (Join-Path $satRoot 'server-error.log')
for ($satTry = 0; $satTry -lt 30; $satTry++) {
    Start-Sleep -Milliseconds 200
    try {
        $satHealth = Invoke-RestMethod -Uri "$satUrl/api/meta" -TimeoutSec 1
        if ($satHealth.domains.Count -eq 4) { if (-not $NoBrowser) { Start-Process $satUrl }; exit 0 }
    } catch { }
}
throw 'The trainer did not start. Check server-error.log in this folder.'
