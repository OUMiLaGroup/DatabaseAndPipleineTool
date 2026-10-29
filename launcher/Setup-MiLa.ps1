# The EXE calls this bootstrap. Python/HTML edits take effect immediately.
#Requires -Version 5.1
param(
    [ValidateSet('', 'existing', 'new')][string]$Preview = '',
    [switch]$SmokeTest,
    [string]$ProjectRoot = '',
    [switch]$Tkinter,
    [string]$BootstrapReadyFile = ''
)
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'workspace.py'
if ($Tkinter) { $script = Join-Path $PSScriptRoot 'mila_launcher.py' }
$candidates = New-Object 'Collections.Generic.List[string]'
$privatePython = Join-Path $env:LOCALAPPDATA 'MiLa\Runtime\Python313\python.exe'
if (Test-Path $privatePython) { $candidates.Add($privatePython) }
$command = Get-Command python.exe -ErrorAction SilentlyContinue
if ($command -and $command.Source -notlike '*\WindowsApps\*') { $candidates.Add($command.Source) }
if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $detected = & py.exe -3 -c 'import sys; print(sys.executable)' 2>$null
    if ($LASTEXITCODE -eq 0 -and $detected) { $candidates.Add([string]$detected) }
    $ErrorActionPreference = $previous
}
foreach ($base in @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles")) {
    if (Test-Path $base) {
        foreach ($folder in (Get-ChildItem $base -Directory -Filter 'Python*' -ErrorAction SilentlyContinue | Sort-Object Name -Descending)) {
            $candidate = Join-Path $folder.FullName 'python.exe'
            if (Test-Path $candidate) { $candidates.Add($candidate) }
        }
    }
}
$python = $null
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $candidate -c 'import sys, tkinter, struct; sys.exit(0 if sys.version_info >= (3, 10) and struct.calcsize(chr(80)) == 8 else 1)' 2>$null
    $supported = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $previous
    if ($supported) { $python = $candidate; break }
}
if (!$python) {
    & (Join-Path $PSScriptRoot 'Ensure-Python.ps1')
    $python = $privatePython
}
if (!$Tkinter) {
    try { & (Join-Path $PSScriptRoot 'Ensure-WebView2.ps1') }
    catch {
        Add-Type -AssemblyName System.Windows.Forms
        [void][Windows.Forms.MessageBox]::Show($_.Exception.Message, 'MiLa browser setup')
        exit 1
    }
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $python -c "import importlib.metadata, sys; sys.exit(0 if importlib.metadata.version('pywebview') == '6.2.1' else 1)" 2>$null
    $installed = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $previous
    if (!$installed) {
        Write-Host 'Installing embedded browser support for MiLa...'
        & $python -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
        if ($LASTEXITCODE -ne 0) {
            Add-Type -AssemblyName System.Windows.Forms
            [void][Windows.Forms.MessageBox]::Show('Browser support could not be installed. Run python -m pip install -r launcher\requirements.txt from the project folder, then retry.', 'MiLa browser setup')
            exit 1
        }
    }
}
$arguments = @($script)
if ($Preview) { $arguments += @('--preview', $Preview) }
if ($SmokeTest) { $arguments += '--smoke-test' }
if ($ProjectRoot) { $arguments += @('--root', $ProjectRoot) }
if ($BootstrapReadyFile) { [IO.File]::WriteAllText($BootstrapReadyFile, 'ready') }
& $python @arguments
exit $LASTEXITCODE
