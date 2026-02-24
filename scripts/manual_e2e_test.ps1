param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$FailingUrl = "http://127.0.0.1:65535",
    [string]$HealthyUrl = "https://scholarlyhelp.com/",
    [int]$TimeoutSeconds = 1500,
    [int]$PollSeconds = 3
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[STEP] $Message" -ForegroundColor Cyan
}

function Write-Pass {
    param([string]$Message)
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Yellow
}

function Invoke-Api {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        [object]$Body = $null
    )

    $uri = "$BaseUrl$Path"
    if ($null -eq $Body) {
        return Invoke-RestMethod -Method $Method -Uri $uri
    }

    $json = $Body | ConvertTo-Json -Depth 10
    return Invoke-RestMethod -Method $Method -Uri $uri -ContentType "application/json" -Body $json
}

function Wait-Until {
    param(
        [Parameter(Mandatory = $true)][string]$Description,
        [Parameter(Mandatory = $true)][scriptblock]$Condition,
        [int]$Timeout = 120,
        [int]$Poll = 3
    )

    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        try {
            if (& $Condition) {
                Write-Pass $Description
                return
            }
        } catch {
            # Keep polling until timeout.
        }
        Start-Sleep -Seconds $Poll
    }

    throw "Timeout waiting for: $Description"
}

Write-Step "Checking API health at $BaseUrl/healthz"
$health = Invoke-Api -Method GET -Path "/healthz"
Write-Pass "API healthy. Environment: $($health.environment)"

Write-Step "Creating a test monitor with fast thresholds"
$monitorPayload = @{
    name = "manual-e2e-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
    url = $FailingUrl
    method = "GET"
    interval_seconds = 10
    timeout_seconds = 5
    expected_status_min = 200
    expected_status_max = 399
    content_substring = $null
    failure_threshold = 1
    recovery_threshold = 1
    cooldown_seconds = 0
}

$monitor = Invoke-Api -Method POST -Path "/monitors" -Body $monitorPayload
$monitorId = $monitor.id
Write-Pass "Monitor created: $monitorId"

try {
    Write-Step "Waiting for outage detection (open incident + failed history)"
    Wait-Until -Description "Open incident created for monitor" -Timeout $TimeoutSeconds -Poll $PollSeconds -Condition {
        $openIncidents = @(Invoke-Api -Method GET -Path "/incidents/open")
        return @($openIncidents | Where-Object { $_.monitor_id -eq $monitorId }).Count -ge 1
    }

    Wait-Until -Description "At least one failed check result recorded" -Timeout $TimeoutSeconds -Poll $PollSeconds -Condition {
        $history = @(Invoke-Api -Method GET -Path "/monitors/$monitorId/history?limit=5")
        return @($history | Where-Object { $_.success -eq $false }).Count -ge 1
    }

    $openIncident = @(
        Invoke-Api -Method GET -Path "/incidents/open" |
        Where-Object { $_.monitor_id -eq $monitorId }
    ) | Select-Object -First 1

    if ($null -ne $openIncident.last_notification_error -and $openIncident.last_notification_error -ne "") {
        Write-Info "ClickUp send error on failure message: $($openIncident.last_notification_error)"
    } else {
        Write-Pass "Failure notification sent without stored error"
    }

    Write-Info "Check your ClickUp Chat now for a [DOWN] message."

    Write-Step "Switching monitor URL to healthy endpoint"
    $patchBody = @{ url = $HealthyUrl }
    Invoke-Api -Method PATCH -Path "/monitors/$monitorId" -Body $patchBody | Out-Null
    Write-Pass "Monitor updated to healthy URL"

    Write-Step "Waiting for recovery detection"
    Wait-Until -Description "Open incident closed for monitor" -Timeout $TimeoutSeconds -Poll $PollSeconds -Condition {
        $openIncidents = @(Invoke-Api -Method GET -Path "/incidents/open")
        return @($openIncidents | Where-Object { $_.monitor_id -eq $monitorId }).Count -eq 0
    }

    Wait-Until -Description "At least one successful check result recorded" -Timeout $TimeoutSeconds -Poll $PollSeconds -Condition {
        $history = @(Invoke-Api -Method GET -Path "/monitors/$monitorId/history?limit=10")
        return @($history | Where-Object { $_.success -eq $true }).Count -ge 1
    }

    $resolved = @(
        Invoke-Api -Method GET -Path "/incidents?status=resolved&limit=100" |
        Where-Object { $_.monitor_id -eq $monitorId }
    ) | Select-Object -First 1

    if ($null -eq $resolved) {
        throw "No resolved incident found for monitor $monitorId"
    }

    if ($null -ne $resolved.last_notification_error -and $resolved.last_notification_error -ne "") {
        Write-Info "ClickUp send error on recovery message: $($resolved.last_notification_error)"
    } else {
        Write-Pass "Recovery notification sent without stored error"
    }

    Write-Info "Check your ClickUp Chat now for a [RECOVERED] message."

    Write-Step "Pause/Resume smoke test"
    $paused = Invoke-Api -Method POST -Path "/monitors/$monitorId/pause"
    if ($paused.active -ne $false) {
        throw "Pause failed for monitor $monitorId"
    }
    $resumed = Invoke-Api -Method POST -Path "/monitors/$monitorId/resume"
    if ($resumed.active -ne $true) {
        throw "Resume failed for monitor $monitorId"
    }
    Write-Pass "Pause/Resume validated"

    Write-Pass "Manual E2E flow completed for monitor: $monitorId"
}
finally {
    try {
        Invoke-Api -Method POST -Path "/monitors/$monitorId/pause" | Out-Null
        Write-Info "Left test monitor paused: $monitorId"
    } catch {
        Write-Info "Could not pause monitor in cleanup: $monitorId"
    }
}
