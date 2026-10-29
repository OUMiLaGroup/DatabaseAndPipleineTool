# Secrets arrive on stdin, never in process arguments or console output.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Account.ps1')
try {
    [Console]::InputEncoding = New-Object Text.UTF8Encoding($false)
    $account = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $content = New-MilaEnvironment $account.username $account.password $account.token
    Save-MilaEnvironment $account.root $content $account.license
    exit 0
} catch { Write-Output $_.Exception.Message; exit 1 }
