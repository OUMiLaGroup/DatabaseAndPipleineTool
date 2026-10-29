#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
. (Join-Path $repo 'scripts/Start-MiLa.ps1')

function Assert-True($Condition, $Message) {
    if (-not $Condition) { throw "FAIL: $Message" }
}
function Assert-Throws([scriptblock]$Action, [string]$Pattern) {
    try { & $Action } catch {
        Assert-True ($_.Exception.Message -match $Pattern) "Unexpected failure: $($_.Exception.Message)"
        return
    }
    throw "FAIL: Expected failure matching $Pattern"
}

$fixture = Join-Path ([IO.Path]::GetTempPath()) ('mila-launcher-' + [guid]::NewGuid())
$null = New-Item -ItemType Directory -Path $fixture
try {
    # Exercise the real native wrapper and bounded wait before replacing tools.
    $nativeOutput = Invoke-Native powershell.exe @('-NoProfile', '-Command', 'Write-Output 123') -Quiet
    Assert-True ($nativeOutput.Trim() -eq '123') 'Native stdout captured'
    Invoke-Native powershell.exe @('-NoProfile', '-Command', 'Write-Output native-console-path-ok')
    Assert-Throws { Invoke-Native powershell.exe @('-NoProfile', '-Command', 'exit 9') } 'exit 9'
    Assert-Throws { Invoke-Native powershell.exe @('-NoProfile', '-Command', 'exit 7') -Quiet } 'exit 7'
    Assert-Throws { Wait-Ready 'test unavailable service' { return $false } -Timeout 0 } 'did not become ready'
    Assert-Throws { Wait-Ready 'crashed service' { throw 'Probe must not run' } -CheckFailure { throw 'container exited' } } 'container exited'
    $ProjectRoot = $fixture
    $NoBrowser = $true
    Copy-Item (Join-Path $repo '.example_env') (Join-Path $fixture '.example_env')
    Set-Content (Join-Path $fixture 'docker-compose.yaml') 'services: {}'
    Assert-Throws { Start-Mila } 'Configuration is missing'
    Assert-True (Test-Path (Join-Path $fixture '.env')) 'Missing env template should be copied'

    $script:settings = @{
        POSTGRES_USER='test'; POSTGRES_PASSWORD='secret'; POSTGRES_DB='test'
        MINIO_ROOT_USER='test'; MINIO_ROOT_PASSWORD='secret123'; MINIO_BUCKET_NAME='test'
        COMMA_JWT='test-token'; CVAT_EMAIL='test@example.org'; CVAT_PASSWORD='secret'
    }
    $script:config = @{services=@{backend=@{environment=$script:settings}; postgres=@{environment=$script:settings}}}
    Assert-Configuration ([pscustomobject]$script:config)
    $script:settings.COMMA_JWT = 'fill this out'
    Assert-Throws { Assert-Configuration ([pscustomobject]$script:config) } 'COMMA_JWT'
    $script:settings.COMMA_JWT = 'test-token'

    $script:calls = New-Object 'System.Collections.Generic.List[string]'
    $script:failMigration = $false
    $script:accountFailure = $false
    $script:failPreflight = ''
    $script:containerStatus = ''
    function docker {
        $script:calls.Add('account setup')
        $global:LASTEXITCODE = [int]$script:accountFailure
    }
    function Invoke-Native {
        param([string]$Program, [string[]]$Arguments, [switch]$Quiet)
        $command = "$Program $($Arguments -join ' ')"
        $script:calls.Add($command)
        if ($script:failPreflight -and $command -match $script:failPreflight) { throw 'simulated Docker failure containing secret-test-value' }
        if ($command -match 'docker-compose.cvat.windows.yml.*config --format json') { return '{"services":{"cvat_server":{"labels":{"traefik.docker.network":"cvat_cvat"}}}}' }
        if ($command -match 'config --format json') { return ($script:config | ConvertTo-Json -Depth 10) }
        if ($command -match 'ps -a --filter name=\^/cvat_server') { if ($script:legacyCvatNetwork) { return 'cvat_server' }; return '' }
        if ($command -match 'inspect cvat_server --format') { return '{}' }
        if ($command -match 'info --format') { return 'linux' }
        if ($command -match 'network ls') { return 'cvat_network' }
        if ($command -match 'ps --all --format json') { return $script:containerStatus }
        if ($command -match 'ps --status running') {
            return "backend`nfrontend`nopen_pilot_download_worker`nopen_pilot_upload_worker`ndataset_export_worker`ncvat_worker`ncvat_import_export_worker"
        }
        if ($script:failMigration -and $command -match 'run .*alembic_worker') { throw 'simulated migration failure' }
        return ''
    }
    function Test-HttpReady { param([string]$Url) return $true }
    # Invoke real probes once, without delays; fail if readiness is not established.
    function Wait-Ready {
        param([string]$Name, [scriptblock]$Probe, [int]$Timeout, [scriptblock]$CheckFailure)
        if ($CheckFailure) { & $CheckFailure }
        Assert-True (& $Probe) "Readiness probe failed: $Name"
    }
    foreach ($status in @('{"State":"exited","ExitCode":1}', '[{"State":"exited","ExitCode":1}]')) {
        $script:containerStatus = $status
        Assert-Throws { Assert-ServiceRunning @('compose') 'backend' } 'backend container is exited.*logs --tail 80 backend'
    }
    $script:containerStatus = '{"State":"running","ExitCode":0}'
    Assert-ServiceRunning @('compose') 'backend'
    $script:containerStatus = ''
    foreach ($case in @(
        @{ command='compose version'; message='Docker Compose check failed' },
        @{ command='info --format'; message='Cannot connect to the Docker engine' },
        @{ command='config --format json'; message='could not read the project configuration' }
    )) {
        $script:failPreflight = $case.command
        Assert-Throws { Start-Mila } $case.message
        try { Start-Mila } catch {
            Assert-True ($_.Exception.Message -notmatch 'secret-test-value') 'Preflight diagnostics must not expose command output'
        }
    }
    $script:failPreflight = ''
    Assert-Throws { Start-Mila } 'license'
    $null = New-Item -ItemType Directory -Path (Join-Path $fixture 'minio'), (Join-Path $fixture 'cvat')
    Set-Content (Join-Path $fixture 'minio/minio.license') 'test-license'
    Set-Content (Join-Path $fixture 'cvat/docker-compose.yml') 'services: {}'

    $script:calls.Clear()
    $CheckOnly = $true
    Start-Mila
    Assert-True (-not (($script:calls -join "`n") -match ' up | run |account setup')) 'CheckOnly must not start services'
    Assert-True (-not (Test-Path (Join-Path $fixture 'data'))) 'CheckOnly must not create data directories'
    $CheckOnly = $false
    $script:calls.Clear()
    $script:legacyCvatNetwork = $true
    Start-Mila
    $joined = $script:calls -join "`n"
    Assert-True ($joined -match 'up -d --no-deps cvat_server') 'Old CVAT proxy network labels must be migrated'
    $script:legacyCvatNetwork = $false
    $composeOperations = @($script:calls | Where-Object { $_ -match '^docker compose ' -and $_ -notmatch 'compose version' })
    Assert-True (@($composeOperations | Where-Object { $_ -notmatch '^docker compose --ansi never --progress plain ' }).Count -eq 0) 'Application and CVAT operations must use plain, non-ANSI progress'
    Assert-True ($joined.IndexOf('alembic_worker') -lt $joined.IndexOf('account setup')) 'Migrations precede CVAT account setup'
    Assert-True ($joined.IndexOf('account setup') -lt $joined.IndexOf('open_pilot_download_worker')) 'Account ready before workers'
    Assert-True ($joined -match 'up -d --no-recreate backend') 'Default preserves running workers'
    foreach ($setupService in @('alembic_worker', 'minio_initializer')) {
        Assert-True ($joined -match "run --rm --no-deps -T --interactive=false $setupService") "Setup job must not require a console: $setupService"
    }
    Assert-True ($joined -notmatch 'network create|git clone|revision| down ') 'Repeated startup avoids destructive/reset operations'

    $script:calls.Clear()
    $script:failMigration = $true
    Assert-Throws { Start-Mila } 'simulated migration failure'
    Assert-True (-not (($script:calls -join "`n") -match 'account setup|up -d --no-recreate backend')) 'Migration failure prevents application startup'
    $script:failMigration = $false
    $script:accountFailure = $true
    $script:calls.Clear()
    Assert-Throws { Start-Mila } 'CVAT account setup failed'
    Assert-True (-not (($script:calls -join "`n") -match 'up -d --no-recreate backend')) 'Account failure prevents worker startup'
    $script:accountFailure = $false
    $Rebuild = $true
    $script:calls.Clear()
    Start-Mila
    Assert-True (($script:calls -join "`n") -match 'up -d --build backend') 'Rebuild explicitly rebuilds application'
    Assert-True (($script:calls -join "`n") -match 'run --rm --no-deps -T --interactive=false --build alembic_worker') 'Rebuilt migrations must also run without a console'
    Write-Host 'PASS: configuration, read-only checks, startup ordering, repeated startup, failure propagation, and rebuild.' -ForegroundColor Green
} finally {
    $resolved = [IO.Path]::GetFullPath($fixture)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf) -like 'mila-launcher-*') {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
