[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]]$RepoUrl,

    [string]$DestinationRoot = "C:\DoxieOS\training-corpora",

    [switch]$Update
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $DestinationRoot | Out-Null

foreach ($url in $RepoUrl) {
    $normalized = $url.Trim().TrimEnd("/")
    $repoName = Split-Path $normalized -Leaf
    if ($repoName.EndsWith(".git")) {
        $repoName = $repoName.Substring(0, $repoName.Length - 4)
    }
    if (-not $repoName) {
        throw "Cannot derive repository name from URL: $url"
    }

    $destination = Join-Path $DestinationRoot $repoName
    if (Test-Path $destination) {
        if ($Update) {
            Write-Host "Updating corpus: $destination"
            git -C $destination pull --ff-only
            if ($LASTEXITCODE -ne 0) {
                throw "git pull failed for $destination"
            }
        }
        else {
            Write-Host "Corpus already exists, skipping: $destination"
        }
    }
    else {
        Write-Host "Cloning corpus: $url -> $destination"
        git clone --depth 1 $url $destination
        if ($LASTEXITCODE -ne 0) {
            throw "git clone failed for $url"
        }
    }

    [PSCustomObject]@{
        RepoUrl = $url
        Path = $destination
        DockerPath = "/mnt/doxie/training-corpora/$repoName"
    }
}
