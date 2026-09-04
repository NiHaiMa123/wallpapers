[CmdletBinding()]
param(
    [string]$Profile,
    [ValidateSet('ai', 'lanczos')]
    [string]$Method,
    [string]$InputVideo,
    [string]$OutputVideo,
    [string]$RunReport,
    [string]$RunId,
    [string]$ProfileFile,
    [string]$PythonPath,
    [string]$ModelPath,
    [switch]$ValidateOnly,
    [switch]$SmokeTest
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not $ProfileFile) {
    $ProfileFile = Join-Path $projectRoot 'presets\wallpaper_4k_profiles.json'
}
if (-not $PythonPath) {
    $PythonPath = 'D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Scripts\python.exe'
}
if (-not $RunId) {
    $timestamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $suffix = [Guid]::NewGuid().ToString('N').Substring(0, 4)
    $RunId = "$timestamp-$suffix"
}

if (-not (Test-Path -LiteralPath $ProfileFile -PathType Leaf)) {
    throw "4K profile file was not found: $ProfileFile"
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "ComfyUI Python was not found: $PythonPath"
}

$config = Get-Content -LiteralPath $ProfileFile -Raw -Encoding UTF8 | ConvertFrom-Json
if ($config.schema_version -ne 1) {
    throw "Unsupported profile schema: $($config.schema_version)"
}
if ($Profile -and $PSBoundParameters.ContainsKey('Method')) {
    throw '-Profile and the deprecated -Method option cannot be used together.'
}
if ($PSBoundParameters.ContainsKey('Method')) {
    Write-Warning '-Method is deprecated; use -Profile instead.'
    if ($Method -eq 'ai') { $Profile = 'ai_detail_default' } else { $Profile = 'temporal_safe' }
}
if (-not $Profile) {
    $Profile = [string]$config.default_profile
}

$profileProperty = $config.profiles.PSObject.Properties | Where-Object { $_.Name -eq $Profile } | Select-Object -First 1
if (-not $profileProperty) {
    throw "Unknown 4K profile: $Profile"
}
$selected = $profileProperty.Value
if ($selected.interpolation) {
    throw "Profile '$Profile' requests interpolation, which is not implemented."
}
if ($selected.method -notin @('lanczos', 'realesrgan_stream')) {
    throw "Unsupported 4K method: $($selected.method)"
}
if ([int]$selected.width -le 0 -or [int]$selected.height -le 0 -or ([int]$selected.width % 2) -ne 0 -or ([int]$selected.height % 2) -ne 0) {
    throw 'Profile dimensions must be positive even integers.'
}
if ($selected.method -eq 'realesrgan_stream' -and [int]$selected.tile -le [int]$selected.overlap) {
    throw 'Profile tile must be larger than overlap.'
}

if (-not $InputVideo) {
    $InputVideo = Join-Path $projectRoot 'outputs\wallpaper\MiniMaxH3_Live2D_Seed2026082904_1024x576_24fps_LOOP_SILENT.mp4'
}
if (-not (Test-Path -LiteralPath $InputVideo -PathType Leaf)) {
    throw "Input video was not found: $InputVideo"
}
$InputVideo = [IO.Path]::GetFullPath($InputVideo)
$ProfileFile = [IO.Path]::GetFullPath($ProfileFile)
$PythonPath = [IO.Path]::GetFullPath($PythonPath)

$inputStem = [IO.Path]::GetFileNameWithoutExtension($InputVideo)
$nameMatch = [regex]::Match($inputStem, '^(?<identity>.+)_\d+x\d+_\d+fps_LOOP_SILENT$')
if (-not $nameMatch.Success -and -not $OutputVideo) {
    throw 'The input name does not match the wallpaper naming contract; supply -OutputVideo explicitly.'
}
if ($nameMatch.Success) {
    $identity = $nameMatch.Groups['identity'].Value
    $outputName = '{0}_{1}x{2}_{3}fps_{4}_LOOP_SILENT.mp4' -f $identity, [int]$selected.width, [int]$selected.height, [int]$selected.fps, [string]$selected.method_tag
    if ($SmokeTest) {
        $outputName = [IO.Path]::GetFileNameWithoutExtension($outputName) + '_SMOKE_1F.mp4'
    }
}

if (-not $OutputVideo) {
    if ($SmokeTest) {
        $OutputVideo = Join-Path $projectRoot "outputs\performance\step10\$RunId\smoke\$outputName"
    }
    else {
        $OutputVideo = Join-Path $projectRoot "outputs\wallpaper4k\runs\$RunId\$outputName"
    }
}
$OutputVideo = [IO.Path]::GetFullPath($OutputVideo)

if (-not $RunReport) {
    $reportName = [IO.Path]::GetFileNameWithoutExtension($OutputVideo) + '_RUN.json'
    $RunReport = Join-Path $projectRoot "outputs\performance\step10\$RunId\$reportName"
}
$RunReport = [IO.Path]::GetFullPath($RunReport)

if ($InputVideo -eq $OutputVideo) {
    throw 'Input and output paths must be different.'
}
if ($OutputVideo -eq $RunReport) {
    throw 'Video and run report paths must be different.'
}
if (Test-Path -LiteralPath $OutputVideo) {
    throw "Refusing to replace existing output: $OutputVideo"
}
if (Test-Path -LiteralPath $RunReport) {
    throw "Refusing to replace existing run report: $RunReport"
}

$commonScript = Join-Path $PSScriptRoot 'upscale_4k_common.py'
$probeLines = & $PythonPath -B $commonScript probe --video $InputVideo
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$probe = ($probeLines -join [Environment]::NewLine) | ConvertFrom-Json
if ([int]$probe.decoded_frames -le 0) {
    throw 'Input video contains no decodable frames.'
}
if ([Math]::Abs([double]$probe.fps - [double]$selected.fps) -gt 0.000001) {
    throw "Input fps $($probe.fps) does not match profile fps $($selected.fps)."
}

if ($selected.method -eq 'realesrgan_stream') {
    if (-not $ModelPath) {
        $ModelPath = Join-Path 'D:\Comfy-Desktop\ComfyUI-Shared\models\upscale_models' ([string]$selected.model_filename)
    }
    if (-not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) {
        throw "RealESRGAN model was not found: $ModelPath"
    }
    $ModelPath = [IO.Path]::GetFullPath($ModelPath)
}

$effective = [ordered]@{
    run_id = $RunId
    profile = $Profile
    method = [string]$selected.method
    input_video = $InputVideo
    output_video = $OutputVideo
    run_report = $RunReport
    python = $PythonPath
    profile_file = $ProfileFile
    model = $ModelPath
    smoke_test = [bool]$SmokeTest
    validate_only = [bool]$ValidateOnly
    settings = $selected
    input_probe = $probe
}
$effective | ConvertTo-Json -Depth 10

if ($ValidateOnly) {
    return
}

$scope = 'full'
$maxFrames = 0
if ($SmokeTest) {
    $scope = 'smoke'
    $maxFrames = 1
}

$commonArgs = @(
    $InputVideo,
    $OutputVideo,
    '--run-report', $RunReport,
    '--profile-file', $ProfileFile,
    '--profile-name', $Profile,
    '--width', [string]$selected.width,
    '--height', [string]$selected.height,
    '--expected-fps', [string]$selected.fps,
    '--crf', [string]$selected.crf,
    '--preset', [string]$selected.encoder_preset,
    '--tune', [string]$selected.tune,
    '--h264-profile', [string]$selected.h264_profile,
    '--h264-level', [string]$selected.h264_level,
    '--max-frames', [string]$maxFrames,
    '--scope', $scope
)

if ($selected.method -eq 'realesrgan_stream') {
    $worker = Join-Path $PSScriptRoot 'upscale_wallpaper_4k_realesrgan_stream.py'
    $workerArgs = $commonArgs + @(
        '--model', $ModelPath,
        '--tile', [string]$selected.tile,
        '--overlap', [string]$selected.overlap,
        '--abort-ram-gib', [string]$selected.abort_ram_gib
    )
}
else {
    $worker = Join-Path $PSScriptRoot 'upscale_wallpaper_4k_lanczos.py'
    $workerArgs = $commonArgs
}

& $PythonPath -B $worker @workerArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
