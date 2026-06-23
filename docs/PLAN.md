# YouTube Podcast Feeds Plan

## Goal

Build a reusable repository that turns one or more YouTube channels into podcast
RSS feeds. Each podcast should be added by configuration, not by copying scripts.

The first show is:

- Slug: `wechter`
- Source: `https://www.youtube.com/@rabbi-wechter`
- Channel ID: `UCEtDOee11d-WSfH4z2G1vhA`
- Feed: `https://shaqo88.github.io/youtube-podcast-feeds/wechter/feed.xml`
- Start date: `2026-06-11`

## Architecture

- `shows/<slug>/config.yml` defines source channel, feed metadata, artwork,
  start date, and R2 object prefix.
- `shows/<slug>/episodes.json` stores durable episode metadata after successful
  upload.
- `podcast_feeds.sync` discovers channel videos, downloads audio with `yt-dlp`,
  converts to 64 kbps MP3, uploads to Cloudflare R2, and saves metadata.
- `podcast_feeds.build` generates static RSS under `public/<slug>/feed.xml` and
  copies artwork under `public/<slug>/assets/`.
- `podcast_feeds.validate` checks artwork, feed structure, GUIDs, enclosures,
  and optionally public feed/media reachability.
- GitHub Pages serves the `public/` directory through the Pages deployment
  workflow.
- Cloudflare R2 stores audio files in one generic bucket, separated by show
  prefix, for example `wechter/<video_id>.mp3`.

## Automation

- `Sync YouTube Podcasts` runs hourly and can also run manually for one show.
- `Rebuild Feeds` rebuilds RSS from checked-in episode metadata.
- `Validate Podcast Feeds` validates generated feeds on push and schedule.
- `Deploy GitHub Pages` publishes `public/` when generated feed files change.

## Adding Another Podcast

1. Create `shows/<new-slug>/config.yml`.
2. Add `shows/<new-slug>/episodes.json` with `{}`.
3. Add `shows/<new-slug>/assets/podcast-cover.png`, 1400-3000 px square.
4. Set a unique R2 prefix matching the slug.
5. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m podcast_feeds.build --show <new-slug>
   .\.venv\Scripts\python.exe -m podcast_feeds.validate --show <new-slug>
   ```

6. Commit and run the sync workflow manually for the new slug.

## Important Design Decisions

- Use a new generic repo instead of refactoring `enachmanson-feed`, so the
  Nachmanson migration remains isolated.
- Use one R2 bucket with per-show prefixes.
- Use stable GUIDs of the form `yt:video:<video_id>`.
- Do not retry permanently unavailable/private/deleted videos forever; they can
  be recorded as unavailable and excluded from feeds.
- Keep feed generation deterministic so rebuilds do not create noisy commits.
