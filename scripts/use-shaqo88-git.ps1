param(
    [string]$Remote = "origin",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
Push-Location $repoRoot
try {

    gh auth switch --user shaqo88 | Out-Host
    $login = (gh api user --jq .login).Trim()
    if ($login -ne "shaqo88") {
        throw "GitHub CLI is authenticated as '$login', not 'shaqo88'. Aborting."
    }

    gh auth setup-git | Out-Host
    $remoteUrl = (git remote get-url $Remote).Trim()
    if ($remoteUrl -match "^git@github\.com:") {
        $remoteUrl = $remoteUrl -replace "^git@github\.com:", "https://github.com/"
        git remote set-url $Remote $remoteUrl
    }

    Write-Host "Verified GitHub account: $login"
    Write-Host "Pushing $Branch through $Remote..."
    git push $Remote "HEAD:$Branch"
}
finally {
    Pop-Location
}
