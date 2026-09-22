param([Parameter(Mandatory=$true)][string]$Bundle)
$ErrorActionPreference = 'Stop'
$bundlePath = (Resolve-Path -LiteralPath $Bundle).Path
$projectPath = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$testRoot = Join-Path $projectPath ('desktop/build/portable-smoke-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$exe = Get-ChildItem -LiteralPath $bundlePath -Filter '*portable.exe' -File
if (@($exe).Count -ne 1) { throw 'Expected exactly one portable executable' }
New-Item -ItemType HardLink -Path (Join-Path $testRoot $exe.Name) -Target $exe.FullName | Out-Null
foreach ($name in @('JEV-runtime', 'JEV-models')) {
    New-Item -ItemType Junction -Path (Join-Path $testRoot $name) -Target (Join-Path $bundlePath $name) | Out-Null
}
Copy-Item -LiteralPath (Join-Path $bundlePath 'JEV') -Destination (Join-Path $testRoot 'JEV') -Recurse
$launcher = Start-Process -FilePath (Join-Path $testRoot $exe.Name) -WindowStyle Hidden -PassThru
$sessionPath = Join-Path $testRoot 'JEV-data/desktop-session.json'
$session = $null
try {
    $deadline = (Get-Date).AddSeconds(100)
    while (-not (Test-Path -LiteralPath $sessionPath)) {
        if ((Get-Date) -gt $deadline) { throw ('Startup timed out; inspect ' + $testRoot) }
        Start-Sleep -Milliseconds 250
    }
    $session = Get-Content -LiteralPath $sessionPath -Raw | ConvertFrom-Json
    $windowProcess = Get-Process -Id $session.pid
    if ($windowProcess.ProcessName -ne 'JEV') { throw 'Unexpected desktop process identity' }
    $backend = Get-CimInstance Win32_Process -Filter "ProcessId=$($session.backendPid)"
    if ($backend.ParentProcessId -ne $windowProcess.Id) { throw 'Unexpected backend parent' }
    if (-not $windowProcess.CloseMainWindow()) { throw 'Could not request normal window close' }
    if (-not $windowProcess.WaitForExit(30000)) { throw 'Desktop did not exit normally' }
    $deadline = (Get-Date).AddSeconds(15)
    while (Get-Process -Id $session.backendPid -ErrorAction SilentlyContinue) {
        if ((Get-Date) -gt $deadline) { throw 'Backend remained alive after window close' }
        Start-Sleep -Milliseconds 250
    }
    if (-not $launcher.WaitForExit(15000)) { throw 'Portable launcher did not exit' }
    $settingsPath = Join-Path $testRoot 'JEV-data/storage/web-sharing.json'
    if ((Test-Path -LiteralPath $settingsPath) -and (Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json).enabled) {
        throw 'A new installation unexpectedly enabled sharing'
    }
    [pscustomobject]@{ passed=$true; executable=$exe.Name; native_portable_started=$true; normal_window_close=$true;
        backend_exited=$true; default_sharing_disabled=$true; test_data=$testRoot } | ConvertTo-Json
} finally {
    if ($session) {
        $owned = Get-CimInstance Win32_Process -Filter "ProcessId=$($session.pid)" -ErrorAction SilentlyContinue
        if ($owned -and $owned.Name -eq 'JEV.exe') { Stop-Process -Id $owned.ProcessId -ErrorAction SilentlyContinue }
    }
    if (-not $launcher.HasExited) { Stop-Process -Id $launcher.Id -ErrorAction SilentlyContinue }
}
