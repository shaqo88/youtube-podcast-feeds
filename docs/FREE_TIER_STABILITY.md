# Free-Tier Stability

This document tracks the components that can affect Torah Pod cost,
availability, or manual maintenance while the project is intentionally running
without paid infrastructure.

## Policy

- Stay on free tiers until donations justify paid services.
- Prefer linked mode over metadata sync or media copying for existing RSS feeds.
- Keep YouTube and Drive media normalized to 64 kbps mono MP3 before R2 upload.
- Pause expansion before accepting surprise paid usage.
- Treat the weekly health workflow as an early warning, not as automatic
  deletion or rotation.

## Storage Guardrails

Cloudflare R2 is the main cost-sensitive component because YouTube and Drive
sources are copied to R2.

| Level | R2 Standard Storage | Action |
| --- | ---: | --- |
| Green | `< 7 GB` | Continue normal onboarding. |
| Warning | `7-9 GB` | Review growth and avoid mirrored existing feeds. |
| Critical | `>= 9 GB` | Pause new YouTube/Drive onboarding until storage is reduced or paid usage is approved. |

Existing RSS sources should use `delivery_mode: linked` by default. That keeps
Torah Pod's website current by scanning the upstream feed during builds while
avoiding both R2 audio copies and repository `episodes.json` snapshots. Use
`delivery_mode: remote` only when Torah Pod intentionally needs to publish its
own RSS feed that references upstream audio URLs. Use `delivery_mode: mirror`
only when Torah Pod needs its own durable audio copy.

Run a manual R2 usage report:

```powershell
$env:R2_ACCOUNT_ID = "..."
$env:R2_ACCESS_KEY = "..."
$env:R2_SECRET_KEY = "..."
$env:R2_BUCKET = "..."
.\.venv\Scripts\python.exe -m podcast_feeds.r2_usage
```

The weekly `Free-Tier Health Check` workflow runs the same report when R2
secrets are configured and emails the report when Gmail notification secrets
are configured.

## Component Inventory

| Component | Current Use | Free-Tier Risk | Recovery |
| --- | --- | --- | --- |
| GitHub Actions | Hourly sync, validation, deploys, onboarding approval | Public repositories are expected to stay free for standard Actions usage, but failures can block updates | Check failed runs, reduce unnecessary schedules if needed |
| GitHub Pages | Backup/public static site | Low cost risk | Keep Cloudflare Pages as parallel deployment |
| Cloudflare Pages | Primary free static site at `torah-pod.pages.dev` | Build/deploy limits and token expiry | Rerun deploy, rotate `CLOUDFLARE_PAGES_API_TOKEN` |
| Cloudflare R2 | Public MP3 storage for copied YouTube/Drive media | Storage can grow past free tier | Monitor weekly, avoid unnecessary copying, pause expansion near critical threshold |
| Cloudflare Worker | Public onboarding form backend | Request limits and Worker token expiry | Rotate `CLOUDFLARE_API_TOKEN`, keep GitHub issue forms as fallback |
| Google Drive API | Reads shared Drive folders through service account | API quota, folder sharing, or service account key issues | Re-share folders, rotate `GOOGLE_SERVICE_ACCOUNT_JSON`, reduce scan frequency if needed |
| Gmail app password | Failure, onboarding-request, new-episode, added-podcast, and weekly status emails from `torahyoupod@gmail.com` | App password can be revoked or blocked | Recreate an app password on `torahyoupod@gmail.com`; update `GMAIL_USER=torahyoupod@gmail.com` and `GMAIL_APP_PASSWORD` |
| YouTube cookies | Fallback auth for YouTube scraping | Cookies expire or YouTube blocks GitHub-hosted runners | Refresh cookies, use local YouTube sync fallback |
| Podcast Index API | Optional directory link discovery | Optional key quota or missing secrets | Skip discovery or rotate keys |

## Weekly Review

1. Open `Actions -> Free-Tier Health Check`.
2. Confirm the weekly email arrived.
3. Confirm R2 status is below the warning threshold.
4. Review recent workflow failures.
5. Confirm Cloudflare Pages deploys are succeeding after sync changes.
6. Check whether any new show uses `existing_feed` with `delivery_mode: mirror`.
7. Confirm Drive folders remain shared with the service account.
8. Confirm notification emails are still arriving.
9. Keep `site_config.yml` donation and contact options current, and verify PayBox, Bit, and contact email links still work.

## References

- Cloudflare R2 pricing: `https://developers.cloudflare.com/r2/pricing/`
- Cloudflare Pages limits: `https://developers.cloudflare.com/pages/platform/limits/`
- Cloudflare Workers pricing: `https://developers.cloudflare.com/workers/platform/pricing/`
- Google Drive API limits: `https://developers.google.com/workspace/drive/api/guides/limits`
- GitHub Actions billing: `https://docs.github.com/en/billing/concepts/product-billing/github-actions`
