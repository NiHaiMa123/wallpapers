[CmdletBinding()]
param(
    [ValidateSet('1080_stream_5', '1080_stream_22', '1080_stream_73', '1080_stream_90', '1080_stream_107', '1080_stream_124')]
    [string]$Profile = '1080_stream_5',
    [long]$Seed = 2026083022,
    [ValidateRange(0.0, 2.0)]
    [double]$LoraStrength = 0.5,
    [string]$InputImage = 'keqing_gpt_reference_16x9.png',
    [string]$PromptFile,
    [string]$ComfyInputDir,
    [string]$ComfyOutputDir,
    [string]$RunId,
    [string]$OutputVideo,
    [string]$RunReport,
    [string]$PythonExe = 'D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Scripts\python.exe',
    [ValidateRange(1.0, 128.0)]
    [double]$AbortRamGiB = 31.0,
    [switch]$SkipEncode,
    [switch]$AllowAnyComfyVersion,
    [string]$Api = 'http://127.0.0.1:8189'
)

# MiniMax H3 native 1080p, frame-sequence output plus external streaming encode.
#
# This runner replaces the CreateVideo/SaveVideo tail of the standard route with
# a per-frame SaveImage into a run-isolated directory, then hands that directory
# to an external encoder once ComfyUI has released its models. Nothing about the
# H3 model, sampler, prompt, seed, LoRA or internal resolution changes, so every
# number it reports is directly comparable with artifacts/h3_1080_probe_*_run.json.

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'h3_input_common.ps1')

$workflowPath = Join-Path $projectRoot 'workflows\minimax_h3_live2d_frames_api.json'
$profilesPath = Join-Path $projectRoot 'presets\minimax_h3_1080_stream_profiles.json'
$config = Get-Content -LiteralPath $profilesPath -Raw -Encoding UTF8 | ConvertFrom-Json
$settings = $config.profiles.$Profile
if (-not $settings) { throw "Profile '$Profile' is missing from $profilesPath" }
$workflow = Get-Content -LiteralPath $workflowPath -Raw -Encoding UTF8 | ConvertFrom-Json

$frames = [int]$settings.length
$internalWidth = [int]$config.invariants.internal_width
$internalHeight = [int]$config.invariants.internal_height
$outputWidth = [int]$config.invariants.output_width
$outputHeight = [int]$config.invariants.output_height
$fps = [double]$config.encoding.fps
$steps = [int]$config.invariants.steps
$sampler = [string]$config.invariants.sampler
$scheduler = [string]$config.invariants.scheduler
$framesRootName = [string]$config.frames.output_subfolder_root
$counterOrigin = [int]$config.frames.counter_origin

function Get-ComfyStats {
    param([Parameter(Mandatory)][string]$Endpoint)
    return Invoke-RestMethod -Uri "$Endpoint/system_stats" -TimeoutSec 30
}

function Get-RamGiB { param($Stats) return ($Stats.system.ram_total - $Stats.system.ram_free) / 1GB }
function Get-VramGiB { param($Stats) return ($Stats.devices[0].vram_total - $Stats.devices[0].vram_free) / 1GB }

function Invoke-ComfyFree {
    param([Parameter(Mandatory)][string]$Endpoint)
    $body = '{"unload_models":true,"free_memory":true}'
    Invoke-RestMethod -Method Post -Uri "$Endpoint/free" -ContentType 'application/json' -Body $body -TimeoutSec 30 | Out-Null
}

function Wait-ComfyIdleRam {
    param(
        [Parameter(Mandatory)][string]$Endpoint,
        [int]$MaxSeconds = 45
    )
    # /free only queues flags; the worker applies them on its next loop pass, then
    # a gc pass releases the cache. Poll until the reading stops falling.
    $best = [double]::MaxValue
    $stable = 0
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    $stats = Get-ComfyStats -Endpoint $Endpoint
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        $stats = Get-ComfyStats -Endpoint $Endpoint
        $ram = Get-RamGiB -Stats $stats
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

$stats = Get-ComfyStats -Endpoint $Api
$comfyVersion = [string]$stats.system.comfyui_version
$versionPrefix = [string]$config.target_instance.comfyui_version_prefix
if (-not $comfyVersion.StartsWith($versionPrefix)) {
    if (-not $AllowAnyComfyVersion) {
        throw "$Api reports ComfyUI $comfyVersion. This route is validated on the $versionPrefix test instance; pass -AllowAnyComfyVersion to override deliberately."
    }
    Write-Warning "Running against ComfyUI $comfyVersion instead of $versionPrefix.x."
}
Write-Host ("ComfyUI {0} at {1}" -f $comfyVersion, $Api)

# Frames must land in the directory this ComfyUI actually writes to, so read it
# from the live process instead of assuming the shared path.
if (-not $ComfyOutputDir) {
    $argv = @($stats.system.argv)
    for ($i = 0; $i -lt $argv.Count - 1; $i++) {
        if ($argv[$i] -eq '--output-directory') {
            $ComfyOutputDir = [string]$argv[$i + 1]
            break
        }
    }
}
if (-not $ComfyOutputDir) { $ComfyOutputDir = 'D:\Comfy-Desktop\ComfyUI-Shared\output' }
if (-not (Test-Path -LiteralPath $ComfyOutputDir -PathType Container)) {
    throw "ComfyUI output directory was not found: $ComfyOutputDir"
}
$ComfyOutputDir = [IO.Path]::GetFullPath($ComfyOutputDir)

if (-not $RunId) {
    $RunId = '{0}-{1}' -f (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'), ([guid]::NewGuid().ToString('N').Substring(0, 4))
}
if ($RunId -notmatch '^[A-Za-z0-9_.-]+$') { throw "RunId may only contain letters, digits, dot, dash and underscore: $RunId" }
$frameDir = Join-Path (Join-Path $ComfyOutputDir $framesRootName) $RunId
if (Test-Path -LiteralPath $frameDir) {
    throw "Frame directory already exists; generate a new RunId rather than mixing runs: $frameDir"
}

if (-not $PromptFile) { $PromptFile = Join-Path $projectRoot 'prompts\MINIMAX_H3_1080P_FEASIBILITY_PROMPT.md' }
$PromptFile = (Resolve-Path -LiteralPath $PromptFile).Path
$promptText = [IO.File]::ReadAllText($PromptFile, [Text.Encoding]::UTF8)
$promptSha = (Get-FileHash -LiteralPath $PromptFile -Algorithm SHA256).Hash
$workflow.'6'.inputs.prompt = $promptText
Write-Host ("Prompt file: {0}" -f $PromptFile)
Write-Host ("  sha256   : {0}" -f $promptSha)

$resolvedImage = Resolve-H3InputImage -InputImage $InputImage -Api $Api -ComfyInputDir $ComfyInputDir
$workflow.'1'.inputs.image = [string]$resolvedImage.load_image_value
$imageTag = [string]$resolvedImage.tag
Write-Host ("Input image: {0} (sha256 {1})" -f $resolvedImage.load_image_value, $resolvedImage.sha256)

$workflow.'17'.inputs.width = $internalWidth
$workflow.'17'.inputs.height = $internalHeight
# run_h3_live2d_profile.ps1 forces 'disabled' for the 1080p profiles, so the input
# image is stretched to 1920x1088 rather than centre-cropped. Matching it is not
# cosmetic: a different first frame produces a different generation for the same seed.
$workflow.'17'.inputs.crop = 'disabled'
$workflow.'6'.inputs.width = $internalWidth
$workflow.'6'.inputs.height = $internalHeight
$workflow.'6'.inputs.length = $frames
$workflow.'8'.inputs.steps = $steps
$workflow.'8'.inputs.scheduler = $scheduler
$workflow.'9'.inputs.sampler_name = $sampler
$workflow.'10'.inputs.noise_seed = $Seed
$workflow.'16'.inputs.strength_model = $LoraStrength
$workflow.'19'.inputs.width = $outputWidth
$workflow.'19'.inputs.height = $outputHeight
$framePrefix = '{0}/{1}/{2}' -f $framesRootName, $RunId, ([string]$config.frames.filename_prefix_leaf)
$workflow.'20'.inputs.filename_prefix = $framePrefix

$strengthTag = '{0:D3}' -f [int][Math]::Round($LoraStrength * 100)
$baseName = 'live2d_1080_stream_i2v_{0}x{1}_{2}f_s{3}_seed{4}_{5}_silent_{6}' -f $outputWidth, $outputHeight, $frames, $strengthTag, $Seed, $imageTag, $RunId
if (-not $OutputVideo) {
    $OutputVideo = Join-Path $projectRoot ('outputs\h3_1080_stream\{0}.mp4' -f $baseName)
}
if (-not $RunReport) {
    $RunReport = Join-Path $projectRoot ('artifacts\h3_1080_stream_{0}_{1}_run.json' -f $frames, $RunId)
}
$sequenceReport = Join-Path $projectRoot ('artifacts\h3_1080_stream_{0}_{1}_frames.json' -f $frames, $RunId)
foreach ($target in @($OutputVideo, $RunReport, $sequenceReport)) {
    if (Test-Path -LiteralPath $target) { throw "Refusing to overwrite an existing artifact: $target" }
}
$outputParent = Split-Path -Parent $OutputVideo
if (-not (Test-Path -LiteralPath $outputParent)) { New-Item -ItemType Directory -Path $outputParent -Force | Out-Null }
$reportParent = Split-Path -Parent $RunReport
if (-not (Test-Path -LiteralPath $reportParent)) { New-Item -ItemType Directory -Path $reportParent -Force | Out-Null }

Write-Host ''
Write-Host ('Profile      : {0} ({1} frames, {2:N2}s at {3}fps)' -f $Profile, $frames, ($frames / $fps), $fps)
Write-Host ('Internal     : {0}x{1} -> output {2}x{3}' -f $internalWidth, $internalHeight, $outputWidth, $outputHeight)
Write-Host ('Run id       : {0}' -f $RunId)
Write-Host ('Frame dir    : {0}' -f $frameDir)
Write-Host ('Output video : {0}' -f $OutputVideo)
Write-Host ('RAM abort    : {0:N2}GiB' -f $AbortRamGiB)
Write-Host ''

Write-Host 'Releasing ComfyUI models and cache before generation...'
Invoke-ComfyFree -Endpoint $Api
$idleStats = Wait-ComfyIdleRam -Endpoint $Api
$idleRam = Get-RamGiB -Stats $idleStats
$idleVram = Get-VramGiB -Stats $idleStats
Write-Host ('Idle baseline: RAM {0:N2}GiB, VRAM {1:N2}GiB, headroom {2:N2}GiB' -f $idleRam, $idleVram, ($AbortRamGiB - $idleRam))
if ($idleRam -ge ($AbortRamGiB - 1.0)) {
    throw ('Idle RAM {0:N2}GiB is already within 1GiB of the abort threshold {1:N2}GiB. Close background programs before starting.' -f $idleRam, $AbortRamGiB)
}

$payload = @{prompt = $workflow; client_id = "codex-h3-1080-stream-$Profile-$RunId"} | ConvertTo-Json -Depth 50 -Compress
$body = [Text.Encoding]::UTF8.GetBytes($payload)
$submitted = Invoke-RestMethod -Method Post -Uri "$Api/prompt" -ContentType 'application/json; charset=utf-8' -Body $body
if ($submitted.node_errors -and $submitted.node_errors.PSObject.Properties.Count -gt 0) {
    $submitted.node_errors | ConvertTo-Json -Depth 20
    throw 'ComfyUI rejected one or more workflow nodes.'
}
$promptId = [string]$submitted.prompt_id
Write-Host ("Submitted prompt: {0}" -f $promptId)

$startedAt = Get-Date
$watch = [System.Diagnostics.Stopwatch]::StartNew()
[double]$peakRam = $idleRam
[double]$peakVram = $idleVram
[double]$stageAPeakRam = $idleRam
[double]$stageBPeakRam = 0
$firstFrameSeconds = $null
$lastFrameSeconds = $null
$timeline = New-Object System.Collections.ArrayList
$nextLog = 0
$framesOnDisk = 0

function Get-FrameCount {
    param([Parameter(Mandatory)][string]$Directory)
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) { return 0 }
    return @(Get-ChildItem -LiteralPath $Directory -Filter 'frame_*.png' -File -ErrorAction SilentlyContinue).Count
}

function Write-StreamRunReport {
    param(
        [Parameter(Mandatory)][string]$Status,
        [Parameter(Mandatory)][string]$FailedStage,
        $Messages,
        $Sequence,
        $Encode,
        [string]$Classification = 'unclassified'
    )

    $stageA = [ordered]@{
        name = 'sampling_decode_scale'
        covers = 'H3 diffusion, VAEDecode of the 1920x1088 batch and the Lanczos scale to 1920x1080'
        seconds = $null
        peak_ram_gib = [math]::Round($stageAPeakRam, 3)
    }
    if ($firstFrameSeconds -ne $null) { $stageA.seconds = [math]::Round($firstFrameSeconds, 3) }
    $stageB = [ordered]@{
        name = 'frame_save'
        covers = 'Per-frame SaveImage of the scaled batch to PNG'
        seconds = $null
        peak_ram_gib = [math]::Round($stageBPeakRam, 3)
        frames_written = $framesOnDisk
    }
    if ($firstFrameSeconds -ne $null -and $lastFrameSeconds -ne $null) {
        $stageB.seconds = [math]::Round($lastFrameSeconds - $firstFrameSeconds, 3)
    }
    $stageC = [ordered]@{
        name = 'external_encode'
        covers = 'PyAV/libx264 streaming encode with ComfyUI models unloaded'
        seconds = $null
        peak_ram_gib = $null
    }
    if ($Encode) {
        $stageC.seconds = $Encode.performance.encode_seconds
        $stageC.peak_ram_gib = [math]::Round([double]$Encode.performance.peak_system_ram_gib, 3)
    }

    [ordered]@{
        schema_version = 1
        kind = 'h3_1080_stream_run'
        status = $Status
        failed_stage = $FailedStage
        classification = $Classification
        started_at = $startedAt.ToUniversalTime().ToString('o')
        completed_at = (Get-Date).ToUniversalTime().ToString('o')
        profile = $Profile
        api = $Api
        comfyui_version = $comfyVersion
        prompt_id = $promptId
        run_id = $RunId
        output_route = 'SaveImage frame sequence + external streaming encode'
        seed = $Seed
        input_image = [string]$workflow.'1'.inputs.image
        input_image_sha256 = [string]$resolvedImage.sha256
        prompt_file = $PromptFile
        prompt_file_sha256 = $promptSha
        internal_width = $internalWidth
        internal_height = $internalHeight
        input_scale_method = [string]$workflow.'17'.inputs.upscale_method
        input_scale_crop = [string]$workflow.'17'.inputs.crop
        output_scale_method = [string]$workflow.'19'.inputs.upscale_method
        output_scale_crop = [string]$workflow.'19'.inputs.crop
        output_width = $outputWidth
        output_height = $outputHeight
        frames = $frames
        fps = $fps
        steps = $steps
        sampler = $sampler
        scheduler = $scheduler
        lora_strength = $LoraStrength
        silent = $true
        ram_abort_gib = $AbortRamGiB
        idle_ram_gib = [math]::Round($idleRam, 3)
        idle_vram_gib = [math]::Round($idleVram, 3)
        elapsed_seconds = [math]::Round($watch.Elapsed.TotalSeconds, 3)
        peak_ram_gib = [math]::Round($peakRam, 3)
        peak_vram_gib = [math]::Round($peakVram, 3)
        headroom_gib = [math]::Round(31.11 - $peakRam, 3)
        stages = @($stageA, $stageB, $stageC)
        frame_dir = $frameDir
        frame_prefix = $framePrefix
        frames_on_disk = $framesOnDisk
        output_video = $OutputVideo
        sequence_validation = $Sequence
        encode = $Encode
        ram_timeline = @($timeline)
        messages = $Messages
    } | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $RunReport -Encoding UTF8
    Write-Host ("Run report: {0}" -f $RunReport)
}

$generationStatus = $null
$generationMessages = $null
$promptCompleted = $false

# Stopping this runner does not stop ComfyUI. Launch a detached guard that keeps the
# RAM circuit breaker in place even if this process is killed outright, and interrupt
# the prompt ourselves on any exit path that leaves it still executing.
$self = Get-Process -Id $PID
$watchdogLog = Join-Path $projectRoot ('artifacts\h3_1080_stream_watchdog_{0}.log' -f $RunId)
$watchdog = Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -PassThru -ArgumentList @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f (Join-Path $PSScriptRoot 'h3_stream_watchdog.ps1')),
    '-Api', $Api,
    '-PromptId', $promptId,
    '-ParentProcessId', $PID,
    '-ParentStartedAt', ('"{0}"' -f $self.StartTime.ToUniversalTime().ToString('o')),
    '-AbortRamGiB', $AbortRamGiB,
    '-LogPath', ('"{0}"' -f $watchdogLog)
)
Write-Host ("Safety guard started: pid {0} (interrupts this prompt at {1:N2}GiB or if this runner dies)" -f $watchdog.Id, $AbortRamGiB)

try {
while ($true) {
    $stats = Get-ComfyStats -Endpoint $Api
    $ram = Get-RamGiB -Stats $stats
    $vram = Get-VramGiB -Stats $stats
    $elapsed = $watch.Elapsed.TotalSeconds
    $count = Get-FrameCount -Directory $frameDir
    if ($count -gt $framesOnDisk) {
        $framesOnDisk = $count
        $lastFrameSeconds = $elapsed
        if ($firstFrameSeconds -eq $null) {
            $firstFrameSeconds = $elapsed
            Write-Host ('First frame on disk at {0:N0}s; sampling/decode/scale peak RAM was {1:N2}GiB' -f $elapsed, $stageAPeakRam)
        }
    }
    $peakRam = [Math]::Max($peakRam, $ram)
    $peakVram = [Math]::Max($peakVram, $vram)
    if ($firstFrameSeconds -eq $null) { $stageAPeakRam = [Math]::Max($stageAPeakRam, $ram) }
    else { $stageBPeakRam = [Math]::Max($stageBPeakRam, $ram) }
    [void]$timeline.Add([ordered]@{
        elapsed_seconds = [math]::Round($elapsed, 2)
        ram_gib = [math]::Round($ram, 3)
        vram_gib = [math]::Round($vram, 3)
        frames_on_disk = $framesOnDisk
    })

    if ($ram -ge $AbortRamGiB) {
        Write-Warning ('RAM reached the safety threshold: {0:N2}GiB >= {1:N2}GiB. Requesting interrupt.' -f $ram, $AbortRamGiB)
        Invoke-RestMethod -Method Post -Uri "$Api/interrupt" -ContentType 'application/json' -Body '{}' | Out-Null
        Start-Sleep -Seconds 3
        $framesOnDisk = Get-FrameCount -Directory $frameDir
        $stage = 'frame_save'
        if ($firstFrameSeconds -eq $null) { $stage = 'sampling_decode_scale' }
        Write-StreamRunReport -Status 'interrupted_ram_threshold' -FailedStage $stage `
            -Messages @(('RAM reached {0:N3}GiB with {1} frames on disk' -f $ram, $framesOnDisk)) `
            -Sequence $null -Encode $null -Classification 'negative_control'
        Write-Host ("Frames kept for inspection: {0}" -f $frameDir)
        throw 'Generation interrupted by the configured RAM safety threshold.'
    }

    if ($elapsed -ge $nextLog) {
        Write-Host ('Progress: {0:N0}s, RAM {1:N2}GiB (peak {2:N2}), VRAM {3:N2}GiB, frames {4}/{5}' -f $elapsed, $ram, $peakRam, $vram, $framesOnDisk, $frames)
        $nextLog += 30
    }

    $history = Invoke-RestMethod -Uri "$Api/history/$promptId" -TimeoutSec 30
    $entry = $history.PSObject.Properties[$promptId]
    if ($entry) {
        $framesOnDisk = Get-FrameCount -Directory $frameDir
        $generationStatus = $entry.Value.status
        $generationMessages = $generationStatus.messages
        $promptCompleted = $true
        Write-Host ('Generation finished: status={0}, elapsed={1:N1}s, peak RAM={2:N2}GiB, frames={3}' -f $generationStatus.status_str, $watch.Elapsed.TotalSeconds, $peakRam, $framesOnDisk)
        break
    }
    Start-Sleep -Seconds 2
}
}
finally {
    if ($watchdog -and -not $watchdog.HasExited) {
        Stop-Process -Id $watchdog.Id -Force -ErrorAction SilentlyContinue
    }
    if (-not $promptCompleted) {
        Write-Warning 'Leaving while the prompt may still be executing. Interrupting it and releasing memory.'
        try { Invoke-RestMethod -Method Post -Uri "$Api/interrupt" -ContentType 'application/json' -Body '{}' -TimeoutSec 15 | Out-Null } catch { }
        Start-Sleep -Seconds 3
        try { Invoke-RestMethod -Method Post -Uri "$Api/free" -ContentType 'application/json' -Body '{"unload_models":true,"free_memory":true}' -TimeoutSec 15 | Out-Null } catch { }
    }
    if ((Test-Path -LiteralPath $watchdogLog) -and -not (Get-Content -LiteralPath $watchdogLog -ErrorAction SilentlyContinue)) {
        Remove-Item -LiteralPath $watchdogLog -Force -ErrorAction SilentlyContinue
    }
}

if ($generationStatus.status_str -ne 'success') {
    $generationMessages | ConvertTo-Json -Depth 20
    Write-StreamRunReport -Status $generationStatus.status_str -FailedStage 'comfyui_execution' `
        -Messages $generationMessages -Sequence $null -Encode $null -Classification 'negative_control'
    exit 3
}

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python interpreter was not found: $PythonExe (av, numpy, psutil and Pillow are required)"
}

Write-Host ''
Write-Host 'Validating the PNG frame sequence...'
$validator = Join-Path $PSScriptRoot 'validate_h3_frame_sequence.py'
& $PythonExe $validator $frameDir --expected-frames $frames --width $outputWidth --height $outputHeight `
    --counter-origin $counterOrigin --report $sequenceReport --quiet
$validatorExit = $LASTEXITCODE
$sequence = $null
if (Test-Path -LiteralPath $sequenceReport) {
    $sequence = Get-Content -LiteralPath $sequenceReport -Raw -Encoding UTF8 | ConvertFrom-Json
}
if ($validatorExit -ne 0) {
    Write-StreamRunReport -Status 'frame_sequence_invalid' -FailedStage 'frame_sequence_validation' `
        -Messages @("validate_h3_frame_sequence.py exited with $validatorExit") `
        -Sequence $sequence -Encode $null -Classification 'negative_control'
    Write-Host ("Frames kept for inspection: {0}" -f $frameDir)
    exit 4
}
Write-Host ('Frame sequence passed: {0}/{1} frames, {2}x{3}, black frames {4}' -f `
    $sequence.found_frames, $frames, $outputWidth, $outputHeight, @($sequence.metrics.black_frame_indexes).Count)

if ($SkipEncode) {
    Write-StreamRunReport -Status 'frames_only' -FailedStage 'none' `
        -Messages @('Encoding skipped by -SkipEncode') -Sequence $sequence -Encode $null -Classification 'frames_only'
    Write-Host ("Frames kept at: {0}" -f $frameDir)
    exit 0
}

Write-Host ''
Write-Host 'Releasing ComfyUI models and cache before the external encode...'
Invoke-ComfyFree -Endpoint $Api
$preEncodeStats = Wait-ComfyIdleRam -Endpoint $Api
Write-Host ('Pre-encode baseline: RAM {0:N2}GiB, VRAM {1:N2}GiB' -f (Get-RamGiB -Stats $preEncodeStats), (Get-VramGiB -Stats $preEncodeStats))

$encodeReport = Join-Path (Split-Path -Parent $OutputVideo) ([IO.Path]::GetFileNameWithoutExtension($OutputVideo) + '_ENCODE.json')
$encoder = Join-Path $PSScriptRoot 'encode_h3_frame_sequence.py'
& $PythonExe $encoder $frameDir $OutputVideo --expected-frames $frames --width $outputWidth --height $outputHeight `
    --fps $fps --counter-origin $counterOrigin --crf ([int]$config.encoding.crf) `
    --encoder-preset ([string]$config.encoding.encoder_preset) --tune ([string]$config.encoding.tune) `
    --h264-profile ([string]$config.encoding.h264_profile) --h264-level ([string]$config.encoding.h264_level) `
    --run-report $encodeReport | Out-Null
$encoderExit = $LASTEXITCODE
$encode = $null
if (Test-Path -LiteralPath $encodeReport) {
    $encode = Get-Content -LiteralPath $encodeReport -Raw -Encoding UTF8 | ConvertFrom-Json
}
if ($encoderExit -ne 0) {
    Write-StreamRunReport -Status 'encode_failed' -FailedStage 'external_encode' `
        -Messages @("encode_h3_frame_sequence.py exited with $encoderExit") `
        -Sequence $sequence -Encode $encode -Classification 'negative_control'
    Write-Host ("Frames and any partial video kept for inspection: {0}" -f $frameDir)
    exit 5
}

# Classification uses the worst stage peak, not just the generation peak: an
# encode that needed the last gigabyte is no more usable than a generation that did.
$totalRamGiB = [double]$config.safety.total_physical_ram_gib
$requiredHeadroom = [double]$config.safety.recommended_headroom_gib
$worstPeak = $peakRam
if ($encode -and $encode.performance.peak_system_ram_gib) {
    $worstPeak = [Math]::Max($worstPeak, [double]$encode.performance.peak_system_ram_gib)
}
$headroom = $totalRamGiB - $worstPeak
$classification = 'boundary'
if ($headroom -ge $requiredHeadroom) { $classification = 'recommended' }

Write-StreamRunReport -Status 'success' -FailedStage 'none' -Messages $generationMessages `
    -Sequence $sequence -Encode $encode -Classification $classification

Write-Host ''
Write-Host ('Output video : {0}' -f $OutputVideo)
Write-Host ('  sha256     : {0}' -f $encode.output.sha256)
Write-Host ('  frames     : {0}' -f $encode.output.validation.decoded_frames)
Write-Host ('  fidelity   : luma PSNR mean {0:N2}dB (min {1:N2}dB), RGB PSNR mean {2:N2}dB, MAD mean {3:N4}' -f `
    [double]$encode.fidelity.luma_psnr_mean_db, [double]$encode.fidelity.luma_psnr_min_db, `
    [double]$encode.fidelity.psnr_mean_db, [double]$encode.fidelity.mad_mean)
Write-Host ('Encode RAM   : peak {0:N2}GiB, growth across run {1:N3}GiB' -f `
    [double]$encode.performance.peak_system_ram_gib, [double]$encode.performance.system_ram_gib_growth_across_run)
Write-Host ('Worst stage peak {0:N2}GiB of {1:N2}GiB physical, headroom {2:N2}GiB -> {3}' -f $worstPeak, $totalRamGiB, $headroom, $classification)
Write-Host ('Frames kept at {0}; delete them only after you accept the video.' -f $frameDir)
exit 0
