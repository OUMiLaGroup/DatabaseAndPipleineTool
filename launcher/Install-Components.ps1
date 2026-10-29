# Runs in a separate process so downloads and builds never block the GUI.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
function Refresh-Tools {
    $env:PATH = [Environment]::GetEnvironmentVariable('PATH','Machine') + ';' + [Environment]::GetEnvironmentVariable('PATH','User') + ';' + $env:PATH
    foreach ($dir in @("$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin", "$env:ProgramFiles\Docker\Docker\resources\bin", "$env:ProgramFiles\Git\cmd", "$env:LOCALAPPDATA\Programs\Git\cmd")) {
        if (Test-Path $dir) { $env:PATH = "$dir;$env:PATH" }
    }
}
function Ensure-Wsl {
    if (!(Get-Command wsl.exe -ErrorAction SilentlyContinue)) { throw 'WSL is unavailable. Update Windows 11 and enable Windows Subsystem for Linux, then retry.' }
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $versionText = ((& wsl.exe --version 2>$null) -join "`n").Replace([string][char]0,'')
    $versionExit = $LASTEXITCODE
    $ErrorActionPreference = $previous
    $match = [regex]::Match($versionText,'\d+\.\d+\.\d+(?:\.\d+)?')
    if ($versionExit -ne 0 -or !$match.Success) {
        Write-Host 'Installing WSL without an extra Linux distribution. Approve the Windows administrator prompt.'
        $wslProcess = Start-Process wsl.exe -Verb RunAs -WindowStyle Hidden -ArgumentList '--install','--no-distribution' -Wait -PassThru
        if ($wslProcess.ExitCode -notin @(0,3010,1641)) { throw "WSL installer exited with code $($wslProcess.ExitCode). Check Windows optional features and retry." }
        throw 'WSL installation completed. Restart Windows, then reopen MiLa-Launcher.exe to continue.'
    }
    if ([version]$match.Value -lt [version]'2.1.5') {
        Write-Host 'Updating WSL for Docker. Approve the Windows administrator prompt.'
        $wslProcess = Start-Process wsl.exe -Verb RunAs -WindowStyle Hidden -ArgumentList '--update' -Wait -PassThru
        if ($wslProcess.ExitCode -in @(3010,1641)) { throw 'WSL update needs a restart. Restart Windows and reopen MiLa-Launcher.exe.' }
        if ($wslProcess.ExitCode -ne 0) { throw "WSL update failed with code $($wslProcess.ExitCode)." }
    }
}
function Download-VerifiedInstaller([string]$Url, [string]$Name, [string]$Publisher) {
    $dir = Join-Path $env:LOCALAPPDATA 'MiLa/Downloads'
    New-Item $dir -ItemType Directory -Force | Out-Null
    $destination = Join-Path $dir $Name
    Write-Host "Downloading $Name from its official publisher..."
    Add-Type -AssemblyName System.Net.Http
    $client = New-Object Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromHours(2)
    $response = $null; $inputStream = $null; $outputStream = $null
    try {
        $response = $client.GetAsync($Url, [Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        $response.EnsureSuccessStatusCode() | Out-Null
        $length = $response.Content.Headers.ContentLength
        $inputStream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $outputStream = [IO.File]::Create($destination)
        $buffer = New-Object byte[] 262144
        $total = 0L; $last = -1
        while (($count = $inputStream.Read($buffer,0,$buffer.Length)) -gt 0) {
            $outputStream.Write($buffer,0,$count); $total += $count
            if ($length -gt 0) {
                $percent = [int](100 * $total / $length)
                if ($percent -ne $last) { Write-Host "DOWNLOAD $percent% $Name"; $last = $percent }
            }
        }
    } finally {
        if ($outputStream) { $outputStream.Dispose() }; if ($inputStream) { $inputStream.Dispose() }
        if ($response) { $response.Dispose() }; $client.Dispose()
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $destination
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch $Publisher) {
        throw "Installer signature verification failed for $Name. Nothing was executed."
    }
    return $destination
}
try {
    $architecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    if ($architecture -ne 'AMD64') { throw 'This project currently requires an AMD64 (Intel/AMD x64) PC; its OpenPilot build is not ARM64 compatible.' }
    Refresh-Tools
    Write-Host 'Preparing Windows prerequisites...'
    if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
        Ensure-Wsl
        $installer = Download-VerifiedInstaller 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe' 'Docker Desktop Installer.exe' 'O=Docker Inc\.?[, ]'
        Write-Host 'Follow the Docker installer window. Choose WSL 2. Windows may request approval or a restart.'
        # Visible because the user must interact with the official installation wizard.
        $installed = Start-Process -FilePath $installer -ArgumentList 'install','--user' -PassThru -Wait
        if ($installed.ExitCode -in @(3010,1641)) { throw 'Docker installation needs a Windows restart. Restart, then reopen MiLa-Launcher.exe.' }
        if ($installed.ExitCode -ne 0) { throw "Docker installer exited with code $($installed.ExitCode). Reopen the launcher after resolving the installer message." }
        Refresh-Tools
    }
    if (!(Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker CLI was not found after installation. Reopen the launcher after completing Docker setup.' }
    if (!(Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host 'Finding the latest official Git for Windows installer...'
        $release = Invoke-RestMethod 'https://api.github.com/repos/git-for-windows/git/releases/latest' -Headers @{'User-Agent'='MiLa-Launcher'}
        $asset = @($release.assets | Where-Object { $_.name -match '^Git-[0-9.]+-64-bit\.exe$' }) | Select-Object -First 1
        if (!$asset -or $asset.browser_download_url -notlike 'https://github.com/git-for-windows/git/releases/download/*') { throw 'Could not locate the official Git AMD64 installer.' }
        $installer = Download-VerifiedInstaller $asset.browser_download_url 'Git-64-bit.exe' '(?:CN|O)="?(?:Open Source Developer, )?Johannes Schindelin(?:[," ]|$)'
        Write-Host 'Complete the Git installer using its default options.'
        $installed = Start-Process $installer -PassThru -Wait
        if ($installed.ExitCode -ne 0) { throw "Git installer exited with code $($installed.ExitCode). Complete setup and retry." }
        Refresh-Tools
        if (!(Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is not yet on PATH. Reopen the launcher after Git setup.' }
    }
    # Starting Docker may display its first-run terms; the user must accept them.
    $ErrorActionPreference = 'Continue'
    $os = & docker info --format '{{.OSType}}' 2>$null
    $ready = $LASTEXITCODE -eq 0 -and $os -eq 'linux'
    $ErrorActionPreference = 'Stop'
    if (!$ready) {
        Ensure-Wsl
        $desktop = @("$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe", "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($desktop) { Start-Process $desktop -WindowStyle Hidden }
        Write-Host 'Waiting up to 10 minutes for Docker. Open Docker Desktop to accept its terms or finish WSL setup. If Windows requests a restart, restart and reopen this launcher.'
        $deadline = (Get-Date).AddMinutes(10)
        while (!$ready -and (Get-Date) -lt $deadline) {
            Start-Sleep 3
            $ErrorActionPreference = 'Continue'
            $os = & docker info --format '{{.OSType}}' 2>$null
            $ready = $LASTEXITCODE -eq 0 -and $os -eq 'linux'
            $ErrorActionPreference = 'Stop'
        }
        if (!$ready) { throw 'Docker is not ready in Linux-container mode. Open Docker Desktop and resolve its WSL, virtualization or terms prompt, then retry.' }
    }
    & (Join-Path $root 'scripts/Start-MiLa.ps1') -NoBrowser -ProjectRoot $root
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & (Join-Path $PSScriptRoot 'Ensure-JobDefinitions.ps1')
    exit 0
} catch { Write-Host "Installation stopped: $($_.Exception.Message)"; exit 1 }
