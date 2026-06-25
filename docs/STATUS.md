# YouTube Podcast Feeds Status

Last updated: `2026-06-26` Israel time.

## Current State

| Area | Status |
| --- | --- |
| GitHub repository | Done: `https://github.com/shaqo88/youtube-podcast-feeds` |
| Visibility | Done: public |
| Local workspace | Done: present in the current workspace |
| Git remote | Done: SSH, `git@github.com:shaqo88/youtube-podcast-feeds.git` |
| GitHub Pages | Done: workflow-based Pages deployment |
| Initial Wechter feed | Done: `https://shaqo88.github.io/youtube-podcast-feeds/wechter/feed.xml` |
| Source types | Done: YouTube channel and Google Drive folder sources supported |
| Wechter config | Done: `shows/wechter/config.yml` |
| Nachmanson import | Done: copied config, artwork, 79 episodes, and generated feed; scheduled sync disabled until playlist ID is re-added |
| Wechter owner | Done: `Torah Pod <torahyoupod@gmail.com>` |
| Wechter artwork | Done: generated from supplied Chabadpedia image |
| R2 bucket | Done: `youtube-podcast-feeds` |
| Required GitHub secrets | Done: `YOUTUBE_COOKIES`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_BUCKET`, `R2_PUBLIC_URL` |
| First real sync | Done: workflow run `28057617760` processed 14 episodes |
| Public feed verification | Done: published feed currently contains 15 items |
| Directory submissions | Done: Apple Podcasts, Spotify, Amazon Music, Podcast Index submitted; awaiting ingestion/review |

## Completed Work

- Created public GitHub repo under `shaqo88`.
- Built a config-driven Python package for multi-show YouTube podcast feeds.
- Added Google Drive folder support for audio/video staging folders with R2
  podcast hosting.
- Added the Wechter show with Hebrew metadata and start date `2026-06-11`.
- Added Wechter owner `Torah Pod <torahyoupod@gmail.com>` for directory
  verification.
- Generated podcast artwork at `shows/wechter/assets/podcast-cover.png`.
- Published initial zero-episode RSS feed through GitHub Pages.
- Added workflows for sync, rebuild, validation, and Pages deployment.
- Fixed invalid pinned Pages action references.
- Configured repo SSH push to use the `shaqo88` key.
- Replaced the small 25-line cookie secret with a filtered browser cookie export
  after the first sync hit YouTube bot-check errors.
- Completed first real Wechter sync and committed 14 episode records plus the
  generated feed update.
- Added refresh logic for recent uploads so a short first capture can be
  overwritten once YouTube exposes the full final duration.
- Manually deployed GitHub Pages after the first sync, because commits made by
  `GITHUB_TOKEN` do not trigger the separate Pages workflow.
- Updated the sync workflow so future sync runs deploy Pages directly after
  committing generated feed changes.
- Added support for Drive source files that publish only when renamed to
  `YYYY-MM-DD - Episode Title.ext`.

## First Sync Notes

- Run URL: `https://github.com/shaqo88/youtube-podcast-feeds/actions/runs/28057617760`
- Result: success.
- Episodes processed: 14.
- Commit: `1f376fe` (`Sync podcast episodes`).
- Pages deployment for this sync was completed manually in run `28058555026`.
- Public feed verification showed 14 RSS items.
- Earlier failed run `28056815534` wrote only a 25-line cookie file and hit
  repeated YouTube bot-check errors.
- The newer filtered cookie export was much larger and included Google/YouTube
  session cookies; the successful run wrote a 135-line, 28,951-byte cookie file
  in GitHub Actions.

## Remaining Work

- Watch scheduled syncs to confirm incremental updates remain stable.
- Re-add the Nachmanson YouTube playlist ID in `shows/nachmanson/config.yml`
  before enabling scheduled sync for that show.
- After 24-72 hours, check secondary apps and submit manually where missing.
- Verify the submitted directories actually ingest the feed and show the latest
  episodes.
- Before adding a Drive-based show, create a Google service account, store
  `GOOGLE_SERVICE_ACCOUNT_JSON`, and share the source folder with that service
  account email.
- If YouTube auth fails later, refresh cookies again from a logged-in browser
  and keep only `.youtube.com` and `.google.com` lines.
- Consider adding a dedicated public custom domain for the R2 bucket later
  instead of relying on `r2.dev`.
- Consider adding a short operator runbook for refreshing cookies and rotating
  R2 credentials.

## Useful Commands

Check sync status:

```powershell
gh run view 28057617760 --repo shaqo88/youtube-podcast-feeds
```

Watch sync:

```powershell
gh run watch 28057617760 --repo shaqo88/youtube-podcast-feeds --exit-status
```

Run sync manually:

```powershell
gh workflow run sync.yml --repo shaqo88/youtube-podcast-feeds -f show=wechter
```

Build and validate locally:

```powershell
.\.venv\Scripts\python.exe -m podcast_feeds.build --show wechter
.\.venv\Scripts\python.exe -m podcast_feeds.validate --show wechter
```

Validate published feed and media after a successful sync:

```powershell
.\.venv\Scripts\python.exe -m podcast_feeds.validate --show wechter --network
```

## Directory Submission Checklist

Use feed URL:

```text
https://shaqo88.github.io/youtube-podcast-feeds/wechter/feed.xml
```

Apple Podcasts:

1. Sign in at `https://podcastsconnect.apple.com`.
2. Add or claim the show with the RSS feed URL.
3. Verify title, artwork, description, and owner contact.
4. Submit and wait for review.

Spotify:

1. Sign in at `https://creators.spotify.com`.
2. Add a podcast from the RSS feed URL.
3. Verify title and artwork.
4. Submit and wait for ingestion.

Amazon Music:

1. Sign in at `https://podcasters.amazon.com`.
2. Add the podcast from the RSS feed URL.
3. Verify ownership and artwork.
4. Submit and wait for validation/import.

Podcast Index:

1. Open `https://podcastindex.org/add`.
2. Paste the RSS feed URL.
3. Submit and complete any verification.

Secondary apps to check after 24-72 hours:

- Pocket Casts
- Podcast Addict
- Castbox
- Deezer
- iHeartRadio
- TuneIn
- Podchaser
- Listen Notes
