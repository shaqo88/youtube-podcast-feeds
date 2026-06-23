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
- Owner: `Torah Pod <torahyoupod@gmail.com>`

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

Use this minimal checklist:

1. Pick a short lowercase slug, for example `newshow`.
2. Create `shows/newshow/config.yml`.
3. Add `shows/newshow/episodes.json` with `{}`.
4. Add square artwork at `shows/newshow/assets/podcast-cover.png`.
5. Set `source.channel_url`, `source.channel_id`, `source.start_date`,
   `podcast.title`, `podcast.author`, `podcast.description`,
   `podcast.owner_name`, `podcast.owner_email`, `podcast.feed_url`,
   `podcast.artwork_url`, and `r2.prefix`.
6. Use a unique feed URL:
   `https://shaqo88.github.io/youtube-podcast-feeds/newshow/feed.xml`.
7. Use a unique R2 prefix matching the slug, for example `newshow`.
8. Build and validate locally:

   ```powershell
   .\.venv\Scripts\python.exe -m podcast_feeds.build --show newshow
   .\.venv\Scripts\python.exe -m podcast_feeds.validate --show newshow
   ```

9. Commit and push.
10. Run the first sync manually:

    ```powershell
    gh workflow run sync.yml --repo shaqo88/youtube-podcast-feeds -f show=newshow
    ```

11. After the sync succeeds, verify:

    ```powershell
    gh workflow run validate.yml --repo shaqo88/youtube-podcast-feeds -f show=newshow -f network=true
    ```

## Submission Steps

Use the feed URL:

```text
https://shaqo88.github.io/youtube-podcast-feeds/wechter/feed.xml
```

Apple Podcasts:

1. Sign in at `https://podcastsconnect.apple.com`.
2. Open `Add Show`.
3. Choose `RSS feed`.
4. Paste the feed URL.
5. Confirm the show metadata, artwork, and ownership contact.
6. Submit and wait for Apple review/ingestion.

Spotify:

1. Sign in at `https://creators.spotify.com`.
2. Add or claim a podcast.
3. Paste the feed URL.
4. Confirm the show title, artwork, and description.
5. Submit and wait for Spotify to ingest the feed.

Amazon Music:

1. Sign in at `https://podcasters.amazon.com`.
2. Add a podcast with an RSS feed.
3. Paste the feed URL.
4. Confirm ownership and artwork.
5. Submit and wait for Amazon to validate and import.

Podcast Index:

1. Open `https://podcastindex.org/add`.
2. Paste the feed URL.
3. Submit the show and confirm any email verification.

Secondary apps to check after 24-72 hours:

- Pocket Casts
- Podcast Addict
- Castbox
- Deezer
- iHeartRadio
- TuneIn
- Podchaser
- Listen Notes

## Important Design Decisions

- Use a new generic repo instead of refactoring `enachmanson-feed`, so the
  Nachmanson migration remains isolated.
- Use one R2 bucket with per-show prefixes.
- Use stable GUIDs of the form `yt:video:<video_id>`.
- Do not retry permanently unavailable/private/deleted videos forever; they can
  be recorded as unavailable and excluded from feeds.
- Keep feed generation deterministic so rebuilds do not create noisy commits.
