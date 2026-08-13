function Resolve-PythonExe {
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
    return $pythonExe
}

function Resolve-PythonwExe {
    # Returns the windowless executable to use for a scheduled-task action, and
    # whether it is the py-launcher's pyw.exe (as opposed to the console
    # interpreter's own pythonw.exe sibling).
    #
    # pyw.exe is resolved as a sibling of the py launcher's own directory
    # (typically C:\Windows\pyw.exe), not via `Get-Command pyw`, because that
    # can resolve to a WindowsApps alias whose target is not guaranteed to be
    # the same install that a `py -c ...` dependency check exercises.
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExe
    )

    $pywPath = $null
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $pyDir = Split-Path $pyLauncher.Source
        $candidate = Join-Path $pyDir "pyw.exe"
        if (Test-Path $candidate) {
            $pywPath = $candidate
        }
    }

    if ($pywPath) {
        return [PSCustomObject]@{ Exe = $pywPath; UsingPyw = $true }
    }

    $pythonwPath = Join-Path (Split-Path $PythonExe) "pythonw.exe"
    return [PSCustomObject]@{ Exe = $pythonwPath; UsingPyw = $false }
}
