param(
    [string]$Manifest = 'JevWikiBookDownloads-0.6.2.json',
    [string]$OutputDirectory = $PSScriptRoot,
    [switch]$VerifyOnly
)
$ErrorActionPreference = 'Stop'
$metadata = Get-Content -LiteralPath (Join-Path $PSScriptRoot $Manifest) -Raw -Encoding UTF8 | ConvertFrom-Json
if ($metadata.archive.name -ne [IO.Path]::GetFileName($metadata.archive.name) -or -not $metadata.archive.name.EndsWith('.zip')) {
    throw 'Invalid archive filename in manifest.'
}
$orderedParts = @($metadata.parts)
if ($orderedParts.Count -lt 1) { throw 'Manifest has no parts.' }
$completeHash = [Security.Cryptography.SHA256]::Create()
$buffer = New-Object byte[] (4 * 1024 * 1024)
try {
    foreach ($part in $orderedParts) {
        if ($part.name -ne [IO.Path]::GetFileName($part.name)) { throw 'Invalid part filename.' }
        $partPath = Join-Path $PSScriptRoot $part.name
        if ((Get-Item -LiteralPath $partPath).Length -ne $part.size) { throw "Wrong size: $($part.name)" }
        if ((Get-FileHash -LiteralPath $partPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $part.sha256) {
            throw "Checksum mismatch: $($part.name)"
        }
        $inputPart = [IO.File]::OpenRead($partPath)
        try {
            while (($count = $inputPart.Read($buffer, 0, $buffer.Length)) -gt 0) {
                [void]$completeHash.TransformBlock($buffer, 0, $count, $buffer, 0)
            }
        } finally { $inputPart.Dispose() }
        Write-Host "Verified $($part.name)"
    }
    [void]$completeHash.TransformFinalBlock([byte[]]@(), 0, 0)
    $combined = [BitConverter]::ToString($completeHash.Hash).Replace('-', '').ToLowerInvariant()
    if ($combined -ne $metadata.archive.sha256) { throw 'Combined ZIP checksum mismatch.' }
} finally { $completeHash.Dispose() }
if ($VerifyOnly) { Write-Host 'All parts reconstruct the original ZIP exactly.'; return }
$destination = Join-Path (Resolve-Path -LiteralPath $OutputDirectory).Path $metadata.archive.name
if (Test-Path -LiteralPath $destination) {
    if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -eq $metadata.archive.sha256) {
        Write-Host "Already verified: $destination"; return
    }
    throw 'Output ZIP already exists with different contents. Choose another output directory.'
}
$temporary = $destination + '.' + [Guid]::NewGuid().ToString('N') + '.partial'
$outputZip = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try {
    foreach ($part in $orderedParts) {
        $inputPart = [IO.File]::OpenRead((Join-Path $PSScriptRoot $part.name))
        try { $inputPart.CopyTo($outputZip) } finally { $inputPart.Dispose() }
    }
} finally { $outputZip.Dispose() }
if ((Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant() -ne $metadata.archive.sha256) {
    throw "Merged checksum mismatch; incomplete output retained at $temporary"
}
Move-Item -LiteralPath $temporary -Destination $destination
Write-Host "Ready: $destination"
Write-Host 'Extract the entire ZIP, then run the portable EXE with JEV-runtime and JEV-models beside it.'
