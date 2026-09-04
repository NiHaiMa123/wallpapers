[CmdletBinding()]
param(
    [ValidateSet(4, 6, 8)]
    [int]$Steps = 4,
    [long]$Seed = 2026082904,
    [ValidateRange(0.0, 2.0)]
    [double]$LoraStrength = 0.5,
    [switch]$LowVram,
    [switch]$Silent,
    [string]$PromptFile,
    [string]$InputImage,
    [string]$ComfyInputDir,
    [ValidateRange(1.0, 128.0)]
    [double]$AbortRamGiB = 31.0,
    [string]$Api = 'http://127.0.0.1:8188'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'h3_input_common.ps1')
$workflowPath = Join-Path $projectRoot 'workflows\minimax_h3_live2d_turbo_api.json'
$workflow = Get-Content -LiteralPath $workflowPath -Raw | ConvertFrom-Json

$workflow.'8'.inputs.steps = $Steps
$workflow.'10'.inputs.noise_seed = $Seed
$workflow.'16'.inputs.strength_model = $LoraStrength
$workflow.'19'.inputs.low_vram = [bool]$LowVram

$promptTag = ''
if ($PromptFile) {
    $resolvedPromptFile = (Resolve-Path -LiteralPath $PromptFile).Path
    $workflow.'6'.inputs.prompt = [IO.File]::ReadAllText($resolvedPromptFile, [Text.Encoding]::UTF8)
    $promptStem = [IO.Path]::GetFileNameWithoutExtension($resolvedPromptFile) -replace '[^A-Za-z0-9]', ''
    if ($promptStem.Length -gt 20) { $promptStem = $promptStem.Substring(0, 20) }
    $promptTag = '_' + $promptStem
    Write-Host ("Prompt file: {0}" -f $resolvedPromptFile)
    Write-Host ("  sha256   : {0}" -f (Get-FileHash -LiteralPath $resolvedPromptFile -Algorithm SHA256).Hash)
}

if ($Silent) {
    $workflow.PSObject.Properties.Remove('5')
    $workflow.PSObject.Properties.Remove('13')
    $workflow.'14'.inputs.PSObject.Properties.Remove('audio')
    $audioTag = '_silent'
}
else {
    $audioTag = ''
}

$imageTag = ''
if ($InputImage) {
    $resolvedImage = Resolve-H3InputImage -InputImage $InputImage -Api $Api -ComfyInputDir $ComfyInputDir
    $workflow.'1'.inputs.image = [string]$resolvedImage.load_image_value
    $imageTag = '_' + [string]$resolvedImage.tag
    Write-Host ("Input image: {0}" -f $resolvedImage.load_image_value)
    Write-Host ("  source   : {0}" -f $resolvedImage.source_path)
    Write-Host ("  sha256   : {0}" -f $resolvedImage.sha256)
    Write-Host ("  published to input dir: {0}" -f $resolvedImage.published)
}
else {
    Write-Host ("Input image: {0} (workflow default)" -f $workflow.'1'.inputs.image)
}

$strengthTag = '{0:D3}' -f [int][Math]::Round($LoraStrength * 100)
$vramTag = if ($LowVram) { 'merge' } else { 'bypass' }
$workflow.'15'.inputs.filename_prefix = "minimax_h3/live2d_turbo${Steps}_i2v_1024x576_73f_s${strengthTag}_${vramTag}_seed${Seed}${imageTag}${promptTag}${audioTag}"

$payload = @{prompt = $workflow; client_id = "codex-h3-turbo-$Steps-$vramTag-$Seed"} | ConvertTo-Json -Depth 50 -Compress
$body = [Text.Encoding]::UTF8.GetBytes($payload)
$submitted = Invoke-RestMethod -Method Post -Uri "$Api/prompt" -ContentType 'application/json; charset=utf-8' -Body $body
if ($submitted.node_errors -and $submitted.node_errors.PSObject.Properties.Count -gt 0) {
    $submitted.node_errors | ConvertTo-Json -Depth 20
    throw 'ComfyUI rejected one or more Turbo workflow nodes.'
}

$promptId = $submitted.prompt_id
Write-Host "Submitted prompt: $promptId"
Write-Host "TurboSteps=$Steps Seed=$Seed HMNSFW=$LoraStrength LowVram=$([bool]$LowVram)"

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
        Write-Warning ('RAM usage reached the safety threshold: {0:N2}GiB >= {1:N2}GiB. Requesting interrupt.' -f $ram, $AbortRamGiB)
        Invoke-RestMethod -Method Post -Uri "$Api/interrupt" -ContentType 'application/json' -Body '{}' | Out-Null
        throw 'Generation interrupted by the configured RAM safety threshold.'
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
        $entry.Value.outputs.'15' | ConvertTo-Json -Depth 10
        if ($status.status_str -ne 'success') {
            $status.messages | ConvertTo-Json -Depth 20
            exit 3
        }
        exit 0
    }

    Start-Sleep -Seconds 2
}
