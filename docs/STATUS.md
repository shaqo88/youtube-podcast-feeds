# YouTube Podcast Feeds Status

Last updated: `2026-06-24` Israel time.

## Current State

| Area | Status |
| --- | --- |
| GitHub repository | Done: `https://github.com/shaqo88/youtube-podcast-feeds` |
| Visibility | Done: public |
| Local clone | Done: `C:\Users\ShaulRoyzen\Documents\personal\repos\youtube-podcast-feeds` |
| Git remote | Done: SSH, `git@github.com:shaqo88/youtube-podcast-feeds.git` |
| GitHub Pages | Done: workflow-based Pages deployment |
| Initial Wechter feed | Done: `https://shaqo88.github.io/youtube-podcast-feeds/wechter/feed.xml` |
| Wechter config | Done: `shows/wechter/config.yml` |
| Wechter artwork | Done: generated from supplied Chabadpedia image |
| R2 bucket | Done: `youtube-podcast-feeds` |
| Required GitHub secrets | Done: `YOUTUBE_COOKIES`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_BUCKET`, `R2_PUBLIC_URL` |
| First real sync | Done: workflow run `28057617760` processed 14 episodes |
| Public feed verification | Done: published feed currently contains 14 items |

## Completed Work

- Created public GitHub repo under `shaqo88`.
- Built a config-driven Python package for multi-show YouTube podcast feeds.
- Added the Wechter show with Hebrew metadata and start date `2026-06-11`.
- Generated podcast artwork at `shows/wechter/assets/podcast-cover.png`.
- Published initial zero-episode RSS feed through GitHub Pages.
- Added workflows for sync, rebuild, validation, and Pages deployment.
- Fixed invalid pinned Pages action references.
- Configured local repo SSH push to use the `shaqo88` key.
- Replaced the small 25-line cookie secret with a filtered browser cookie export
  after the first sync hit YouTube bot-check errors.
- Completed first real Wechter sync and committed 14 episode records plus the
  generated feed update.
- Manually deployed GitHub Pages after the first sync, because commits made by
  `GITHUB_TOKEN` do not trigger the separate Pages workflow.
- Updated the sync workflow so future sync runs deploy Pages directly after
  committing generated feed changes.

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

- Pull the committed `episodes.json` and generated feed changes locally.
- Run public validation for the updated feed and R2 media.
- Watch the next scheduled sync to confirm incremental updates remain stable.
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
