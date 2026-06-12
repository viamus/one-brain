[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$PreserveJobStatus
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$postgresVolume = if ($env:ONEBRAIN_POSTGRES_VOLUME) { $env:ONEBRAIN_POSTGRES_VOLUME } else { "onebrain_postgres_data" }
$qdrantVolume = if ($env:ONEBRAIN_QDRANT_VOLUME) { $env:ONEBRAIN_QDRANT_VOLUME } else { "onebrain_qdrant_storage" }
$jobStatusVolume = if ($env:ONEBRAIN_JOB_STATUS_VOLUME) { $env:ONEBRAIN_JOB_STATUS_VOLUME } else { "onebrain_job_status" }
$mlArtifactsVolume = if ($env:ONEBRAIN_ML_ARTIFACTS_VOLUME) { $env:ONEBRAIN_ML_ARTIFACTS_VOLUME } else { "onebrain_ml_artifacts" }

$volumesToRemove = @(
    $postgresVolume,
    $qdrantVolume
)

if (-not $PreserveJobStatus) {
    $volumesToRemove += $jobStatusVolume
}

$preservedVolumes = @(
    $mlArtifactsVolume
)

Write-Host "OneBrain lab reset"
Write-Host "Repository: $repoRoot"
Write-Host ""
Write-Host "Will remove:"
$volumesToRemove | ForEach-Object { Write-Host "  - $_" }
Write-Host ""
Write-Host "Will preserve:"
$preservedVolumes | ForEach-Object { Write-Host "  - $_" }
Write-Host ""

if (-not $Apply) {
    Write-Host "Dry run only. Re-run with -Apply to reset the lab data volumes."
    exit 0
}

Write-Host "Stopping and removing OneBrain containers..."
docker compose down
if ($LASTEXITCODE -ne 0) {
    throw "docker compose down failed"
}

foreach ($volume in $volumesToRemove) {
    docker volume inspect $volume *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Removing Docker volume: $volume"
        docker volume rm $volume
        if ($LASTEXITCODE -ne 0) {
            throw "failed to remove Docker volume: $volume"
        }
    }
    else {
        Write-Host "Docker volume not found, skipping: $volume"
    }
}

Write-Host "Recreating OneBrain stack with empty PostgreSQL/Qdrant data..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    throw "docker compose up failed"
}

Write-Host ""
Write-Host "OneBrain lab reset complete."
