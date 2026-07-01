param(
    [string]$Show = "",

    [Parameter(Mandatory = $true)]
    [string]$CookieFile,

    [ValidateSet("cookie", "cookie_then_pot", "pot_then_cookie", "pot")]
    [string]$AuthMode = "cookie",

    [switch]$NoPush,

    [switch]$AllowDirty,

    [switch]$SkipFetch
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [string[]]$Arguments = @()
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Test-GitDiff {
    param([string[]]$Pathspec)

    & git diff --quiet -- @Pathspec
    return $LASTEXITCODE -ne 0
}

if (-not (Test-Path -LiteralPath $CookieFile)) {
    throw "Cookie file not found: $CookieFile"
}

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $pythonCommand = Get-Command python -ErrorAction Stop
    $python = $pythonCommand.Source
}

Get-Command git -ErrorAction Stop | Out-Null
Get-Command ffmpeg -ErrorAction Stop | Out-Null

$requiredEnv = @(
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY",
    "R2_SECRET_KEY",
    "R2_BUCKET",
    "R2_PUBLIC_URL"
)

$missingEnv = @()
foreach ($name in $requiredEnv) {
    $value = [Environment]::GetEnvironmentVariable($name, "Process")
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($name, "User")
    }
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    }
    if ($value) {
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    } else {
        $missingEnv += $name
    }
}

if ($missingEnv.Count -gt 0) {
    throw "Missing required environment variables: $($missingEnv -join ', ')"
}

if (-not $AllowDirty) {
    $status = & git status --porcelain
    if ($status) {
        throw "Working tree is not clean. Commit/stash changes or re-run with -AllowDirty."
    }
}

if (-not $SkipFetch) {
    Invoke-Checked -FilePath "git" -Arguments @("fetch", "origin")
    Invoke-Checked -FilePath "git" -Arguments @("rebase", "origin/main")
}

$cookieTarget = Join-Path $env:TEMP "torah-pod-yt-cookies.txt"
Copy-Item -LiteralPath $CookieFile -Destination $cookieTarget -Force

$previousCookieFile = $env:YOUTUBE_COOKIES_FILE
$previousAuthMode = $env:YOUTUBE_AUTH_MODE

try {
    $env:YOUTUBE_COOKIES_FILE = $cookieTarget
    $env:YOUTUBE_AUTH_MODE = $AuthMode

    $syncArgs = @("-m", "podcast_feeds.sync", "--source-type", "youtube", "--source-type", "youtube_playlist")
    if ($Show) {
        $syncArgs += @("--show", $Show)
    }

    & $python @syncArgs
    $syncExit = $LASTEXITCODE
    $showsChanged = Test-GitDiff -Pathspec @("shows")

    if ($syncExit -ne 0 -and -not $showsChanged) {
        throw "YouTube sync failed before changing episode metadata."
    }

    if (-not $showsChanged) {
        Write-Host "No YouTube episode changes detected."
        return
    }

    $buildArgs = @("-m", "podcast_feeds.build")
    $validateArgs = @("-m", "podcast_feeds.validate")
    if ($Show) {
        $buildArgs += @("--show", $Show)
        $validateArgs += @("--show", $Show)
    }

    Invoke-Checked -FilePath $python -Arguments $buildArgs
    Invoke-Checked -FilePath $python -Arguments $validateArgs

    Invoke-Checked -FilePath "git" -Arguments @("add", "shows", "public")
    & git diff --staged --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "No staged changes after build."
        return
    }

    Invoke-Checked -FilePath "git" -Arguments @("commit", "-m", "Sync YouTube episodes locally")

    if ($NoPush) {
        Write-Host "Committed local YouTube sync. Push skipped because -NoPush was set."
    } else {
        Invoke-Checked -FilePath "git" -Arguments @("push")
        Write-Host "Pushed local YouTube sync."
    }

    if ($syncExit -ne 0) {
        throw "YouTube sync had partial failures after preserving successful changes."
    }
}
finally {
    if ($null -eq $previousCookieFile) {
        Remove-Item Env:\YOUTUBE_COOKIES_FILE -ErrorAction SilentlyContinue
    } else {
        $env:YOUTUBE_COOKIES_FILE = $previousCookieFile
    }

    if ($null -eq $previousAuthMode) {
        Remove-Item Env:\YOUTUBE_AUTH_MODE -ErrorAction SilentlyContinue
    } else {
        $env:YOUTUBE_AUTH_MODE = $previousAuthMode
    }

    Remove-Item -LiteralPath $cookieTarget -Force -ErrorAction SilentlyContinue
}
