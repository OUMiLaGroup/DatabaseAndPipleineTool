# Package only application source. Accounts, licenses, CVAT checkout and datasets stay local.
#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
& (Join-Path $PSScriptRoot 'Build-Launcher.ps1')
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('mila-package-' + [Guid]::NewGuid().ToString('N') + '.zip')
$directories = @('alembic_worker', 'backend', 'cvat_import_export_worker', 'cvat_worker', 'dataset_export_worker', 'frontend', 'launcher', 'minio_initializer', 'open_pilot_download_worker', 'open_pilot_upload_worker', 'scripts', 'shared', 'tests')
$rootFiles = @('.example_env', '.gitignore', 'docker-compose.yaml', 'docker-compose.cvat.yml', 'docker-compose.cvat.windows.yml', 'docker-compose.gpu.yml', 'MiLa-Launcher.exe', 'pyproject.toml', 'pyrightconfig.json', 'README.md', 'requirements.txt', 'Start-MiLa.cmd', 'Start-MiLa-GUI.cmd')
$files = @($rootFiles | ForEach-Object { Get-Item -LiteralPath (Join-Path $root $_) })
foreach ($directory in $directories) {
    $files += Get-ChildItem -LiteralPath (Join-Path $root $directory) -File -Recurse | Where-Object {
        $_.FullName -notmatch '\\(node_modules|__pycache__|\.git|\.pytest_cache|dist|build|\.venv|venv)\\' -and
        $_.Name -notmatch '^(\.env|.*\.(license|pem|key|pfx|p12|log|zip|pyc|pyo))$' -and $_.Name -notlike '.env.*'
    }
}
try {
    $zip = [IO.Compression.ZipFile]::Open($temporary, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($file in $files) {
            $relative = $file.FullName.Substring($root.Length + 1).Replace('\', '/')
            [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.FullName, $relative, [IO.Compression.CompressionLevel]::Optimal)
        }
    } finally { $zip.Dispose() }
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
    $output = Join-Path $root 'MiLa-Installer.exe'
    & $compiler /nologo /target:winexe /platform:x64 /reference:System.Windows.Forms.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /reference:System.Web.Extensions.dll "/resource:$temporary,MiLa.Project.zip" "/out:$output" (Join-Path $PSScriptRoot 'Installer.cs')
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
    Write-Host "Built $output with $($files.Count) application files."
} finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary } }
