$ErrorActionPreference = "Stop"

$taskName = "PasteAnywhere"
$scriptPath = Join-Path $PSScriptRoot "paste_anywhere.py"

if (-not (Test-Path $scriptPath)) {
    Write-Error "paste_anywhere.py not found at $scriptPath"
    exit 1
}

. (Join-Path $PSScriptRoot "resolve_python.ps1")

$pythonExe = Resolve-PythonExe
if (-not $pythonExe) {
    Write-Error "No Python interpreter found. Install Python 3.9+ from python.org first."
    exit 1
}

$pythonwResolved = Resolve-PythonwExe -PythonExe $pythonExe
$exePath = $pythonwResolved.Exe
$usingPyw = $pythonwResolved.UsingPyw

if (-not (Test-Path $exePath)) {
    Write-Error "$(if ($usingPyw) { 'pyw.exe' } else { 'pythonw.exe' }) not found at $exePath"
    exit 1
}

# The check must exercise the same resolution path as the registered action.
# pyw.exe is a launcher, not a fixed interpreter, so when it is the action we
# check through the py launcher (py and pyw resolve the same default
# interpreter). Otherwise the action is pythonw.exe next to $pythonExe, so we
# keep checking $pythonExe, its console sibling.
if ($usingPyw) {
    & py -c "import win32clipboard, PIL" 2>$null
} else {
    & $pythonExe -c "import win32clipboard, PIL" 2>$null
}
if ($LASTEXITCODE -ne 0) {
    Write-Error "Missing dependencies. Run: `"$pythonExe`" -m pip install pywin32 Pillow"
    exit 1
}

$action = New-ScheduledTaskAction -Execute $exePath -Argument "`"$scriptPath`""
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# The bridge normally survives sleep. If it died while the machine was asleep,
# nothing would bring it back until the next logon, so also start on unlock and
# on wake. A start while the bridge is already running is ignored (IgnoreNew).
# Wake is Power-Troubleshooter 1 (S3 / hibernate) or Kernel-Power 507 (Modern Standby).
$triggerNs = "Root/Microsoft/Windows/TaskScheduler"
$unlockTrigger = New-CimInstance -ClientOnly -CimClass (Get-CimClass -Namespace $triggerNs -ClassName MSFT_TaskSessionStateChangeTrigger) -Property @{ StateChange = 8; UserId = $env:USERNAME; Enabled = $true }
$wakeQuery = "<QueryList><Query Id='0' Path='System'><Select Path='System'>*[System[Provider[@Name='Microsoft-Windows-Power-Troubleshooter'] and EventID=1]]</Select><Select Path='System'>*[System[Provider[@Name='Microsoft-Windows-Kernel-Power'] and EventID=507]]</Select></Query></QueryList>"
$wakeTrigger = New-CimInstance -ClientOnly -CimClass (Get-CimClass -Namespace $triggerNs -ClassName MSFT_TaskEventTrigger) -Property @{ Subscription = $wakeQuery; Enabled = $true }
$trigger = @($logonTrigger, $unlockTrigger, $wakeTrigger)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Watches the clipboard for screenshots and re-publishes them as image + file + path" -Force | Out-Null
Start-ScheduledTask -TaskName $taskName

Write-Host "Task '$taskName' registered and started. It also starts automatically at each logon, unlock, and wake from sleep."
Write-Host "Action executable: $exePath"
