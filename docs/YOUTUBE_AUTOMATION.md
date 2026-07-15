# YouTube Automation

This document defines the current YouTube import operating model.

## Target Model

1. GitHub Actions runs the automatic scheduled scrape every hour on the
   `google-youtube` self-hosted runner.
2. Scheduled runs use `youtube_auth_mode=none` so they do not depend on browser
   cookies or PO-token helpers.
3. GitHub-hosted `ubuntu-latest` remains the normal path for validation,
   GitHub Pages, and Cloudflare Pages deploys.
4. Manual runs can still target `google-youtube`, `github-hosted`, or a local
   WSL/self-hosted fallback when needed.
5. The local Windows importer remains available as a manual complement from
   this machine.

This is intentionally redundant: Google is the automatic YouTube path,
GitHub-hosted runners handle validation/deploy work, and the local script is the
manual fallback when a cloud path is blocked or needs debugging.

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
.\scripts\set-youtube-cookies.ps1 -CookieFile "C:\Users\ShaulRoyzen\Downloads\cookies.txt" -YouTubeAuthMode cookie_then_pot -RunSync
```

The helper filters Google/YouTube cookies, preserves the Netscape header, and
uses:

```powershell
$env:GH_CONFIG_DIR = "$env:LOCALAPPDATA\gh-codex-shaqo88"
```

It should not switch the global GitHub CLI account.

If only one show needs to be retried, pass the show slug:

```powershell
.\scripts\set-youtube-cookies.ps1 -CookieFile "C:\Users\ShaulRoyzen\Downloads\cookies.txt" -Show wechter -YouTubeAuthMode cookie_then_pot -RunSync
```

## Cookie Failure Email Recovery

When the scheduled sync fails in a way that looks like stale or invalid YouTube
cookies, the workflow sends an email with:

- The failed GitHub Actions run URL.
- Whether a cookie refresh was detected as likely required.
- The exact PowerShell command to update `YOUTUBE_COOKIES`.
- The exact `gh workflow run` command to rerun sync.
- The tail of the sync log for triage.

The failure email is sent from `Torah Pod <torahyoupod@gmail.com>`. If no email
arrives, confirm the repository secrets use `GMAIL_USER=torahyoupod@gmail.com`
and a matching `GMAIL_APP_PASSWORD`.

The normal recovery is:

```powershell
cd C:\Users\ShaulRoyzen\Documents\personal\repos\youtube-podcast-feeds
$env:GH_CONFIG_DIR = "$env:LOCALAPPDATA\gh-codex-shaqo88"
.\scripts\set-youtube-cookies.ps1 -CookieFile "C:\Users\ShaulRoyzen\Downloads\cookies.txt" -YouTubeAuthMode cookie_then_pot -RunSync
```

Replace the cookie path if the browser export has a different file name. With
`-RunSync`, the helper updates the GitHub secret and immediately reruns the
sync workflow, so a separate "I renewed" action is not needed.

## Verify The GitHub Scheduled Path

Trigger a targeted Wechter run:

```powershell
$env:GH_CONFIG_DIR = "$env:LOCALAPPDATA\gh-codex-shaqo88"
gh workflow run sync.yml --repo shaqo88/youtube-podcast-feeds -f show=wechter -f runner=google-youtube -f youtube_auth_mode=none
gh run watch --repo shaqo88/youtube-podcast-feeds --exit-status
```

Check recent runs:

```powershell
$env:GH_CONFIG_DIR = "$env:LOCALAPPDATA\gh-codex-shaqo88"
gh run list --repo shaqo88/youtube-podcast-feeds --workflow sync.yml --limit 10
```

## Use The Google YouTube Runner

Use this when a skipped-video email says a runner hit a YouTube bot-check block,
or when a targeted YouTube sync is urgent.

Start or confirm the Google Cloud self-hosted runner for this repository with
the custom label:

```text
google-youtube
```

The runner host needs Docker, `sudo apt-get`, outbound internet access,
`ffmpeg`, Chrome or Chromium, and enough disk space for temporary downloads.
An Ubuntu runner is the intended target because `sync.yml` installs packages
with `apt-get` and uses Linux paths.

On a NetFree connection, install a combined CA bundle at:

```text
~/.netfree-ca-bundle.crt
```

The workflow exports that bundle for `curl`, Git, Node, Python, and yt-dlp on
self-hosted runs. This fixes certificate verification errors, but it does not
bypass NetFree policy blocks. If YouTube, Transistor, Captivate, or Cloudflare
URLs return `HTTP 418 Blocked by NetFree`, open those domains/URLs in NetFree
before rerunning.

After the runner shows as online in GitHub, run:

```powershell
$env:GH_CONFIG_DIR = "$env:LOCALAPPDATA\gh-codex-shaqo88"
gh workflow run sync.yml --repo shaqo88/youtube-podcast-feeds -f show=nachmanson -f runner=google-youtube -f youtube_auth_mode=none
gh run watch --repo shaqo88/youtube-podcast-feeds --exit-status
```

Manual runs with `runner=github-hosted` continue to use GitHub-hosted
`ubuntu-latest`; scheduled runs use `google-youtube`.

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
