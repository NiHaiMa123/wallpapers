[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Api,
    [Parameter(Mandatory)][string]$PromptId,
    [Parameter(Mandatory)][int]$ParentProcessId,
    [Parameter(Mandatory)][string]$ParentStartedAt,
    [Parameter(Mandatory)][double]$AbortRamGiB,
    [Parameter(Mandatory)][string]$LogPath
)

# Detached safety guard for one queued ComfyUI prompt.
#
# Stopping run_h3_1080_stream.ps1 does not stop ComfyUI: the prompt keeps running
# with no RAM circuit breaker, which is exactly what plans/H3_1080_STREAMING_OUTPUT_PLAN.md
# forbids for the 90/107/124 profiles. This process outlives a hard kill of the
# runner and interrupts the prompt if either the RAM threshold is crossed or the
# runner disappears while the prompt is still executing.
#
# It only ever interrupts while its own prompt id is the one ComfyUI reports as
# running, so a later unrelated job can never be cancelled by a stale guard.

$ErrorActionPreference = 'Continue'
$pollSeconds = 2
$graceSeconds = 6

function Write-GuardLog {
    param([Parameter(Mandatory)][string]$Message)
    $line = '{0} {1}' -f (Get-Date).ToUniversalTime().ToString('o'), $Message
    try {
        $directory = Split-Path -Parent $LogPath
        if ($directory -and -not (Test-Path -LiteralPath $directory)) {
            New-Item -ItemType Directory -Path $directory -Force | Out-Null
        }
        Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
    }
    catch { }
}

function Test-PromptRunning {
    try {
        $queue = Invoke-RestMethod -Uri "$Api/queue" -TimeoutSec 15
    }
    catch { return $null }
    foreach ($item in @($queue.queue_running)) {
        if ([string]$item[1] -eq $PromptId) { return $true }
    }
    foreach ($item in @($queue.queue_pending)) {
        if ([string]$item[1] -eq $PromptId) { return $true }
    }
    return $false
}

function Test-ParentAlive {
    try {
        $process = Get-Process -Id $ParentProcessId -ErrorAction Stop
    }
    catch { return $false }
    # Guard against PID reuse: a recycled id belongs to a different process.
    if ($process.StartTime.ToUniversalTime().ToString('o') -ne $ParentStartedAt) { return $false }
    return $true
}

function Stop-Prompt {
    param([Parameter(Mandatory)][string]$Reason)
    Write-GuardLog "interrupting prompt $PromptId : $Reason"
    try { Invoke-RestMethod -Method Post -Uri "$Api/interrupt" -ContentType 'application/json' -Body '{}' -TimeoutSec 15 | Out-Null }
    catch { Write-GuardLog "interrupt request failed: $_" }
    Start-Sleep -Seconds 3
    try { Invoke-RestMethod -Method Post -Uri "$Api/free" -ContentType 'application/json' -Body '{"unload_models":true,"free_memory":true}' -TimeoutSec 15 | Out-Null }
    catch { Write-GuardLog "free request failed: $_" }
    Write-GuardLog 'guard finished after interrupting'
}

$parentMissingSince = $null
while ($true) {
    Start-Sleep -Seconds $pollSeconds

    $running = Test-PromptRunning
    if ($running -eq $false) { break }

    try {
        $stats = Invoke-RestMethod -Uri "$Api/system_stats" -TimeoutSec 15
        $ram = ($stats.system.ram_total - $stats.system.ram_free) / 1GB
    }
    catch { $ram = $null }

    if ($ram -ne $null -and $ram -ge $AbortRamGiB) {
        Stop-Prompt -Reason ('RAM {0:N3}GiB reached the {1:N2}GiB threshold' -f $ram, $AbortRamGiB)
        exit 2
    }

    if (Test-ParentAlive) {
        $parentMissingSince = $null
        continue
    }

    # The runner is gone. Allow a short grace period in case it is exiting cleanly
    # and the prompt is about to be reported as finished.
    if ($parentMissingSince -eq $null) {
        $parentMissingSince = Get-Date
        Write-GuardLog "runner process $ParentProcessId disappeared while prompt $PromptId was still queued"
        continue
    }
    if (((Get-Date) - $parentMissingSince).TotalSeconds -ge $graceSeconds) {
        Stop-Prompt -Reason 'runner process exited while the prompt was still running, leaving no RAM circuit breaker'
        exit 3
    }
}

exit 0
