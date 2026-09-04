[CmdletBinding()]
param(
    [ValidateSet('draft', 'long_draft', 'final', '1080_smoke', '1080_short', '1080_probe_39', '1080_probe_56', '1080_probe_73', '1080_probe_84', '1080_probe_90')]
    [string]$Profile = 'draft',
    [long]$Seed = 2026082901,
    [ValidateRange(0.0, 2.0)]
    [double]$LoraStrength = 0.5,
    [switch]$LoopLock,
    [switch]$Silent,
    [string]$PromptFile,
    [string]$InputImage,
    [string]$ComfyInputDir,
    [string]$RunReport,
    [ValidateRange(1.0, 128.0)]
    [double]$AbortRamGiB = 31.0,
    [string]$Api = 'http://127.0.0.1:8188'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'h3_input_common.ps1')
$workflowPath = Join-Path $projectRoot 'workflows\minimax_h3_live2d_figurine_api.json'
$profilesPath = Join-Path $projectRoot 'presets\minimax_h3_live2d_profiles.json'
$workflow = Get-Content -LiteralPath $workflowPath -Raw | ConvertFrom-Json
$profiles = Get-Content -LiteralPath $profilesPath -Raw | ConvertFrom-Json
$settings = $profiles.$Profile

$promptText = $null
if ($PromptFile) {
    $resolvedPromptFile = (Resolve-Path -LiteralPath $PromptFile).Path
    $promptText = [IO.File]::ReadAllText($resolvedPromptFile, [Text.Encoding]::UTF8)
    Write-Host ("Prompt file: {0}" -f $resolvedPromptFile)
}

$imageTag = ''
$loadImageValue = [string]$workflow.'1'.inputs.image
if ($InputImage) {
    $resolvedImage = Resolve-H3InputImage -InputImage $InputImage -Api $Api -ComfyInputDir $ComfyInputDir
    $loadImageValue = [string]$resolvedImage.load_image_value
    $imageTag = '_' + [string]$resolvedImage.tag
    Write-Host ("Input image: {0}" -f $loadImageValue)
    Write-Host ("  source   : {0}" -f $resolvedImage.source_path)
    Write-Host ("  sha256   : {0}" -f $resolvedImage.sha256)
    Write-Host ("  published to input dir: {0}" -f $resolvedImage.published)
}
else {
    Write-Host ("Input image: {0} (workflow default)" -f $loadImageValue)
}

if ($Silent) { $audioTag = '_silent' } else { $audioTag = '_audio' }

$outputWidth = $settings.width
$outputHeight = $settings.height
$scaleOutput = $false
if ($settings.PSObject.Properties.Name -contains 'output_width') {
    $outputWidth = $settings.output_width
    $outputHeight = $settings.output_height
    $scaleOutput = $true
}

if ($LoopLock) { $mode = 'fl2v_looplock' } else { $mode = 'i2v' }

$strengthTag = '{0:D3}' -f [int][Math]::Round($LoraStrength * 100)
$filenamePrefix = "minimax_h3/live2d_${Profile}_${mode}_${outputWidth}x${outputHeight}_$($settings.length)f_s${strengthTag}_seed${Seed}${imageTag}${audioTag}"

$python = 'D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) { throw 'Python was not found to build the ComfyUI payload.' }
    $python = $pythonCmd.Source
}

$patchPath = Join-Path $env:TEMP "h3_live2d_patches_$PID.json"
$payloadPath = Join-Path $env:TEMP "h3_live2d_payload_$PID.json"
$patches = [ordered]@{
    client_id = "codex-h3-live2d-$Profile-$mode-$Seed"
    prompt = $promptText
    image = $loadImageValue
    silent = [bool]$Silent
    loop_lock = [bool]$LoopLock
    width = [int]$settings.width
    height = [int]$settings.height
    length = [int]$settings.length
    steps = [int]$settings.steps
    scheduler = [string]$settings.scheduler
    sampler = [string]$settings.sampler
    seed = $Seed
    fps = [double]$settings.fps
    lora_strength = $LoraStrength
    output_width = [int]$outputWidth
    output_height = [int]$outputHeight
    scale_output = [bool]$scaleOutput
    filename_prefix = $filenamePrefix
}
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllText($patchPath, ($patches | ConvertTo-Json -Depth 6), $utf8NoBom)
Write-Host 'Building workflow payload with Python...'
& $python (Join-Path $PSScriptRoot 'h3_build_live2d_payload.py') --workflow $workflowPath --patches $patchPath --output $payloadPath
if ($LASTEXITCODE -ne 0) {
    throw "Failed to build ComfyUI payload (python exit $LASTEXITCODE)."
}
$body = [IO.File]::ReadAllBytes($payloadPath)
$submitted = Invoke-RestMethod -Method Post -Uri "$Api/prompt" -ContentType 'application/json; charset=utf-8' -Body $body
if ($submitted.node_errors -and $submitted.node_errors.PSObject.Properties.Count -gt 0) {
    $submitted.node_errors | ConvertTo-Json -Depth 20
    throw 'ComfyUI rejected one or more workflow nodes.'
}

$promptId = $submitted.prompt_id
Write-Host "Submitted prompt: $promptId"
Write-Host "Profile=$Profile Mode=$mode Seed=$Seed LoRA=$LoraStrength"

$startedAt = Get-Date
$watch = [System.Diagnostics.Stopwatch]::StartNew()
[double]$peakVram = 0
[double]$peakRam = 0
$nextReport = 0
[double]$releasedRam = 0
[double]$releasedVram = 0

function Get-H3RamGiB { param($Stats) return ($Stats.system.ram_total - $Stats.system.ram_free) / 1GB }
function Get-H3VramGiB { param($Stats) return ($Stats.devices[0].vram_total - $Stats.devices[0].vram_free) / 1GB }

function Invoke-ComfyFree {
    param([Parameter(Mandatory)][string]$Endpoint)
    $freeBody = '{"unload_models":true,"free_memory":true}'
    Invoke-RestMethod -Method Post -Uri "$Endpoint/free" -ContentType 'application/json' -Body $freeBody -TimeoutSec 30 | Out-Null
}

function Wait-ComfyIdleRam {
    param(
        [Parameter(Mandatory)][string]$Endpoint,
        [int]$MaxSeconds = 45
    )
    # /free only queues flags; the worker applies them on its next loop pass.
    $best = [double]::MaxValue
    $stable = 0
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    $stats = Invoke-RestMethod -Uri "$Endpoint/system_stats" -TimeoutSec 30
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        $stats = Invoke-RestMethod -Uri "$Endpoint/system_stats" -TimeoutSec 30
        $ram = Get-H3RamGiB -Stats $stats
        if ($ram -lt ($best - 0.05)) {
            $best = $ram
            $stable = 0
        }
        else {
            $stable++
            if ($stable -ge 3) { break }
        }
    }
    return $stats
}

function Release-H3Models {
    Write-Host 'Releasing ComfyUI models and cache...'
    try {
        Invoke-ComfyFree -Endpoint $Api
        $after = Wait-ComfyIdleRam -Endpoint $Api
        $script:releasedRam = [math]::Round((Get-H3RamGiB -Stats $after), 3)
        $script:releasedVram = [math]::Round((Get-H3VramGiB -Stats $after), 3)
        Write-Host ('Released: RAM {0:N2}GiB, VRAM {1:N2}GiB' -f $script:releasedRam, $script:releasedVram)
    }
    catch {
        Write-Warning ("Failed to release ComfyUI memory: {0}" -f $_)
    }
}

function Write-H3RunReport {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Status,
        $Output,
        $Messages
    )
    if (-not $RunReport) { return }

    $reportPath = [IO.Path]::GetFullPath($RunReport)
    $reportDirectory = Split-Path -Parent $reportPath
    if ($reportDirectory -and -not (Test-Path -LiteralPath $reportDirectory)) {
        New-Item -ItemType Directory -Path $reportDirectory -Force | Out-Null
    }
    [ordered]@{
        schema_version = 1
        started_at = $startedAt.ToUniversalTime().ToString('o')
        completed_at = (Get-Date).ToUniversalTime().ToString('o')
        status = $Status
        profile = $Profile
        api = $Api
        prompt_id = $promptId
        seed = $Seed
        mode = $mode
        input_image = [string]$loadImageValue
        internal_width = [int]$settings.width
        internal_height = [int]$settings.height
        output_width = [int]$outputWidth
        output_height = [int]$outputHeight
        frames = [int]$settings.length
        fps = [double]$settings.fps
        steps = [int]$settings.steps
        sampler = [string]$settings.sampler
        scheduler = [string]$settings.scheduler
        lora_strength = $LoraStrength
        silent = [bool]$Silent
        ram_abort_gib = $AbortRamGiB
        elapsed_seconds = [math]::Round($watch.Elapsed.TotalSeconds, 3)
        peak_vram_gib = [math]::Round($peakVram, 3)
        peak_ram_gib = [math]::Round($peakRam, 3)
        released_ram_gib = $releasedRam
        released_vram_gib = $releasedVram
        output = $Output
        messages = $Messages
    } | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Host "Run report: $reportPath"
}

$exitCode = 0
$reportStatus = $null
$reportOutput = $null
$reportMessages = $null
try {
    while ($true) {
        $stats = Invoke-RestMethod -Uri "$Api/system_stats"
        $ram = Get-H3RamGiB -Stats $stats
        $vram = Get-H3VramGiB -Stats $stats
        $peakRam = [Math]::Max($peakRam, $ram)
        $peakVram = [Math]::Max($peakVram, $vram)

        if ($ram -ge $AbortRamGiB) {
            Write-Warning ('RAM usage reached the safety threshold: {0:N2}GiB >= {1:N2}GiB. Requesting interrupt.' -f $ram, $AbortRamGiB)
            Invoke-RestMethod -Method Post -Uri "$Api/interrupt" -ContentType 'application/json' -Body '{}' | Out-Null
            $reportStatus = 'interrupted_ram_threshold'
            $reportMessages = @("RAM usage reached ${ram}GiB")
            throw 'Generation interrupted by the configured RAM safety threshold.'
        }

        if ($watch.Elapsed.TotalSeconds -ge $nextReport) {
            Write-Host ('Progress: {0:N0}s, VRAM {1:N2}GiB, RAM {2:N2}GiB, peaks {3:N2}/{4:N2}GiB' -f $watch.Elapsed.TotalSeconds, $vram, $ram, $peakVram, $peakRam)
            $nextReport += 30
        }

        $history = Invoke-RestMethod -Uri "$Api/history/$promptId"
        $entry = $history.PSObject.Properties[$promptId]
        if ($entry) {
            $status = $entry.Value.status
            Write-Host ('Finished: status={0}, elapsed={1:N1}s, peak VRAM={2:N2}GiB, peak RAM={3:N2}GiB' -f $status.status_str, $watch.Elapsed.TotalSeconds, $peakVram, $peakRam)
            $entry.Value.outputs.'15' | ConvertTo-Json -Depth 10
            $reportStatus = [string]$status.status_str
            $reportOutput = $entry.Value.outputs.'15'
            $reportMessages = $status.messages
            if ($status.status_str -ne 'success') {
                $status.messages | ConvertTo-Json -Depth 20
                $exitCode = 3
            }
            break
        }

        Start-Sleep -Seconds 2
    }
}
finally {
    Release-H3Models
    if ($reportStatus) {
        Write-H3RunReport -Status $reportStatus -Output $reportOutput -Messages $reportMessages
    }
}

if ($exitCode -ne 0) { exit $exitCode }
exit 0
