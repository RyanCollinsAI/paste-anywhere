$ErrorActionPreference = "Stop"

$taskName = "PasteAnywhere"
$scriptPath = Join-Path $PSScriptRoot "paste_anywhere.py"

if (-not (Test-Path $scriptPath)) {
    Write-Error "paste_anywhere.py not found at $scriptPath"
    exit 1
}

$pythonExe = $null
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    $pythonExe = & py -c "import sys; print(sys.executable)"
}
if (-not $pythonExe) {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        $pythonExe = & python -c "import sys; print(sys.executable)"
    }
}
if (-not $pythonExe) {
    Write-Error "No Python interpreter found. Install Python 3.9+ from python.org first."
    exit 1
}

$pythonwPath = Join-Path (Split-Path $pythonExe) "pythonw.exe"
if (-not (Test-Path $pythonwPath)) {
    Write-Error "pythonw.exe not found next to $pythonExe"
    exit 1
}

$action = New-ScheduledTaskAction -Execute $pythonwPath -Argument "`"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Watches the clipboard for screenshots and re-publishes them as image + file + path" -Force | Out-Null
Start-ScheduledTask -TaskName $taskName

Write-Host "Task '$taskName' registered and started. It also starts automatically at each logon."
