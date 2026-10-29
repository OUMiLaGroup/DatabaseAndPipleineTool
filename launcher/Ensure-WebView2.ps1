# Official Evergreen runtime bootstrapper; install only when missing.
$ErrorActionPreference = 'Stop'
function Test-WebView2Runtime {
    $id = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    foreach ($path in @("HKCU:\Software\Microsoft\EdgeUpdate\Clients\$id", "HKLM:\Software\WOW6432Node\Microsoft\EdgeUpdate\Clients\$id", "HKLM:\Software\Microsoft\EdgeUpdate\Clients\$id")) {
        $entry = Get-ItemProperty $path -Name pv -ErrorAction SilentlyContinue
        if ($entry -and $entry.pv -match '^\d+\.\d+\.\d+\.\d+$' -and [version]$entry.pv -gt [version]'0.0.0.0') { return $true }
    }
    return $false
}
if (!(Test-WebView2Runtime)) {
    Write-Host 'Downloading Microsoft WebView2 browser runtime...'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $folder = Join-Path $env:LOCALAPPDATA 'MiLa/Downloads'
    New-Item $folder -ItemType Directory -Force | Out-Null
    $installer = Join-Path $folder 'MicrosoftEdgeWebview2Setup.exe'
    Invoke-WebRequest 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $installer -UseBasicParsing
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'CN=Microsoft Corporation(?:,|$)') { throw 'Microsoft WebView2 installer signature verification failed. Nothing was executed.' }
    $process = Start-Process $installer -ArgumentList '/silent','/install' -WindowStyle Hidden -PassThru -Wait
    if ($process.ExitCode -ne 0 -or !(Test-WebView2Runtime)) { throw 'WebView2 installation did not finish. Install the Evergreen Runtime from developer.microsoft.com/microsoft-edge/webview2, then retry.' }
}
