function ConvertTo-DotEnvValue([string]$Value) {
    if ($Value -match '[\r\n\x00]') { throw 'Account fields must be a single line.' }
    # Double quotes support trailing backslashes; $$ disables Compose interpolation.
    return '"' + $Value.Replace('\', '\\').Replace('"', '\"').Replace('$', '$$') + '"'
}
function New-MilaEnvironment([string]$Username, [string]$Password, [string]$Token) {
    if ($Username -cnotmatch '^[a-z][a-z0-9_]{2,31}$') { throw 'Username: 3-32 lowercase letters, digits or underscores; begin with a letter.' }
    if ($Password.Length -lt 12) { throw 'Use a password with at least 12 characters.' }
    if ($Token -notmatch '^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$') { throw 'Paste the JWT from jwt.comma.ai, not a google_ account ID or URL.' }
    $values = [ordered]@{
        CONDA_ENV_NAME='openpilot'; RUN_MODEL_ON_CPU_OR_NOT='true'; REPLACE_CEREAL_SERVICE_OR_NOT='true'
        POSTGRES_USER=$Username; POSTGRES_PASSWORD=$Password; POSTGRES_DB='db'
        MINIO_ROOT_USER=$Username; MINIO_ROOT_PASSWORD=$Password; MINIO_BUCKET_NAME='data'
        COMMA_JWT=$Token; CVAT_EMAIL="$Username@mila.local"; CVAT_PASSWORD=$Password
    }
    return (($values.GetEnumerator() | ForEach-Object { $_.Key + '=' + (ConvertTo-DotEnvValue $_.Value) }) -join "`r`n") + "`r`n"
}
function Save-MilaEnvironment([string]$Root, [string]$Content, [string]$License) {
    $path = Join-Path $Root '.env'
    if (Test-Path $path) { throw 'An existing .env was found. It will not be overwritten.' }
    foreach ($folder in @('postgres_data', 'minio/data')) {
        if ((Test-Path (Join-Path $Root $folder)) -and (Get-ChildItem (Join-Path $Root $folder) -Force | Select-Object -First 1)) {
            throw 'Existing database/storage data found. Restore its original .env before continuing.'
        }
    }
    if (!(Test-Path -LiteralPath $License -PathType Leaf) -or (Get-Item -LiteralPath $License).Length -eq 0) { throw 'Select a nonempty MinIO license file.' }
    $destination = Join-Path $Root 'minio/minio.license'
    New-Item (Split-Path $destination) -ItemType Directory -Force | Out-Null
    if ([IO.Path]::GetFullPath($License) -ne [IO.Path]::GetFullPath($destination)) {
        if (Test-Path $destination) { throw 'A MinIO license already exists. Select that file to keep it.' }
        Copy-Item -LiteralPath $License -Destination $destination
    }
    # CreateNew prevents overwriting a configuration created by another launcher.
    $stream = New-Object IO.FileStream($path, [IO.FileMode]::CreateNew)
    try { $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes($Content); $stream.Write($bytes,0,$bytes.Length) }
    finally { $stream.Dispose() }
}
function Read-MilaAccount([string]$Path) {
    $values = [ordered]@{}
    foreach ($line in [IO.File]::ReadAllLines($Path)) {
        if ($line -match '^\s*([A-Z_]+)\s*=(.*)$') {
            $key = $Matches[1]; $value = $Matches[2].Trim()
            if ($value.StartsWith('"') -and $value.EndsWith('"')) {
                try { $value = ($value | ConvertFrom-Json).Replace('$$','$') } catch { }
            } elseif ($value.StartsWith("'") -and $value.EndsWith("'")) {
                $value = $value.Substring(1,$value.Length-2).Replace("\'", "'")
            }
            $values[$key] = $value
        }
    }
    return $values
}
