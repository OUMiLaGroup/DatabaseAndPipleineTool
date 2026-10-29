# Reusable, idempotent default setup through the public application API.
#Requires -Version 5.1
param([string]$ApiUrl = 'http://localhost:8000')
$ErrorActionPreference = 'Stop'
$definitions = Invoke-RestMethod -Uri "$ApiUrl/job-definitions/" -TimeoutSec 20
foreach ($preset in @('general-detection.json', 'monocular-depth.json')) {
    $payload = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot $preset)
    $definition = $payload | ConvertFrom-Json
    $existing = @($definitions | Where-Object { ([string]$_.name).Trim() -ieq $definition.name })
    if ($existing.Count) {
        Write-Host "$($definition.name) already exists (job definition $($existing[0].job_def_id))."
        continue
    }
    $created = Invoke-RestMethod -Method Post -Uri "$ApiUrl/job-definitions/" -ContentType 'application/json' -Body $payload -TimeoutSec 20
    Write-Host "Created $($definition.name) (job definition $($created.job_def_id))."
}
