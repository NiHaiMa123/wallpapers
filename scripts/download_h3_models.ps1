[CmdletBinding()]
param(
    [string]$ModelRoot = 'D:\Comfy-Desktop\ComfyUI-Shared\models',
    [string]$Proxy = 'http://127.0.0.1:9567',
    [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'

$repositoryPath = 'Comfy-Org/MiniMax-H3'
$sources = @(
    [pscustomobject]@{
        Name = 'ModelScope mirror'
        Base = "https://modelscope.cn/models/$repositoryPath/resolve/master/"
    },
    [pscustomobject]@{
        Name = 'HF-Mirror'
        Base = "https://hf-mirror.com/$repositoryPath/resolve/main/"
    },
    [pscustomobject]@{
        Name = 'Hugging Face official'
        Base = "https://huggingface.co/$repositoryPath/resolve/main/"
    }
)

# SHA-256 values are the matching X-Linked-ETag values returned by both
# ModelScope and Hugging Face on 2026-08-29.
$models = @(
    [pscustomobject]@{
        RelativePath = 'diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors'
        Bytes = [int64]20970379616
        Sha256 = 'e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a'
    },
    [pscustomobject]@{
        RelativePath = 'text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors'
        Bytes = [int64]15687142551
        Sha256 = '35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6'
    },
    [pscustomobject]@{
        RelativePath = 'vae/minimax_h3_video_vae_fp16.safetensors'
        Bytes = [int64]5207808496
        Sha256 = '7c1f131492e7eddacaac9069a61b81bdd39de5cc96561e677c5eab1cdce5e522'
    },
    [pscustomobject]@{
        RelativePath = 'vae/minimax_h3_audio_vae_fp32.safetensors'
        Bytes = [int64]605254808
        Sha256 = '8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48'
    }
)

function Invoke-Curl {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    & curl.exe @Arguments
    return $LASTEXITCODE
}

function Test-DownloadSource {
    param(
        [Parameter(Mandatory)]
        [pscustomobject]$Source,
        [Parameter(Mandatory)]
        [string]$RelativePath
    )

    $url = $Source.Base + $RelativePath.Replace('\', '/')
    $arguments = @(
        '--location',
        '--fail',
        '--silent',
        '--show-error',
        '--max-time', '35',
        '--range', '0-0',
        '--output', 'NUL'
    )
    if ($Proxy) {
        $arguments += @('--proxy', $Proxy)
    }
    $arguments += $url

    $exitCode = Invoke-Curl -Arguments $arguments
    return ($exitCode -eq 0)
}

function Test-CompletedFile {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [int64]$ExpectedBytes,
        [Parameter(Mandatory)]
        [string]$ExpectedSha256
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }

    $file = Get-Item -LiteralPath $Path
    if ($file.Length -ne $ExpectedBytes) {
        return $false
    }

    $actualHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    return ($actualHash -eq $ExpectedSha256)
}

if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
    throw 'curl.exe is required but was not found.'
}

Write-Host "Model root: $ModelRoot"
Write-Host "Proxy:      $Proxy"
Write-Host 'Source order: ModelScope mirror -> HF-Mirror -> Hugging Face official'

if ($PreflightOnly) {
    $probeFile = 'vae/minimax_h3_audio_vae_fp32.safetensors'
    $available = 0
    foreach ($source in $sources) {
        Write-Host -NoNewline "Checking $($source.Name)... "
        if (Test-DownloadSource -Source $source -RelativePath $probeFile) {
            Write-Host 'OK'
            $available++
        }
        else {
            Write-Host 'FAILED'
        }
    }
    if ($available -eq 0) {
        throw 'No model source passed the preflight check.'
    }
    Write-Host "Preflight complete: $available/$($sources.Count) sources available."
    exit 0
}

$rootPath = [System.IO.Path]::GetPathRoot($ModelRoot)
$driveInfo = [System.IO.DriveInfo]::new($rootPath)
$remainingBytes = [int64]0
foreach ($model in $models) {
    $targetPath = Join-Path $ModelRoot $model.RelativePath
    if (-not (Test-Path -LiteralPath $targetPath -PathType Leaf)) {
        $remainingBytes += $model.Bytes
    }
}
$reserveBytes = [int64](10GB)
if ($driveInfo.AvailableFreeSpace -lt ($remainingBytes + $reserveBytes)) {
    throw "Insufficient disk space. Need the remaining model bytes plus a 10 GiB reserve."
}

foreach ($model in $models) {
    $targetPath = Join-Path $ModelRoot $model.RelativePath
    $targetDirectory = Split-Path -Parent $targetPath
    $partialPath = "$targetPath.part"

    if (Test-Path -LiteralPath $targetPath -PathType Leaf) {
        Write-Host "Verifying existing file: $targetPath"
        if (Test-CompletedFile -Path $targetPath -ExpectedBytes $model.Bytes -ExpectedSha256 $model.Sha256) {
            Write-Host 'Existing file is valid; skipping.'
            continue
        }
        throw "An invalid final file already exists: $targetPath. It was not overwritten."
    }

    if (-not (Test-Path -LiteralPath $targetDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $targetDirectory | Out-Null
    }

    if (Test-Path -LiteralPath $partialPath -PathType Leaf) {
        $partialLength = (Get-Item -LiteralPath $partialPath).Length
        if ($partialLength -gt $model.Bytes) {
            throw "Partial file is larger than expected: $partialPath. It was not deleted."
        }
        Write-Host "Resuming partial file at $partialLength bytes: $partialPath"
    }

    $downloadSucceeded = $false
    foreach ($source in $sources) {
        $url = $source.Base + $model.RelativePath.Replace('\', '/')
        Write-Host "Downloading from $($source.Name): $($model.RelativePath)"
        $arguments = @(
            '--location',
            '--fail',
            '--show-error',
            '--retry', '8',
            '--retry-all-errors',
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
        $arguments += $url

        $exitCode = Invoke-Curl -Arguments $arguments
        if ($exitCode -eq 0 -and (Test-Path -LiteralPath $partialPath -PathType Leaf)) {
            $partialLength = (Get-Item -LiteralPath $partialPath).Length
            if ($partialLength -eq $model.Bytes) {
                $downloadSucceeded = $true
                break
            }
            Write-Warning "Source returned success but size is $partialLength; expected $($model.Bytes). Trying next source."
        }
        else {
            Write-Warning "$($source.Name) failed with curl exit code $exitCode. Trying next source."
        }
    }

    if (-not $downloadSucceeded) {
        throw "All sources failed for $($model.RelativePath). Partial data was kept for resume."
    }

    Write-Host "Computing SHA-256: $partialPath"
    $actualHash = (Get-FileHash -LiteralPath $partialPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $model.Sha256) {
        throw "SHA-256 mismatch for $partialPath. The partial file was kept for inspection."
    }

    Move-Item -LiteralPath $partialPath -Destination $targetPath
    Write-Host "Completed and verified: $targetPath"
}

Write-Host 'All MiniMax H3 base files are present and verified.'
