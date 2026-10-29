$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
. (Join-Path $root 'launcher/Account.ps1')
$env:PATH = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin;$env:ProgramFiles\Docker\Docker\resources\bin;$env:PATH"
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('mila-gui-test-' + [guid]::NewGuid().ToString('N'))
New-Item $fixture -ItemType Directory | Out-Null
function Assert([bool]$Condition, [string]$Message) { if (!$Condition) { throw $Message } }
try {
    [IO.File]::WriteAllText((Join-Path $fixture 'compose.yaml'), "services:`n  test:`n    image: alpine`n    environment:`n      PASSWORD: `${POSTGRES_PASSWORD}`n      MINIO_PASSWORD: `${MINIO_ROOT_PASSWORD}`n      CVAT_PASSWORD: `${CVAT_PASSWORD}`n      USER: `${POSTGRES_USER}`n      CVAT_EMAIL: `${CVAT_EMAIL}`n")
    foreach ($password in @('Abcd$efg#1234\end''quote"','Abcdef123456\','Abcdef1234\''test','Abcdef1234\\end','Abcdef$$12345','Abcd efgh 1234')) {
        [IO.File]::WriteAllText((Join-Path $fixture '.env'), (New-MilaEnvironment 'mila_test' $password 'eyJtest.payload.signature'))
        Assert ((Read-MilaAccount (Join-Path $fixture '.env')).POSTGRES_PASSWORD -ceq $password) 'Account display must decode the saved password'
        $json = & docker compose --project-directory $fixture config --format json
        Assert ($LASTEXITCODE -eq 0) 'Compose must accept generated .env'
        $account = ($json | ConvertFrom-Json).services.test.environment
        foreach ($key in @('PASSWORD','MINIO_PASSWORD','CVAT_PASSWORD')) {
            Assert ($account.$key.Replace('$$','$') -ceq $password) "Password roundtrip failed for $key"
        }
        Assert ($account.USER -ceq 'mila_test') 'Shared user was not preserved'
        Assert ($account.CVAT_EMAIL -ceq 'mila_test@mila.local') 'CVAT login email was not generated'
    }
    foreach ($bad in @(@('bad name','longpassword123','a.b.c'), @('valid','short','a.b.c'), @('valid','longpassword123','google_123'), @('valid',"long`npassword123",'a.b.c'))) {
        $rejected = $false
        try { New-MilaEnvironment @bad | Out-Null } catch { $rejected = $true }
        Assert $rejected 'Invalid account input must be rejected'
    }
    $before = [IO.File]::ReadAllText((Join-Path $fixture '.env'))
    $rejected = $false
    try { Save-MilaEnvironment $fixture 'replacement' 'missing.license' } catch { $rejected = $true }
    Assert $rejected 'Existing environment must not be overwritten'
    Assert ([IO.File]::ReadAllText((Join-Path $fixture '.env')) -ceq $before) 'Existing environment changed'
    Remove-Item -LiteralPath (Join-Path $fixture '.env')
    $license = Join-Path $fixture 'source.license'
    [IO.File]::WriteAllText($license,'TEST LICENSE - NOT REAL')
    $content = New-MilaEnvironment 'mila_test' 'longpassword123' 'a.b.c'
    Save-MilaEnvironment $fixture $content $license
    Assert ([IO.File]::ReadAllText((Join-Path $fixture '.env')) -ceq $content) 'Fresh config was not written'
    Assert (Test-Path (Join-Path $fixture 'minio/minio.license')) 'License was not copied'
    Write-Host 'PASS: Compose special-character roundtrip, shared accounts, validation, existing-file protection and fresh setup.'
} finally {
    $resolved = [IO.Path]::GetFullPath($fixture)
    if ($resolved.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()), [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf) -like 'mila-gui-test-*') { Remove-Item -LiteralPath $resolved -Recurse -Force }
}
