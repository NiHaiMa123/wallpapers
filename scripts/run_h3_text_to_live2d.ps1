[CmdletBinding()]
param(
    [long]$ImageSeed = 2026083003,
    [long]$VideoSeed = 2026082904,
    [ValidateRange(0, 4)]
    [int]$FrameIndex = 0,
    [ValidateRange(0.0, 2.0)]
    [double]$ImageLoraStrength = 0.0,
    [ValidateRange(0.0, 2.0)]
    [double]$MotionLoraStrength = 0.5,
    [ValidateRange(1.0, 128.0)]
    [double]$AbortRamGiB = 31.0,
    [string]$ImagePrompt,
    [string]$MotionPrompt,
    [string]$Api = 'http://127.0.0.1:8188'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$workflowPath = Join-Path $projectRoot 'workflows\minimax_h3_text_to_live2d_api.json'
$workflow = Get-Content -LiteralPath $workflowPath -Raw | ConvertFrom-Json
$workflow.'25'.inputs.noise_seed = $ImageSeed
$workflow.'10'.inputs.noise_seed = $VideoSeed
$workflow.'28'.inputs.batch_index = $FrameIndex
$workflow.'30'.inputs.strength_model = $ImageLoraStrength
$workflow.'16'.inputs.strength_model = $MotionLoraStrength
if ($ImageLoraStrength -gt 0) {
    $workflow.'22'.inputs.model = @('30', 0)
    $workflow.'23'.inputs.model = @('30', 0)
} else {
    $workflow.'22'.inputs.model = @('2', 0)
    $workflow.'23'.inputs.model = @('2', 0)
}
if ($ImagePrompt) { $workflow.'21'.inputs.prompt = $ImagePrompt }
if ($MotionPrompt) { $workflow.'6'.inputs.prompt = $MotionPrompt }
$workflow.'29'.inputs.filename_prefix = "minimax_h3/text_to_live2d/first_frame_seed${ImageSeed}_frame${FrameIndex}"
$workflow.'15'.inputs.filename_prefix = "minimax_h3/text_to_live2d_image${ImageSeed}_video${VideoSeed}_frame${FrameIndex}"

$payload = @{prompt = $workflow; client_id = "codex-h3-text-live2d-$ImageSeed-$VideoSeed"} | ConvertTo-Json -Depth 50 -Compress
$submitted = Invoke-RestMethod -Method Post -Uri "$Api/prompt" -ContentType 'application/json' -Body $payload
if ($submitted.node_errors -and $submitted.node_errors.PSObject.Properties.Count -gt 0) {
    $submitted.node_errors | ConvertTo-Json -Depth 20
    throw 'ComfyUI rejected one or more text-to-Live2D workflow nodes.'
}

$promptId = $submitted.prompt_id
Write-Host "Submitted prompt: $promptId"
Write-Host "ImageSeed=$ImageSeed VideoSeed=$VideoSeed Frame=$FrameIndex ImageHMNSFW=$ImageLoraStrength MotionHMNSFW=$MotionLoraStrength"

$watch = [System.Diagnostics.Stopwatch]::StartNew()
[double]$peakVram = 0
[double]$peakRam = 0
$nextReport = 0
while ($true) {
    $stats = Invoke-RestMethod -Uri "$Api/system_stats"
    $ram = ($stats.system.ram_total - $stats.system.ram_free) / 1GB
    $vram = ($stats.devices[0].vram_total - $stats.devices[0].vram_free) / 1GB
    $peakRam = [Math]::Max($peakRam, $ram)
    $peakVram = [Math]::Max($peakVram, $vram)
    if ($ram -ge $AbortRamGiB) {
        Invoke-RestMethod -Method Post -Uri "$Api/interrupt" -ContentType 'application/json' -Body '{}' | Out-Null
        throw ('Generation interrupted at RAM safety threshold: {0:N2}GiB' -f $ram)
    }
    if ($watch.Elapsed.TotalSeconds -ge $nextReport) {
        Write-Host ('Progress: {0:N0}s, VRAM {1:N2}GiB, RAM {2:N2}GiB, peaks {3:N2}/{4:N2}GiB' -f $watch.Elapsed.TotalSeconds, $vram, $ram, $peakVram, $peakRam)
        $nextReport += 15
    }
    $history = Invoke-RestMethod -Uri "$Api/history/$promptId"
    $entry = $history.PSObject.Properties[$promptId]
    if ($entry) {
        $status = $entry.Value.status
        Write-Host ('Finished: status={0}, elapsed={1:N1}s, peak VRAM={2:N2}GiB, peak RAM={3:N2}GiB' -f $status.status_str, $watch.Elapsed.TotalSeconds, $peakVram, $peakRam)
        $entry.Value.outputs | ConvertTo-Json -Depth 12
        if ($status.status_str -ne 'success') {
            $status.messages | ConvertTo-Json -Depth 20
            exit 3
        }
        exit 0
    }
    Start-Sleep -Seconds 2
}
