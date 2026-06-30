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

Refresh `YOUTUBE_COOKIES` when sync runs fail with bot-check, sign-in,
authentication, or age/consent errors.

1. Sign in to YouTube in a normal browser profile that can view the source
   videos.
2. Export cookies in Netscape format.
3. Keep only `.youtube.com`, `youtube.com`, `.google.com`, and `google.com`
   lines.
4. Confirm that secure Google session cookies are present. Useful names include
   `__Secure-1PSID`, `__Secure-3PSID`, `SAPISID`, `APISID`, `SSID`, `HSID`, and
   `SID`.
5. Replace the GitHub Actions secret:

   ```text
   Settings -> Secrets and variables -> Actions -> Secrets -> YOUTUBE_COOKIES
   ```

6. Trigger a manual sync for the affected show:

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

## Failed Sync Triage

1. Open the failed run from `Actions -> Sync YouTube Podcasts`.
2. Check whether the failure is source-specific or infrastructure-wide.
3. For YouTube auth errors, refresh `YOUTUBE_COOKIES`.
4. For R2 upload errors, verify R2 secrets and bucket access.
5. For Drive errors, verify the folder is shared with the service account.
6. If the workflow committed successful episodes before failing, leave that
   commit in place. The workflow is designed to preserve partial success.
7. Re-run the workflow manually for the affected show after fixing the cause.
