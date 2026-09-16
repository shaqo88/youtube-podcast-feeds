param(
    [string]$Remote = "origin",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
Push-Location $repoRoot
try {

    $ghConfig = Join-Path $env:LOCALAPPDATA "gh-codex-shaqo88"
    if (-not (Test-Path $ghConfig)) {
        throw "Missing scoped GH CLI configuration: $ghConfig"
    }
    $env:GH_CONFIG_DIR = $ghConfig
    $login = (gh api user --jq .login).Trim()
    if ($login -ne "shaqo88") {
        throw "GitHub CLI is authenticated as '$login', not 'shaqo88'. Aborting."
    }

    git config --global --add safe.directory ([string]$repoRoot)
    git config --global --unset-all url.ssh://git@github.com/.insteadof 2>$null
    $remoteUrl = (git remote get-url $Remote).Trim()
    if ($remoteUrl -match "^(git@github\.com:|ssh://git@github\.com/)") {
        $remoteUrl = $remoteUrl -replace "^(git@github\.com:|ssh://git@github\.com/)", "https://github.com/"
        git remote set-url $Remote $remoteUrl
    }

    Write-Host "Verified GitHub account: $login"
    Write-Host "Pushing $Branch through $Remote..."
    $credentialHelper = "!gh auth git-credential"
    git -c credential.helper= -c "credential.helper=$credentialHelper" push $Remote "HEAD:$Branch"
}
finally {
    Pop-Location
}
