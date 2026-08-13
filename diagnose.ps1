$ErrorActionPreference = "Stop"

$statusScript = Join-Path $PSScriptRoot "status.py"

. (Join-Path $PSScriptRoot "resolve_python.ps1")
$consolePython = Resolve-PythonExe

# (a) task PasteAnywhere or ClipboardBridge missing
$taskNames = @("PasteAnywhere", "ClipboardBridge")
$task = $null
$taskName = $null
foreach ($name in $taskNames) {
    $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($t) {
        $task = $t
        $taskName = $name
        break
    }
}

if (-not $task) {
    Write-Host "FAIL: no scheduled task found (checked PasteAnywhere, ClipboardBridge)."
    Write-Host "Fix: run register_task.ps1 to register the PasteAnywhere task."
    exit 1
}

# (b) task disabled
if ($task.State -eq "Disabled") {
    Write-Host "FAIL: task '$taskName' is disabled."
    Write-Host "Fix: Enable-ScheduledTask -TaskName '$taskName'"
    exit 1
}

# (c) task action executable path does not exist
$actionExe = $task.Actions[0].Execute
if (-not (Test-Path $actionExe)) {
    Write-Host "FAIL: task '$taskName' action executable does not exist: $actionExe"
    Write-Host "Fix: re-run register_task.ps1 (stale interpreter path after a Python upgrade)."
    exit 1
}

# (d) deps fail to import in the resolved interpreter
& $actionExe -c "import win32clipboard, PIL" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: dependencies fail to import in $actionExe"
    Write-Host "Fix: & `"$actionExe`" -m pip install pywin32 Pillow"
    exit 1
}

# (e) Pictures\Clips not writable
$clipsDir = $env:PASTE_ANYWHERE_DIR
if (-not $clipsDir) {
    $clipsDir = Join-Path $env:USERPROFILE "Pictures\Clips"
}
if (-not (Test-Path $clipsDir)) {
    try {
        New-Item -ItemType Directory -Path $clipsDir -Force | Out-Null
    } catch {
        Write-Host "FAIL: clips folder does not exist and could not be created: $clipsDir"
        Write-Host "Fix: create the folder or fix permissions on $clipsDir"
        exit 1
    }
}
$probeFile = Join-Path $clipsDir "._diagnose_probe.tmp"
$writable = $true
try {
    [System.IO.File]::WriteAllText($probeFile, "probe")
    Remove-Item -Path $probeFile -Force -ErrorAction Stop
} catch {
    $writable = $false
}
if (-not $writable) {
    Write-Host "FAIL: clips folder is not writable: $clipsDir"
    Write-Host "Fix: fix permissions on $clipsDir"
    exit 1
}

# (f) process not running despite task Ready
if ($task.State -eq "Ready") {
    $running = $false
    if ($consolePython) {
        & $consolePython $statusScript --json 2>$null | Out-Null
        $running = ($LASTEXITCODE -eq 0)
    }
    if (-not $running) {
        Write-Host "FAIL: task '$taskName' is Ready but the process is not running."
        Write-Host "Fix: Start-ScheduledTask -TaskName '$taskName'"
        exit 1
    }
}

Write-Host "all checks pass"
if ($consolePython) {
    & $consolePython $statusScript
} else {
    Write-Host "(no console Python interpreter found to run status.py)"
}
