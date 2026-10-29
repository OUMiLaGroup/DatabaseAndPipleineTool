# Install a private runtime without changing PATH, file associations, or system Python.
#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$runtime = Join-Path $env:LOCALAPPDATA 'MiLa\Runtime\Python313'
$python = Join-Path $runtime 'python.exe'
if (Test-Path $python) { return }
$downloads = Join-Path $env:LOCALAPPDATA 'MiLa\Downloads'
[void](New-Item -ItemType Directory -Force -Path $downloads)
$installer = Join-Path $downloads 'python-3.13.16-amd64.exe'
Write-Host 'Downloading Python from python.org (about 29 MB)...'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.13.16/python-3.13.16-amd64.exe' -OutFile $installer
$expected = 'fb4f9f5d438b2396da0086dc70b935c530cb578e37adc6d354f7ad2037fee83b'
if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ne $expected) { throw 'Python installer checksum did not match. Installation stopped.' }
$signature = Get-AuthenticodeSignature -LiteralPath $installer
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'Python installer publisher could not be verified.' }
Write-Host 'Installing Python with Tcl/Tk and pip for this Windows account...'
$options = @('/quiet', 'InstallAllUsers=0', "TargetDir=`"$runtime`"", 'Include_tcltk=1', 'Include_pip=1', 'Include_test=0', 'Include_doc=0', 'Include_launcher=0', 'InstallLauncherAllUsers=0', 'AssociateFiles=0', 'PrependPath=0', 'Shortcuts=0')
$process = Start-Process -FilePath $installer -ArgumentList $options -PassThru -Wait -WindowStyle Hidden
if ($process.ExitCode -in @(3010, 1641)) { throw 'Python installation requires a Windows restart. Restart, then reopen MiLa.' }
if ($process.ExitCode -ne 0 -or !(Test-Path $python)) { throw "Python installation failed (exit $($process.ExitCode)). Reopen MiLa to retry." }
& $python -c 'import tkinter, pip'
if ($LASTEXITCODE -ne 0) { throw 'Python runtime validation failed.' }
