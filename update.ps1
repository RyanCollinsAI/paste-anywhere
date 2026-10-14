$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {
    # git writes normal progress to stderr, and Windows PowerShell 5.1 turns
    # redirected native stderr into a terminating error under "Stop". Judge the
    # pull by its exit code instead.
    $ErrorActionPreference = "Continue"
    $pullOutput = git pull --ff-only 2>&1
    $pullExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    Write-Host $pullOutput
    if ($pullExit -ne 0) {
        Write-Error "git pull failed, stopping. See output above."
        exit 1
    }

    . (Join-Path $PSScriptRoot "resolve_python.ps1")
    $pythonExe = Resolve-PythonExe
    if (-not $pythonExe) {
        Write-Error "No Python interpreter found. Install Python 3.9+ from python.org first."
        exit 1
    }

    & $pythonExe -c "import win32clipboard, PIL" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Missing dependencies. Run: `"$pythonExe`" -m pip install pywin32 Pillow"
        exit 1
    }

    $taskNames = @("PasteAnywhere", "ClipboardBridge")
    $taskName = $null
    foreach ($name in $taskNames) {
        $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($t) {
            $taskName = $name
            break
        }
    }

    if ($taskName) {
        # Stop-ScheduledTask returns before the old bridge has released its
        # mutex, and a new instance that still sees the mutex exits silently.
        # So wait for the old one to be gone, then confirm the new one is up.
        function Wait-Bridge([bool]$wantRunning) {
            $deadline = (Get-Date).AddSeconds(15)
            do {
                & $pythonExe (Join-Path $PSScriptRoot "status.py") --json | Out-Null
                if (($LASTEXITCODE -eq 0) -eq $wantRunning) { return }
                Start-Sleep -Milliseconds 250
            } until ((Get-Date) -gt $deadline)
            Write-Error "Bridge did not $(if ($wantRunning) { 'start' } else { 'stop' }) within 15 seconds."
            exit 1
        }

        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Wait-Bridge $false
        Start-ScheduledTask -TaskName $taskName
        Wait-Bridge $true
        Write-Host "Restarted task '$taskName'."
    } else {
        Write-Host "No PasteAnywhere or ClipboardBridge task found to restart."
    }

    $shortHash = git rev-parse --short HEAD
    Write-Host "Updated to commit $shortHash"
} finally {
    Pop-Location
}
