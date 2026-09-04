[CmdletBinding()]
param(
    [long]$Seed = 2026083003,
    [ValidateRange(0, 4)]
    [int]$FrameIndex = 0,
    [ValidateRange(32, 4096)]
    [int]$Width = 1024,
    [ValidateRange(32, 4096)]
    [int]$Height = 576,
    [ValidateRange(0.0, 2.0)]
    [double]$ImageLoraStrength = 0.0,
    [ValidateRange(1.0, 128.0)]
    [double]$AbortRamGiB = 31.0,
    [string]$Prompt,
    [string]$OutputTag,
    [string]$Api = 'http://127.0.0.1:8188'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$workflowPath = Join-Path $projectRoot 'workflows\minimax_h3_pseudo_t2i_api.json'
$workflow = Get-Content -LiteralPath $workflowPath -Raw | ConvertFrom-Json

if ($Width % 32 -ne 0 -or $Height % 32 -ne 0) {
    throw 'MiniMax H3 width and height must be multiples of 32.'
}
$workflow.'4'.inputs.width = $Width
$workflow.'4'.inputs.height = $Height
$workflow.'8'.inputs.noise_seed = $Seed
$workflow.'12'.inputs.batch_index = $FrameIndex
$workflow.'14'.inputs.strength_model = $ImageLoraStrength
if ($ImageLoraStrength -gt 0) {
    $workflow.'5'.inputs.model = @('14', 0)
    $workflow.'6'.inputs.model = @('14', 0)
} else {
    $workflow.'5'.inputs.model = @('1', 0)
    $workflow.'6'.inputs.model = @('1', 0)
}
if ($Prompt) { $workflow.'4'.inputs.prompt = $Prompt }
$strengthTag = $ImageLoraStrength.ToString('0.00', [Globalization.CultureInfo]::InvariantCulture).Replace('.', 'p')
if (-not $OutputTag) { $OutputTag = "lora${strengthTag}" }
if ($OutputTag -notmatch '^[A-Za-z0-9_-]+$') { throw 'OutputTag may contain only letters, digits, underscore and hyphen.' }
$workflow.'11'.inputs.filename_prefix = "minimax_h3/t2i/${OutputTag}_contact_seed${Seed}"
$workflow.'13'.inputs.filename_prefix = "minimax_h3/t2i/${OutputTag}_selected_seed${Seed}_frame${FrameIndex}"

$payload = @{prompt = $workflow; client_id = "codex-h3-pseudo-t2i-$Seed-$FrameIndex"} | ConvertTo-Json -Depth 40 -Compress
$submitted = Invoke-RestMethod -Method Post -Uri "$Api/prompt" -ContentType 'application/json' -Body $payload
if ($submitted.node_errors -and $submitted.node_errors.PSObject.Properties.Count -gt 0) {
    $submitted.node_errors | ConvertTo-Json -Depth 20
    throw 'ComfyUI rejected one or more pseudo-T2I workflow nodes.'
}

$promptId = $submitted.prompt_id
Write-Host "Submitted prompt: $promptId"
Write-Host "Mode=H3 pseudo-T2I Frames=5 Steps=20 Seed=$Seed SelectedFrame=$FrameIndex Size=${Width}x${Height} ImageHMNSFW=$ImageLoraStrength Tag=$OutputTag"

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
