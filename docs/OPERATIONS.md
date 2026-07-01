# Torah Pod Operations

This runbook covers recurring maintenance for the current GitHub
Actions/R2/GitHub Pages system.

## Routine Checks

Run these after onboarding a podcast and during normal operation:

```powershell
gh run list --repo shaqo88/youtube-podcast-feeds --limit 10
```

Check the public status page:

```text
https://shaqo88.github.io/youtube-podcast-feeds/status/
```

Check local feed generation before pushing manual config changes:

```powershell
.\.venv\Scripts\python.exe -m podcast_feeds.build
.\.venv\Scripts\python.exe -m podcast_feeds.validate
```

Use network validation after a successful sync or migration:

```powershell
.\.venv\Scripts\python.exe -m podcast_feeds.validate --network
```

## Refresh YouTube Cookies

Manual YouTube syncs require `YOUTUBE_COOKIES`. Refresh the secret when manual
YouTube sync runs fail with bot-check, sign-in, authentication, or age/consent
errors.

Scheduled syncs intentionally skip YouTube and process only stable non-YouTube
sources (`drive` and `existing_feed`). This avoids hourly failures when YouTube
rotates browser cookies or rejects GitHub-hosted traffic.

1. Sign in to YouTube in a normal browser profile that can view the source
   videos.
2. Export cookies in Netscape format. The file should start with
   `# Netscape HTTP Cookie File`.
3. Keep only `.youtube.com`, `youtube.com`, `.google.com`, and `google.com`
   lines.
4. Confirm that secure Google session cookies are present. Useful names include
   `__Secure-1PSID`, `__Secure-3PSID`, `SAPISID`, `APISID`, `SSID`, `HSID`, and
   `SID`.
5. Replace the GitHub Actions secret. GitHub Actions secrets have a practical
   payload limit near 48 KB. If `gh secret set` returns `HTTP 422: Value is too
   large`, use the helper script below; it automatically falls back from a
   broad Google/YouTube filter to an essential-cookie filter.

   ```powershell
   .\scripts\set-youtube-cookies.ps1 -CookieFile "C:\Users\ShaulRoyzen\Downloads\cookies.txt" -DryRun
   .\scripts\set-youtube-cookies.ps1 -CookieFile "C:\Users\ShaulRoyzen\Downloads\cookies.txt" -RunSync
   ```

   If the essential-cookie filter is still larger than the limit, export from a
   clean browser profile that is only logged in to Google/YouTube, then retry.
   The helper preserves the Netscape header required by `yt-dlp`; if the
   workflow says the cookie secret is not Netscape format, re-run the helper
   from the latest `main`.

6. Trigger a manual sync for the affected YouTube show:

   ```powershell
   gh workflow run sync.yml --repo shaqo88/youtube-podcast-feeds -f show=wechter
   ```

7. Watch the run:

   ```powershell
   gh run watch --repo shaqo88/youtube-podcast-feeds --exit-status
   ```

The sync workflow prints cookie line counts and Google/YouTube cookie counts,
but it does not print secret values.

## Rotate R2 Credentials

Rotate R2 credentials if a token was exposed, a maintainer leaves, or the
Cloudflare account policy requires rotation.

1. In Cloudflare, create a new R2 API token with access to the
   `youtube-podcast-feeds` bucket.
2. Update these GitHub Actions secrets:

   ```text
   R2_ACCESS_KEY
   R2_SECRET_KEY
   ```

3. Confirm these existing values still match the account and bucket:

   ```text
   R2_ACCOUNT_ID
   R2_BUCKET
   R2_PUBLIC_URL
   ```

4. Run a manual sync for a small or recently active show:

   ```powershell
   gh workflow run sync.yml --repo shaqo88/youtube-podcast-feeds -f show=wechter
   ```

5. Run published media validation after the sync:

   ```powershell
   gh workflow run validate.yml --repo shaqo88/youtube-podcast-feeds -f network=true
   ```

6. Revoke the old Cloudflare token only after the sync and validation pass.

## Change R2 Public URL

Changing `R2_PUBLIC_URL` affects all newly generated enclosure URLs. Do this
only when moving to a stable custom media domain.

1. Configure the new public R2 domain in Cloudflare.
2. Update the GitHub Actions secret:

   ```text
   R2_PUBLIC_URL
   ```

3. Rebuild only after confirming old URLs remain reachable or after accepting
   that regenerated feeds will point to the new domain.
4. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m podcast_feeds.build
   .\.venv\Scripts\python.exe -m podcast_feeds.validate --network
   ```

5. Commit and push the regenerated feeds if the URL change is intentional.

## Drive Service Account

Drive-based podcasts require `GOOGLE_SERVICE_ACCOUNT_JSON`.

Before approving a Drive onboarding request:

1. Share the Drive folder with the service account email as Viewer.
2. Run:

   ```text
   Actions -> Check Drive Folder -> Run workflow
   ```

3. Confirm at least one publishable file uses:

   ```text
   YYYY-MM-DD - Episode Title.ext
   ```

## Discover Platform Links

Platform links are intentionally conservative. The automation updates a show
only when a directory result proves the same RSS feed URL. Title-only matches
are reported for manual review and are not written to config.

Run locally:

```powershell
.\.venv\Scripts\python.exe -m podcast_feeds.discover_platform_links --write --report C:\tmp\platform-link-report.md
.\.venv\Scripts\python.exe -m podcast_feeds.build
.\.venv\Scripts\python.exe -m podcast_feeds.validate
```

Run in GitHub Actions:

```powershell
gh workflow run discover_platform_links.yml --repo shaqo88/youtube-podcast-feeds
```

Current automation:

- Apple Podcasts: auto-adds when Apple's `feedUrl` exactly matches the Torah
  Pod feed URL, or for `existing_feed` sources, the exact upstream source feed.
- Podcast Index: auto-adds by exact feed URL when `PODCASTINDEX_API_KEY` and
  `PODCASTINDEX_API_SECRET` secrets are configured.
- Spotify, Amazon, Zinc Music, and title-only Apple results: manual review.

Add manual links under `podcast.platforms`:

```yaml
podcast:
  platforms:
    apple: "https://podcasts.apple.com/..."
    spotify: "https://open.spotify.com/show/..."
    amazon: "https://music.amazon.com/podcasts/..."
    podcast_index: "https://podcastindex.org/podcast/..."
    zinc: "https://..."
```

## Failed Sync Triage

1. Open the failed run from `Actions -> Sync YouTube Podcasts`.
2. Check whether the failure is source-specific or infrastructure-wide.
3. For YouTube auth errors, refresh `YOUTUBE_COOKIES`.
4. For R2 upload errors, verify R2 secrets and bucket access.
5. For Drive errors, verify the folder is shared with the service account.
6. If the workflow committed successful episodes before failing, leave that
   commit in place. The workflow is designed to preserve partial success.
7. Re-run the workflow manually for the affected show after fixing the cause.
