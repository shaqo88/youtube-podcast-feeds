# YouTube Sync Operations

This document explains the YouTube episode synchronization workflow, common patterns, and operational issues with their resolutions.

## Overview

The YouTube sync runs hourly via `.github/workflows/sync.yml` and discovers, downloads, and publishes episodes from configured YouTube sources (channels and playlists).

### Runner Selection

- **Preferred:** `google-youtube` self-hosted runner (labeled `["self-hosted", "google-youtube"]`)
- **Fallback:** `ubuntu-latest` GitHub-hosted runner
- **Configuration:** See `.github/workflows/sync.yml`, job `sync`, `runs-on` selector

The Google runner is preferred because it has a persistent environment and avoids repeated YouTube authentication challenges. GitHub-hosted runners are stateless and may encounter fresh bot-check blocks on every run.

### Authentication Methods

The sync supports multiple YouTube auth strategies in order, configured by `YOUTUBE_AUTH_MODE`:

1. **`pot_then_cookie`** (default for scheduled runs): Try PO-token provider first, fall back to browser cookies
2. **`cookie_then_pot`**: Try cookies first, fall back to PO-token
3. **`pot`**: Use only PO-token provider (requires bgutil Docker container)
4. **`cookie`**: Use only browser cookies
5. **`none`**: Use plain yt-dlp (prone to 403 blocks and bot-check)

**Cookie management:** Fresh browser cookies must be exported in Netscape format and updated via:
```powershell
$env:GH_CONFIG_DIR = "$env:LOCALAPPDATA\gh-codex-shaqo88"
.\scripts\set-youtube-cookies.ps1 -CookieFile "path/to/cookies.txt" -YouTubeAuthMode cookie_then_pot -RunSync
```

## Episode Lifecycle

### New Episode Discovery

1. Each sync discovers recent videos from configured tabs (videos, streams, community, etc.)
2. Videos are filtered by start date and live status
3. Each discovered video is checked for metadata and duration

### Metadata Phase

- Video is checked for title, description, duration, publish date
- If already known and recent (≤14 days), duration is checked for refresh eligibility
- Auth/bot-check blocks at this phase result in a skip with reason "sign in to confirm you're not a bot"

### Download Phase

- Audio is extracted and converted to MP3 (64 kbps)
- Uploaded to Cloudflare R2 storage
- If ≥120 seconds, record is saved and published
- If <120 seconds, episode is silently skipped (not reported)

### Skip Classification

All skips are classified as retryable or permanent:

| Reason | Phase | Retryable | Details |
|--------|-------|-----------|---------|
| `HTTP Error 403: Forbidden` | download, refresh | Yes | Audio fetch blocked; YouTube typically clears after hours |
| `sign in to confirm you're not a bot` | metadata, refresh | Yes | Auth/bot-check block; usually clears on next sync |
| `Requested format is not available` | download, refresh | Yes | PO-token provider failure; same as auth block |
| Video unavailable / private / removed | metadata | No | Permanent; recorded as unavailable |
| Short duration (<120s) | download | No | Not reported; silently skipped |
| Post-live (< 1 hour after publish) | metadata | No | Deferred; checked after 1-hour delay |

## Common Issues and Solutions

### Issue: Repeat 403 or Auth-Block Skips on Same Videos

**Symptom:** Same video IDs appear in skip reports on consecutive syncs with "HTTP Error 403: Forbidden".

**Root Cause:** Episodes published within the live refresh window (14 days) are checked on every sync for duration changes. If YouTube's access block persists across syncs, the same videos skip repeatedly, creating a hammering pattern.

**Solution (Deployed 2026-08-31):**

The sync now tracks retryable download failures in episode metadata:

1. First 403 or auth/bot-check block: Failure reason and time are stored in `last_failure_reason` and `last_failure_at`.
2. For six hours, subsequent syncs skip that episode via `_should_skip_403_retry()`.
3. Once the cooldown expires, the next scheduled sync retries automatically.
4. This prevents hourly hammering while allowing previously skipped episodes to recover without a manual dispatch.

**Operational Impact:**
- 403- or auth-blocked episodes will no longer appear on every hourly skip report
- They are automatically retried after a six-hour cooldown (or immediately with a forced manual retry)
- Extended refresh window from 7 to 14 days reduces refresh pressure

### Issue: YouTube Auth/Bot-Check Blocks

**Symptom:** Episodes show skip reason "sign in to confirm you're not a bot" or "gvs po token".

**Root Cause:** 
- YouTube detects unusual access patterns and issues bot-check challenges
- GitHub-hosted runners are particularly susceptible (stateless, fresh IP per run)
- High-frequency syncs on same videos within short window trigger detection

**Prevention:**
- Use Google self-hosted runner (has persistent environment and history)
- Stagger manual re-runs if possible
- If blocks persist, rotate cookie secret or wait for YouTube's detection to reset

### Issue: Missing Episodes After Sync Success

**Symptom:** Workflow shows success, but expected episodes aren't in the final output.

**Root Cause:** 
- Episodes are discovered but blocked during download (403 or auth challenge)
- These are marked retryable and deferred, not fatal to the workflow
- Next sync will retry them

**Investigation:**
1. Check the skip report in GitHub Actions job output
2. Look for "Prepare skipped episode notification" step output
3. Email notification (if configured) lists skipped videos and reasons
4. All skipped videos are retryable, so check back on the next sync

### Issue: Failed Dependabot PRs on Workflow Changes

**Symptom:** Dependabot bump PRs show validation failures in "Validate Android Wrapper" or "Validate Podcast Feeds".

**Root Cause:** Android wrapper workflow has locked SHA digests that must match the repo's validation tests. Dependabot updates can change workflow action versions, breaking the locked digest check.

**Solution:**
- Manually update `.github/workflows/android.yml` action digests to match the new versions
- Re-run the validation workflow
- Or merge the Dependabot PR and manually fix the workflow digests on a follow-up PR

## Operational Runbook

### Normal Sync Failure

1. Check workflow logs for phase (sync, build, deploy)
2. If sync phase failed with 403/auth block, this is expected and retryable
3. Next hourly sync will retry automatically
4. If urgent, manually trigger: `gh workflow run sync.yml --repo shaqo88/youtube-podcast-feeds`

### Cookie Expiry or Auth Degradation

1. Export fresh cookies from a logged-in browser profile (Netscape format)
2. Run: `.\scripts\set-youtube-cookies.ps1 -CookieFile "path" -YouTubeAuthMode cookie_then_pot -RunSync`
3. Script updates the `YOUTUBE_COOKIES` GitHub secret and re-triggers sync
4. Monitor the triggered run for success

### Persistent 403 Blocks

If the same videos repeatedly show 403 across multiple syncs (2–3 hours apart):

1. Check if YouTube has a system issue (unlikely but possible)
2. Try a different authentication mode: `gh workflow run sync.yml --repo shaqo88/youtube-podcast-feeds -f youtube_auth_mode=pot_then_cookie`
3. If still blocked, YouTube may have rate-limited the account; wait 24 hours before retrying

### Force a Retry After Refreshing Cookies

Scheduled syncs deliberately skip episodes that already have a recorded 403 to
avoid repeatedly hitting YouTube. After refreshing `YOUTUBE_COOKIES`, run a
one-time forced retry on the persistent Google runner:

```powershell
$env:GH_CONFIG_DIR = "$env:LOCALAPPDATA\gh-codex-shaqo88"
gh workflow run sync.yml --repo shaqo88/youtube-podcast-feeds -f runner=google-youtube -f youtube_auth_mode=cookie_then_pot -f force_retry_403=true
```

`force_retry_403` applies only to that manually dispatched run. Scheduled runs
continue using backoff protection.

## Configuration Reference

### `.github/workflows/sync.yml` Key Variables

| Variable | Source | Purpose |
|----------|--------|---------|
| `YOUTUBE_COOKIES` | GitHub Secrets | Netscape-format browser cookies for yt-dlp |
| `YOUTUBE_AUTH_MODE` | Workflow input (scheduled: `pot_then_cookie`, manual: user choice) | Auth strategy order |
| `force_retry_403` | Manual workflow input | Retry episodes that were previously deferred after a 403; use only after refreshing authentication. |
| `YOUTUBE_WPC_BROWSER_PATH` | Workflow detection | Path to Chrome/Chromium for PO-token provider |
| `LIVE_REFRESH_WINDOW_DAYS` | `podcast_feeds/sync.py` (currently 14) | Max age for duration re-checks |

### Episode Metadata

Stored in `shows/{show_slug}/episodes.json` per episode:

```json
{
  "id": "video_id",
  "title": "Episode Title",
  "published": "20260831",
  "duration": 3600,
  "url": "https://r2.example.com/...mp3",
  "size": 123456,
  "source_url": "https://youtube.com/watch?v=...",
  "last_failure_reason": "HTTP Error 403: Forbidden"
}
```

The `last_failure_reason` field is set when a 403 or auth block occurs and used to suppress retries on subsequent syncs.

## Future Improvements

- Implement exponential backoff for 403-blocked episodes (skip longer on repeated failures)
- Add per-episode retry counters to distinguish between transient and systemic blocks
- Monitor YouTube account-level rate limits and auto-pause syncs if near threshold
- Support persistent browser profile on self-hosted runner to further reduce bot-check blocks

