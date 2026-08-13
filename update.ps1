$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {
    $pullOutput = git pull --ff-only 2>&1
    $pullExit = $LASTEXITCODE
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
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Start-ScheduledTask -TaskName $taskName
        Write-Host "Restarted task '$taskName'."
    } else {
        Write-Host "No PasteAnywhere or ClipboardBridge task found to restart."
    }

    $shortHash = git rev-parse --short HEAD
    Write-Host "Updated to commit $shortHash"
} finally {
    Pop-Location
}
