[CmdletBinding()]
param(
    [string]$ModelRoot = 'D:\Comfy-Desktop\ComfyUI-Shared\models',
    [string]$Proxy = 'http://127.0.0.1:9567',
    [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'
$repositoryPath = 'larryvrh/MiniMax-H3-Turbo-Lora'
$fileName = 'minimax_h3_turbo_v4_step600_ema.safetensors'
$expectedBytes = [int64]779849816
$expectedSha256 = '5f3a626cd72c93a8b9318d6760c510bc5092d2ab13aaba1f932c5bab07a416d3'

$sources = @(
    [pscustomobject]@{Name = 'ModelScope mirror'; Url = "https://modelscope.cn/models/$repositoryPath/resolve/master/$fileName"},
    [pscustomobject]@{Name = 'HF-Mirror'; Url = "https://hf-mirror.com/$repositoryPath/resolve/main/$fileName"},
    [pscustomobject]@{Name = 'Hugging Face official'; Url = "https://huggingface.co/$repositoryPath/resolve/main/$fileName"}
)

function Invoke-Curl {
    param([Parameter(Mandatory)][string[]]$Arguments)
    & curl.exe @Arguments
    return $LASTEXITCODE
}

function Test-Source {
    param([Parameter(Mandatory)][pscustomobject]$Source)
    $arguments = @('--location', '--fail', '--silent', '--show-error', '--max-time', '20', '--range', '0-0', '--output', 'NUL')
    if ($Proxy) {$arguments += @('--proxy', $Proxy)}
    $arguments += $Source.Url
    return ((Invoke-Curl -Arguments $arguments) -eq 0)
}

function Test-CompletedFile {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {return $false}
    if ((Get-Item -LiteralPath $Path).Length -ne $expectedBytes) {return $false}
    return ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -eq $expectedSha256)
}

if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {throw 'curl.exe is required but was not found.'}

Write-Host "Target: $fileName"
Write-Host "Proxy:  $Proxy"
Write-Host 'Source order: ModelScope mirror -> HF-Mirror -> Hugging Face official'

$availableSources = @()
foreach ($source in $sources) {
    Write-Host -NoNewline "Checking $($source.Name)... "
    if (Test-Source -Source $source) {
        Write-Host 'OK'
        $availableSources += $source
    }
    else {
        Write-Host 'FAILED'
    }
}
if ($availableSources.Count -eq 0) {throw 'No Turbo LoRA source passed the preflight check.'}
if ($PreflightOnly) {
    Write-Host "Preflight complete: $($availableSources.Count)/$($sources.Count) sources available."
    exit 0
}

$targetDirectory = Join-Path $ModelRoot 'loras'
$targetPath = Join-Path $targetDirectory $fileName
$partialPath = "$targetPath.part"

if (Test-Path -LiteralPath $targetPath -PathType Leaf) {
    Write-Host "Verifying existing file: $targetPath"
    if (Test-CompletedFile -Path $targetPath) {Write-Host 'Existing file is valid; skipping.'; exit 0}
    throw "An invalid final file already exists: $targetPath. It was not overwritten."
}
if (-not (Test-Path -LiteralPath $targetDirectory -PathType Container)) {New-Item -ItemType Directory -Path $targetDirectory | Out-Null}
if (Test-Path -LiteralPath $partialPath -PathType Leaf) {
    $partialLength = (Get-Item -LiteralPath $partialPath).Length
    if ($partialLength -gt $expectedBytes) {throw "Partial file is larger than expected: $partialPath"}
    Write-Host "Resuming at $partialLength bytes."
}

$downloadSucceeded = $false
foreach ($source in $availableSources) {
    Write-Host "Downloading from $($source.Name)..."
    $arguments = @('--location', '--fail', '--show-error', '--retry', '8', '--retry-connrefused', '--retry-delay', '5', '--connect-timeout', '20', '--speed-time', '120', '--speed-limit', '1024', '--continue-at', '-', '--output', $partialPath)
    if ($Proxy) {$arguments += @('--proxy', $Proxy)}
    $arguments += $source.Url
    $exitCode = Invoke-Curl -Arguments $arguments
    if ($exitCode -eq 0 -and (Test-Path -LiteralPath $partialPath -PathType Leaf) -and (Get-Item -LiteralPath $partialPath).Length -eq $expectedBytes) {
        $downloadSucceeded = $true
        break
    }
    Write-Warning "$($source.Name) failed or returned the wrong size; trying next source."
}
if (-not $downloadSucceeded) {throw "All sources failed. Partial data was kept at $partialPath"}

$actualHash = (Get-FileHash -LiteralPath $partialPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedSha256) {throw "SHA-256 mismatch. Partial data was kept at $partialPath"}
Move-Item -LiteralPath $partialPath -Destination $targetPath
Write-Host "Completed and verified: $targetPath"
