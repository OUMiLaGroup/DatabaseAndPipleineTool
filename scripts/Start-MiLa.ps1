#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$CheckOnly,
    [switch]$Rebuild,
    [ValidateRange(10, 3600)][int]$TimeoutSeconds = 300,
    [string]$ProjectRoot = ''
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Split-Path $PSScriptRoot -Parent
}

function Invoke-Native {
    param([string]$Program, [string[]]$Arguments, [switch]$Quiet)
    # Capture output for preflight commands: Compose config contains secrets.
    # Windows PowerShell treats native stderr as errors under Stop.
    $oldPreference = $ErrorActionPreference
    $oldBuildProgress = $env:BUILDKIT_PROGRESS
    if ($Program -eq 'docker') { $env:BUILDKIT_PROGRESS = 'plain' }
    $ErrorActionPreference = 'Continue'
    try {
        if ($Quiet) { $output = & $Program @Arguments 2>$null }
        # Do not pipe native stdout to Out-Host: Docker can mistake the pipe
        # for an interactive Windows console and fail with an invalid handle.
        else { & $Program @Arguments }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldPreference
        $env:BUILDKIT_PROGRESS = $oldBuildProgress
    }
    if ($code -ne 0) {
        if ($Program -eq 'git') {
            throw "Git failed (exit $code). See the Git error above. For checkout/path issues, see scripts/STARTUP.md."
        }
        if ($Quiet) {
            throw "$Program failed (exit $code). Check Docker Desktop and configuration. Command output is suppressed for configuration/credential checks."
        }
        throw "$Program failed (exit $code). See the command output above for the underlying error."
    }
    if ($Quiet) { return ($output -join "`n") }
}

function Repair-CvatCheckout {
    param([string]$Path)
    $marker = Join-Path $Path '.git/mila-checkout-incomplete'
    # A failed initial Git checkout can leave HEAD valid but no index.
    # Rebuild only the index and materialize missing files; never force-overwrite
    # existing files or reset a checkout that already has an index.
    if ((Test-Path -LiteralPath (Join-Path $Path '.git/HEAD')) -and
        (-not (Test-Path -LiteralPath (Join-Path $Path '.git/index')) -or (Test-Path -LiteralPath $marker))) {
        Write-Host 'Completing the interrupted CVAT checkout (preserving existing files)...'
        $null = Invoke-Native git @('-C', $Path, 'rev-parse', '--verify', 'HEAD') -Quiet
        Set-Content -LiteralPath $marker -Value 'Checkout recovery in progress'
        Invoke-Native git @('-C', $Path, 'config', '--local', 'core.longpaths', 'true')
        Invoke-Native git @('-C', $Path, 'read-tree', 'HEAD')
        $missing = Invoke-Native git @('-C', $Path, 'ls-files', '--deleted') -Quiet
        if (-not [string]::IsNullOrWhiteSpace($missing)) {
            # Write LF explicitly: PowerShell's native pipeline adds CRLF, and
            # checkout-index treats the CR as part of each filename.
            $startInfo = New-Object System.Diagnostics.ProcessStartInfo
            $startInfo.FileName = (Get-Command git).Source
            $startInfo.WorkingDirectory = $Path
            $startInfo.Arguments = 'checkout-index --stdin'
            $startInfo.UseShellExecute = $false
            $startInfo.CreateNoWindow = $true
            $startInfo.RedirectStandardInput = $true
            $process = [Diagnostics.Process]::Start($startInfo)
            try {
                $process.StandardInput.Write(($missing -replace "`r`n", "`n") + "`n")
                $process.StandardInput.Close()
                $process.WaitForExit()
                if ($process.ExitCode -ne 0) { throw 'Could not complete CVAT checkout. See scripts/STARTUP.md; existing files were not overwritten.' }
            } finally { $process.Dispose() }
        }
        Remove-Item -LiteralPath $marker
    }
}

function Wait-Ready {
    param([string]$Name, [scriptblock]$Probe, [int]$Timeout = $TimeoutSeconds, [scriptblock]$CheckFailure)
    Write-Host "Waiting for $Name (up to $Timeout seconds)..."
    $timer = [Diagnostics.Stopwatch]::StartNew()
    do {
        if ($CheckFailure) { & $CheckFailure }
        try { if (& $Probe) { return } } catch { }
        Start-Sleep -Seconds 2
    } while ($timer.Elapsed.TotalSeconds -lt $Timeout)
    throw "$Name did not become ready within $Timeout seconds. See scripts/STARTUP.md for diagnostic commands."
}

function Assert-ServiceRunning {
    param([string[]]$ComposeArguments, [string]$Service)
    $json = Invoke-Native docker ($ComposeArguments + @('ps', '--all', '--format', 'json', $Service)) -Quiet
    if ([string]::IsNullOrWhiteSpace($json)) { return }
    # Compose versions can return either a JSON array or one object per line.
    $containers = if ($json.TrimStart().StartsWith('[')) { $json | ConvertFrom-Json }
        else { $json -split '\r?\n' | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json } }
    foreach ($container in $containers) {
        if ($container.State -in @('exited', 'dead', 'restarting')) {
            throw "$Service container is $($container.State) (exit $($container.ExitCode)). Run: docker compose logs --tail 80 $Service"
        }
    }
}

function Test-HttpReady {
    param([string]$Url)
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
    return $response.StatusCode -eq 200
}

function Assert-Configuration {
    param($Config)
    $settings = $Config.services.backend.environment
    $required = @('POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB',
        'MINIO_ROOT_USER', 'MINIO_ROOT_PASSWORD', 'MINIO_BUCKET_NAME',
        'COMMA_JWT', 'CVAT_EMAIL', 'CVAT_PASSWORD')
    $missing = @($required | Where-Object {
        $value = [string]$settings.$_
        [string]::IsNullOrWhiteSpace($value) -or $value -match '(?i)fill this out|changeme|your[_ -].*here'
    })
    if ($missing.Count) { throw "Edit .env and fill in: $($missing -join ', '). Values were not printed." }
    if ([string]$settings.CVAT_EMAIL -notmatch '^[^@\s]+@[^@\s]+$') { throw 'CVAT_EMAIL must be an email address in .env.' }
}

function Start-Mila {
    $root = (Resolve-Path -LiteralPath $ProjectRoot).Path
    $envPath = Join-Path $root '.env'
    $composePath = Join-Path $root 'docker-compose.yaml'
    if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) { throw 'Project root must contain docker-compose.yaml.' }
    if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
        if (-not $CheckOnly) { Copy-Item -LiteralPath (Join-Path $root '.example_env') -Destination $envPath }
        throw 'Configuration is missing. Copy .example_env to .env (normal startup does this for you), fill in the credentials, and run again.'
    }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker was not found. Install Docker Desktop with the WSL 2 backend, start it in Linux-container mode, then run this launcher again.'
    }
    Write-Host 'Checking Docker Compose...'
    try { $null = Invoke-Native docker @('compose', 'version') -Quiet }
    catch { throw 'Docker Compose check failed. Run "docker compose version" in PowerShell for details. Install or repair Docker Desktop if Compose is unavailable.' }
    Write-Host 'Checking the Docker engine...'
    try { $osType = Invoke-Native docker @('info', '--format', '{{.OSType}}') -Quiet }
    catch { throw 'Cannot connect to the Docker engine. Open Docker Desktop and wait until the engine is running, then retry. Run "docker version" in PowerShell for the underlying connection error. If it still fails, check Docker Desktop troubleshooting and the selected Docker context.' }
    if ($osType.Trim() -ne 'linux') { throw 'Start Docker Desktop and switch to Linux containers.' }
    $compose = @('compose', '--ansi', 'never', '--progress', 'plain', '--project-directory', $root, '--env-file', $envPath, '-f', $composePath)
    Write-Host 'Checking Compose configuration and .env syntax...'
    try {
        $config = (Invoke-Native docker ($compose + @('config', '--format', 'json')) -Quiet) | ConvertFrom-Json
        # Compose escapes literal dollars for reusable config output. API payloads
        # and native command arguments need the original values, not that escaping.
        foreach ($property in $config.services.backend.environment.PSObject.Properties) {
            if ($property.Value -is [string]) { $property.Value = $property.Value.Replace('$$', '$') }
        }
    } catch {
        throw 'Docker Compose could not read the project configuration. Check .env quoting and Docker Compose compatibility. From the project folder, run "docker compose --env-file .env -f docker-compose.yaml config --quiet" for details. Review errors locally: malformed .env lines may contain credentials. Do not share unredacted configuration output.'
    }
    Assert-Configuration $config
    $license = Join-Path $root 'minio/minio.license'
    if (-not (Test-Path -LiteralPath $license -PathType Leaf) -or (Get-Item -LiteralPath $license).Length -eq 0) {
        throw 'Place your MinIO AIStor license in minio/minio.license, then run again. See README.md for the license link.'
    }
    $cvatRoot = Join-Path $root 'cvat'
    if (-not (Test-Path -LiteralPath $cvatRoot)) {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is required for first-time CVAT setup. Install Git for Windows, then run again.' }
    } elseif (-not (Test-Path -LiteralPath (Join-Path $cvatRoot 'docker-compose.yml')) -and
        -not (Test-Path -LiteralPath (Join-Path $cvatRoot '.git/HEAD'))) {
        throw 'The cvat folder exists but docker-compose.yml is missing. Restore a complete CVAT checkout before retrying.'
    }
    Write-Host 'Prerequisite checks passed.' -ForegroundColor Green
    if ($CheckOnly) { Write-Host 'CheckOnly: no containers started or files changed.'; return }

    foreach ($folder in @('data', 'data_exports', 'cvat_share', 'annotations')) {
        $null = New-Item -ItemType Directory -Force -Path (Join-Path $root $folder)
    }
    if (-not (Test-Path -LiteralPath $cvatRoot)) {
        Write-Host 'Downloading CVAT for first-time setup...'
        Invoke-Native git @('clone', '--config', 'core.longpaths=true', '--depth', '1', 'https://github.com/cvat-ai/cvat.git', $cvatRoot)
    }
    Repair-CvatCheckout $cvatRoot
    if (-not (Test-Path -LiteralPath (Join-Path $cvatRoot 'docker-compose.yml'))) {
        throw 'CVAT checkout is incomplete: docker-compose.yml is missing. See scripts/STARTUP.md.'
    }
    $networks = Invoke-Native docker @('network', 'ls', '--format', '{{.Name}}') -Quiet
    if ('cvat_network' -notin ($networks -split '\r?\n')) { Invoke-Native docker @('network', 'create', 'cvat_network') }

    $previousShare = $env:MILA_CVAT_SHARE
    $env:MILA_CVAT_SHARE = (Join-Path $root 'cvat_share').Replace('\', '/')
    try {
        $cvatCompose = @('compose', '--ansi', 'never', '--progress', 'plain', '--project-directory', $cvatRoot, '--env-file', $envPath,
            '-f', (Join-Path $cvatRoot 'docker-compose.yml'), '-f', (Join-Path $root 'docker-compose.cvat.windows.yml'))
        Write-Host 'Checking CVAT Compose configuration...'
        try { $cvatConfig = (Invoke-Native docker ($cvatCompose + @('config', '--format', 'json')) -Quiet) | ConvertFrom-Json }
        catch { throw 'CVAT Compose configuration is invalid. Check the CVAT checkout, docker-compose.cvat.windows.yml, and Docker Compose version. The application startup has not begun.' }
        Write-Host '[1/5] Starting PostgreSQL and MinIO...'
        Invoke-Native docker ($compose + @('up', '-d', '--no-recreate', 'postgres', 'minio'))
        Wait-Ready 'PostgreSQL' {
            $null = Invoke-Native docker ($compose + @('exec', '-T', 'postgres', 'pg_isready', '-U',
                [string]$config.services.postgres.environment.POSTGRES_USER, '-d', [string]$config.services.postgres.environment.POSTGRES_DB)) -Quiet
            return $true
        }
        Wait-Ready 'MinIO' { Test-HttpReady 'http://localhost:9000/minio/health/ready' }

        Write-Host '[2/5] Applying migrations and ensuring the storage bucket exists...'
        # Setup jobs do not read input. Explicitly disable console allocation:
        # PowerShell output piping can otherwise trigger an invalid handle error.
        $runArgs = @('run', '--rm', '--no-deps', '-T', '--interactive=false')
        if ($Rebuild) { $runArgs += '--build' }
        Invoke-Native docker ($compose + $runArgs + @('alembic_worker'))
        Invoke-Native docker ($compose + $runArgs + @('minio_initializer'))

        Write-Host '[3/5] Starting CVAT...'
        Invoke-Native docker ($cvatCompose + @('up', '-d', '--no-recreate'))
        # Older Windows installs did not pin Traefik's network. Only migrate
        # that server when necessary; normal launches retain running containers.
        $expectedNetwork = $cvatConfig.services.cvat_server.labels.'traefik.docker.network'
        $serverName = Invoke-Native docker @('ps', '-a', '--filter', 'name=^/cvat_server$', '--format', '{{.Names}}') -Quiet
        if ($expectedNetwork -and $serverName.Trim() -eq 'cvat_server') {
            $labels = (Invoke-Native docker @('inspect', 'cvat_server', '--format', '{{json .Config.Labels}}') -Quiet) | ConvertFrom-Json
            if ($labels.'traefik.docker.network' -ne $expectedNetwork) {
                Write-Host 'Repairing CVAT proxy network selection for this existing installation...'
                Invoke-Native docker ($cvatCompose + @('up', '-d', '--no-deps', 'cvat_server'))
            }
        }
        Wait-Ready 'CVAT API' { Test-HttpReady 'http://localhost:8080/api/server/about' }
        # Pass credentials through stdin, never command arguments or console logs.
        # Existing accounts are authenticated, never silently reset.
        $accountCode = @'
import json, sys
from django.contrib.auth import get_user_model
data = json.load(sys.stdin)
User = get_user_model()
username = data['email'].split('@')[0]
user = User.objects.filter(email=data['email']).first()
if user is None:
    user = User.objects.filter(username=username).first()
    if user is not None:
        raise RuntimeError('CVAT username already exists with a different email. Correct .env or the account.')
    user = User.objects.create_superuser(username=username, email=data['email'], password=data['password'])
if not user.is_active or not user.check_password(data['password']):
    raise RuntimeError('Existing CVAT credentials do not match .env, or the account is inactive.')
print('CVAT account ready.')
'@
        # Encoded script avoids Windows native argument quoting of Python strings.
        $encodedCode = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($accountCode))
        $accountPayload = @{email = $config.services.backend.environment.CVAT_EMAIL; password = $config.services.backend.environment.CVAT_PASSWORD} | ConvertTo-Json -Compress
        $accountArgs = $cvatCompose + @('exec', '-T', 'cvat_server', 'python', 'manage.py', 'shell', '-c', "exec(__import__('base64').b64decode('$encodedCode'))")
        $previousEncoding = $OutputEncoding
        try {
            $OutputEncoding = New-Object System.Text.UTF8Encoding $false
            $accountPayload | & docker @accountArgs
            if ($LASTEXITCODE -ne 0) { throw 'CVAT account setup failed. Check the account details in .env; existing passwords were not changed.' }
        } finally { $OutputEncoding = $previousEncoding }

        Write-Host '[4/5] Starting application and processing workers (first build can take a long time)...'
        $services = @('backend', 'open_pilot_download_worker', 'open_pilot_upload_worker',
            'dataset_export_worker', 'cvat_worker', 'cvat_import_export_worker', 'frontend')
        $upArgs = @('up', '-d')
        if ($Rebuild) { $upArgs += '--build' } else { $upArgs += '--no-recreate' }
        Invoke-Native docker ($compose + $upArgs + $services)
        Write-Host '[5/5] Checking the dashboard and worker containers...'
        Wait-Ready 'backend' { Test-HttpReady 'http://localhost:8000/health-check' } -CheckFailure { Assert-ServiceRunning $compose 'backend' }
        Wait-Ready 'dashboard' { Test-HttpReady 'http://localhost:5173' } -CheckFailure { Assert-ServiceRunning $compose 'frontend' }
        Wait-Ready 'application containers' {
            $running = Invoke-Native docker ($compose + @('ps', '--status', 'running', '--services')) -Quiet
            return @($services | Where-Object { $_ -notin ($running -split '\r?\n') }).Count -eq 0
        } -CheckFailure { foreach ($service in $services) { Assert-ServiceRunning $compose $service } }
        Write-Host 'MiLa is running: http://localhost:5173' -ForegroundColor Green
        Write-Host 'CVAT: http://localhost:8080 | Containers keep running when you close this window.'
        Write-Host 'Startup checks passed. Worker container status does not verify a complete route-processing run.'
        if (-not $NoBrowser) { Start-Process 'http://localhost:5173' }
    } finally { $env:MILA_CVAT_SHARE = $previousShare }
}

if ($MyInvocation.InvocationName -ne '.') {
    try { Start-Mila; exit 0 }
    catch { Write-Host "`nStartup stopped: $($_.Exception.Message)" -ForegroundColor Red; exit 1 }
}
