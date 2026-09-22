$ErrorActionPreference = 'Stop'
$jevFolder = $PSScriptRoot
$jevManifest = Get-Content -LiteralPath (Join-Path $jevFolder 'JEV-models-0.6.0-downloads.json') -Raw | ConvertFrom-Json
$jevOutput = Join-Path $jevFolder 'JEV-models-0.6.0.zip'
if (Test-Path -LiteralPath $jevOutput) { throw 'Output ZIP already exists; keep it or choose another folder.' }
foreach ($jevPart in $jevManifest.parts) {
    if ($jevPart.name -notmatch '^JEV-models-0\.6\.0\.zip\.\d{3}$') { throw 'Invalid archive part name' }
    $jevPath = Join-Path $jevFolder $jevPart.name
    if ((Get-Item -LiteralPath $jevPath).Length -ne $jevPart.bytes -or (Get-FileHash -LiteralPath $jevPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $jevPart.sha256) { throw ('Checksum mismatch: ' + $jevPart.name) }
}
$jevStream = [IO.File]::Open($jevOutput + '.partial', [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
try {
    foreach ($jevPart in $jevManifest.parts) {
        $jevInput = [IO.File]::OpenRead((Join-Path $jevFolder $jevPart.name))
        try { $jevInput.CopyTo($jevStream) } finally { $jevInput.Dispose() }
    }
} finally { $jevStream.Dispose() }
if ((Get-FileHash -LiteralPath ($jevOutput + '.partial') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $jevManifest.sha256) { throw 'Combined ZIP checksum mismatch; partial file retained for inspection.' }
Move-Item -LiteralPath ($jevOutput + '.partial') -Destination $jevOutput
Write-Host 'Verified models ZIP is ready. Extract JEV-models beside the application executable.'
