[CmdletBinding()]
param(
    [string[]]$Profiles = @('1080_stream_90', '1080_stream_107', '1080_stream_124'),
    [string]$Api = 'http://127.0.0.1:8188',
    [double]$AbortRamGiB = 31.0
)

# Phase 3 and phase 4 of plans/H3_1080_STREAMING_OUTPUT_PLAN.md: walk the frame
# counts upward with identical settings and stop at the first failure instead of
# pushing on to longer clips.

$ErrorActionPreference = 'Continue'
$runner = Join-Path $PSScriptRoot 'run_h3_1080_stream.ps1'
$results = @()

foreach ($profileName in $Profiles) {
    Write-Host ''
    Write-Host ('=============== {0} ===============' -f $profileName)
    & $runner -Profile $profileName -Api $Api -AbortRamGiB $AbortRamGiB
    $code = $LASTEXITCODE
    $results += [pscustomobject]@{ Profile = $profileName; ExitCode = $code }
    Write-Host ('=============== {0} exit={1} ===============' -f $profileName, $code)
    if ($code -ne 0) {
        Write-Warning ('{0} failed with exit code {1}. Stopping the escalation as planned.' -f $profileName, $code)
        break
    }
}

Write-Host ''
Write-Host 'CHAIN SUMMARY'
foreach ($row in $results) {
    Write-Host ('  {0} exit={1}' -f $row.Profile, $row.ExitCode)
}
$failed = @($results | Where-Object { $_.ExitCode -ne 0 })
if ($failed.Count -gt 0) { exit 1 }
exit 0
