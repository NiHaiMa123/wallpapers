[CmdletBinding()]
param(
    [string]$ModelRoot = 'D:\Comfy-Desktop\ComfyUI-Shared\models',
    [string]$Proxy = 'http://127.0.0.1:9567',
    [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'

$repositoryPath = 'Hearmeman/minimax-h3-loras'
$fileName = 'HMNSFW-AIO-V2.5.safetensors'
$expectedBytes = [int64]86040232
$expectedSha256 = 'a07732a84fd733085eb5d910f602f918fa7a3658117116927e4329f5951a9d2d'

$sources = @(
    [pscustomobject]@{
        Name = 'ModelScope mirror'
        Url = "https://modelscope.cn/models/$repositoryPath/resolve/master/$fileName"
    },
    [pscustomobject]@{
        Name = 'HF-Mirror'
        Url = "https://hf-mirror.com/$repositoryPath/resolve/main/$fileName"
    },
    [pscustomobject]@{
        Name = 'Hugging Face official'
        Url = "https://huggingface.co/$repositoryPath/resolve/main/$fileName"
    }
)

function Invoke-Curl {
    param([Parameter(Mandatory)][string[]]$Arguments)

    & curl.exe @Arguments
    return $LASTEXITCODE
}

function Test-Source {
    param([Parameter(Mandatory)][pscustomobject]$Source)

    $arguments = @(
        '--location',
        '--fail',
        '--silent',
        '--show-error',
        '--max-time', '45',
        '--range', '0-0',
        '--output', 'NUL'
    )
    if ($Proxy) {
        $arguments += @('--proxy', $Proxy)
    }
    $arguments += $Source.Url
    return ((Invoke-Curl -Arguments $arguments) -eq 0)
}

function Test-CompletedFile {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }
    if ((Get-Item -LiteralPath $Path).Length -ne $expectedBytes) {
        return $false
    }
    $actualHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    return ($actualHash -eq $expectedSha256)
}

if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
    throw 'curl.exe is required but was not found.'
}

Write-Host "Model root:   $ModelRoot"
Write-Host "Proxy:        $Proxy"
Write-Host "Target LoRA:  $fileName"
Write-Host 'Source order: ModelScope mirror -> HF-Mirror -> Hugging Face official'

if ($PreflightOnly) {
    $available = 0
    foreach ($source in $sources) {
        Write-Host -NoNewline "Checking $($source.Name)... "
        if (Test-Source -Source $source) {
            Write-Host 'OK'
            $available++
        }
        else {
            Write-Host 'FAILED'
        }
    }
    if ($available -eq 0) {
        throw 'No LoRA source passed the preflight check.'
    }
    Write-Host "Preflight complete: $available/$($sources.Count) sources available."
    exit 0
}

$targetDirectory = Join-Path $ModelRoot 'loras'
$targetPath = Join-Path $targetDirectory $fileName
$partialPath = "$targetPath.part"

if (Test-Path -LiteralPath $targetPath -PathType Leaf) {
    Write-Host "Verifying existing file: $targetPath"
    if (Test-CompletedFile -Path $targetPath) {
        Write-Host 'Existing file is valid; skipping.'
        exit 0
    }
    throw "An invalid final file already exists: $targetPath. It was not overwritten."
}

if (-not (Test-Path -LiteralPath $targetDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $targetDirectory | Out-Null
}

if (Test-Path -LiteralPath $partialPath -PathType Leaf) {
    $partialLength = (Get-Item -LiteralPath $partialPath).Length
    if ($partialLength -gt $expectedBytes) {
        throw "Partial file is larger than expected: $partialPath. It was not deleted."
    }
    Write-Host "Resuming partial file at $partialLength bytes: $partialPath"
}

$downloadSucceeded = $false
foreach ($source in $sources) {
    Write-Host "Downloading from $($source.Name): $fileName"
    $arguments = @(
        '--location',
        '--fail',
        '--show-error',
        '--retry', '8',
        '--retry-connrefused',
        '--retry-delay', '5',
        '--connect-timeout', '20',
        '--speed-time', '120',
        '--speed-limit', '1024',
        '--continue-at', '-',
        '--output', $partialPath
    )
    if ($Proxy) {
        $arguments += @('--proxy', $Proxy)
    }
    $arguments += $source.Url

    $exitCode = Invoke-Curl -Arguments $arguments
    if ($exitCode -eq 0 -and (Test-Path -LiteralPath $partialPath -PathType Leaf)) {
        $partialLength = (Get-Item -LiteralPath $partialPath).Length
        if ($partialLength -eq $expectedBytes) {
            $downloadSucceeded = $true
            break
        }
        Write-Warning "Source returned $partialLength bytes; expected $expectedBytes. Trying next source."
    }
    else {
        Write-Warning "$($source.Name) failed with curl exit code $exitCode. Trying next source."
    }
}

if (-not $downloadSucceeded) {
    throw "All sources failed for $fileName. Partial data was kept for resume."
}

Write-Host "Computing SHA-256: $partialPath"
$actualHash = (Get-FileHash -LiteralPath $partialPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedSha256) {
    throw "SHA-256 mismatch for $partialPath. The partial file was kept for inspection."
}

Move-Item -LiteralPath $partialPath -Destination $targetPath
Write-Host "Completed and verified: $targetPath"
