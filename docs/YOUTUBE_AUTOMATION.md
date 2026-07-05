# YouTube Automation

This document defines the current YouTube import operating model.

## Target Model

1. GitHub Actions runs the automatic scheduled scrape every hour.
2. `bgutil-ytdlp-pot-provider` is tried first.
3. `YOUTUBE_COOKIES` is used as the fallback.
4. If GitHub-hosted runners are blocked, the local Windows importer complements
   it from this machine.

This is intentionally redundant: GitHub Actions is the automatic cloud path,
and the local script is the practical fallback when YouTube blocks cloud IPs or
rotates browser cookies.

## Refresh The GitHub Cookie Secret

Export fresh YouTube cookies in Netscape format from a logged-in browser. The
file should start with:

```text
# Netscape HTTP Cookie File
```

Then update the GitHub Actions secret using the isolated `shaqo88` GitHub CLI
config:

```powershell
cd C:\Users\ShaulRoyzen\Documents\personal\repos\youtube-podcast-feeds
.\scripts\set-youtube-cookies.ps1 -CookieFile "C:\Users\ShaulRoyzen\Downloads\cookies.txt" -DryRun
.\scripts\set-youtube-cookies.ps1 -CookieFile "C:\Users\ShaulRoyzen\Downloads\cookies.txt" -RunSync
```

The helper filters Google/YouTube cookies, preserves the Netscape header, and
uses:

```powershell
$env:GH_CONFIG_DIR = "$env:LOCALAPPDATA\gh-codex-shaqo88"
```

It should not switch the global GitHub CLI account.

## Verify The GitHub Scheduled Path

Trigger a targeted Wechter run:

```powershell
$env:GH_CONFIG_DIR = "$env:LOCALAPPDATA\gh-codex-shaqo88"
gh workflow run sync.yml --repo shaqo88/youtube-podcast-feeds -f show=wechter -f youtube_auth_mode=cookie_then_pot
gh run watch --repo shaqo88/youtube-podcast-feeds --exit-status
```

Check recent runs:

```powershell
$env:GH_CONFIG_DIR = "$env:LOCALAPPDATA\gh-codex-shaqo88"
gh run list --repo shaqo88/youtube-podcast-feeds --workflow sync.yml --limit 10
```

## Configure Local Windows Complement

Set R2 values as persistent user environment variables. Use the actual
Cloudflare R2 values:

```powershell
[Environment]::SetEnvironmentVariable("R2_ACCOUNT_ID", "...", "User")
[Environment]::SetEnvironmentVariable("R2_ACCESS_KEY", "...", "User")
[Environment]::SetEnvironmentVariable("R2_SECRET_KEY", "...", "User")
[Environment]::SetEnvironmentVariable("R2_BUCKET", "...", "User")
[Environment]::SetEnvironmentVariable("R2_PUBLIC_URL", "...", "User")
```

Open a new PowerShell window after setting them, then test without pushing:

```powershell
cd C:\Users\ShaulRoyzen\Documents\personal\repos\youtube-podcast-feeds
.\scripts\run-local-youtube-sync.ps1 -Show wechter -CookieFile "C:\Users\ShaulRoyzen\Downloads\cookies.txt" -NoPush
```

If the test imports an episode and creates a local commit, review it and push:

```powershell
git status --short --branch
git log --oneline -3
git push
```

For normal local operation:

```powershell
.\scripts\run-local-youtube-sync.ps1 -Show wechter -CookieFile "C:\Users\ShaulRoyzen\Downloads\cookies.txt"
```

## Task Scheduler

After the local command succeeds manually, create a Windows Task Scheduler task.

Program:

```text
powershell.exe
```

Arguments:

```powershell
-ExecutionPolicy Bypass -File "C:\Users\ShaulRoyzen\Documents\personal\repos\youtube-podcast-feeds\scripts\run-local-youtube-sync.ps1" -Show wechter -CookieFile "C:\Users\ShaulRoyzen\Downloads\cookies.txt"
```

Recommended trigger: hourly.

Recommended settings:

- Run only when the user is logged on at first.
- Stop the task if it runs longer than 2 hours.
- Do not start a new instance if the task is already running.

## Failure Interpretation

- `YOUTUBE_COOKIES is not a Netscape-format cookie file`: export cookies again
  and re-run `set-youtube-cookies.ps1`.
- `provided YouTube account cookies are no longer valid`: export fresh cookies
  and update the GitHub secret.
- `Sign in to confirm you're not a bot`: try local sync; GitHub-hosted traffic
  may be blocked.
- `Missing required environment variables`: set the R2 user environment
  variables and open a new PowerShell window.
