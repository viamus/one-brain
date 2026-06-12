[CmdletBinding()]
param(
    [string]$CatalogPath = "C:\DoxieOS\training-corpora\awesome-agent-skills\README.md",
    [string]$DestinationRoot = "C:\DoxieOS\training-corpora\awesome-agent-skills-expanded",
    [int]$MaxRepos = 25,
    [switch]$Update,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $CatalogPath)) {
    throw "Catalog file not found: $CatalogPath"
}

New-Item -ItemType Directory -Force -Path $DestinationRoot | Out-Null

$content = Get-Content -Raw -Path $CatalogPath
$matches = [regex]::Matches(
    $content,
    "https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:/[^\s\)\""\]\<]*)?"
)

$excludedOwners = @(
    "user-attachments",
    "sponsors"
)

$seen = @{}
$repositories = New-Object System.Collections.Generic.List[object]

foreach ($match in $matches) {
    $owner = $match.Groups[1].Value
    $repo = $match.Groups[2].Value

    if ($excludedOwners -contains $owner) {
        continue
    }

    $repo = $repo.TrimEnd(".")
    if ($repo.EndsWith(".git")) {
        $repo = $repo.Substring(0, $repo.Length - 4)
    }

    $key = "$owner/$repo"
    if ($seen.ContainsKey($key)) {
        $seen[$key].SourceLinks += $match.Value
        continue
    }

    $entry = [PSCustomObject]@{
        Slug = $key
        CloneUrl = "https://github.com/$key.git"
        Destination = Join-Path $DestinationRoot ($key -replace "/", "__")
        DockerPath = "/mnt/doxie/training-corpora/awesome-agent-skills-expanded/$($key -replace "/", "__")"
        SourceLinks = @($match.Value)
    }

    $seen[$key] = $entry
    $repositories.Add($entry)
}

$selected = $repositories | Select-Object -First $MaxRepos
$manifestPath = Join-Path $DestinationRoot "manifest.json"

$selected |
    Select-Object Slug, CloneUrl, Destination, DockerPath, SourceLinks |
    ConvertTo-Json -Depth 8 |
    Set-Content -Path $manifestPath -Encoding UTF8

Write-Host "Catalog: $CatalogPath"
Write-Host "GitHub repositories discovered: $($repositories.Count)"
Write-Host "Selected for this batch: $($selected.Count)"
Write-Host "Manifest: $manifestPath"
Write-Host ""

foreach ($repository in $selected) {
    if ($DryRun) {
        Write-Host "Would clone: $($repository.CloneUrl) -> $($repository.Destination)"
        continue
    }

    if (Test-Path $repository.Destination) {
        if ($Update) {
            Write-Host "Updating: $($repository.Slug)"
            git -C $repository.Destination pull --ff-only
            if ($LASTEXITCODE -ne 0) {
                throw "git pull failed for $($repository.Slug)"
            }
        }
        else {
            Write-Host "Already exists, skipping: $($repository.Slug)"
        }
    }
    else {
        Write-Host "Cloning: $($repository.Slug)"
        git clone --depth 1 $repository.CloneUrl $repository.Destination
        if ($LASTEXITCODE -ne 0) {
            throw "git clone failed for $($repository.Slug)"
        }
    }
}

Write-Host ""
Write-Host "Expanded corpus path: $DestinationRoot"
Write-Host "Docker path: /mnt/doxie/training-corpora/awesome-agent-skills-expanded"
