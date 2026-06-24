# YouTube Podcast Feeds Plan

## Goal

Build a reusable repository that turns one or more YouTube channels or Google
Drive folders into podcast RSS feeds. Each podcast should be added by
configuration, not by copying scripts.

The first show is:

- Slug: `wechter`
- Source: `https://www.youtube.com/@rabbi-wechter`
- Channel ID: `UCEtDOee11d-WSfH4z2G1vhA`
- Feed: `https://shaqo88.github.io/youtube-podcast-feeds/wechter/feed.xml`
- Start date: `2026-06-11`
- Owner: `Torah Pod <torahyoupod@gmail.com>`

## Architecture

- `shows/<slug>/config.yml` defines source type, feed metadata, artwork, start
  date, and R2 object prefix.
- `shows/<slug>/episodes.json` stores durable episode metadata after successful
  upload.
- `podcast_feeds.sync` discovers channel videos, downloads audio with `yt-dlp`,
  converts to 64 kbps MP3, uploads to Cloudflare R2, and saves metadata.
- Drive sources use a Google service account, read a shared Drive folder,
  ignore draft filenames, extract audio from audio/video files, normalize to
  64 kbps mono MP3, upload to R2, and save metadata.
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
- Recent live uploads are rechecked for a short window after publish so a
  first partial capture can be overwritten once YouTube finalizes the video.

## Adding Another Podcast

Use this minimal checklist for any show:

1. Start from an approved onboarding issue. Creators can use
   `https://shaqo88.github.io/youtube-podcast-feeds/onboard/` for either a
   YouTube channel or a Google Drive folder.
2. Pick a short lowercase slug, for example `newshow`.
3. Create `shows/newshow/config.yml`.
4. Add `shows/newshow/episodes.json` with `{}`.
5. Add square artwork at `shows/newshow/assets/podcast-cover.png`.
6. Set source metadata, `podcast.title`, `podcast.author`,
   `podcast.description`, `podcast.owner_name`, `podcast.owner_email`,
   `podcast.feed_url`, `podcast.artwork_url`, and `r2.prefix`.
   For YouTube, use `source.type: youtube`, `source.channel_url`, and
   `source.channel_id`. For Drive, use `source.type: drive` and
   `source.folder_id`.
7. Use a unique feed URL:
   `https://shaqo88.github.io/youtube-podcast-feeds/newshow/feed.xml`.
8. Use a unique R2 prefix matching the slug, for example `newshow`.
9. Build and validate locally:

   ```powershell
   .\.venv\Scripts\python.exe -m podcast_feeds.build --show newshow
   .\.venv\Scripts\python.exe -m podcast_feeds.validate --show newshow
   ```

10. Commit and push.
11. Run the first sync manually:

    ```powershell
    gh workflow run sync.yml --repo shaqo88/youtube-podcast-feeds -f show=newshow
    ```

12. After the sync succeeds, verify:

    ```powershell
    gh workflow run validate.yml --repo shaqo88/youtube-podcast-feeds -f show=newshow -f network=true
    ```

## Drive Source Rules

- Share the Drive folder with the Google service account email stored in
  `GOOGLE_SERVICE_ACCOUNT_JSON`.
- New Drive podcasts should be submitted through the public onboarding page or
  the `Drive Podcast Onboarding` GitHub issue form and approved before config
  is added.
- Use the `Check Drive Folder` manual workflow to verify folder access and file
  naming before approval.
- Creators can upload files with generic draft names. Draft names are ignored.
- A file publishes only after it is renamed to:

  ```text
  YYYY-MM-DD - Episode Title.ext
  ```

- Supported inputs include audio and video. Output is always a 64 kbps mono MP3
  stored in R2.
- Drive file ID is the stable episode identity, so renaming a synced file
  updates metadata without creating a duplicate.
- If a synced file changes in Drive, sync overwrites the R2 MP3.
- If a synced file is deleted from Drive, it remains in the podcast because R2
  is the durable public copy.

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

Current submission state:

- Apple Podcasts: submitted, awaiting review or ingestion.
- Spotify: submitted, awaiting ingestion.
- Amazon Music: submitted, awaiting validation or import.
- Podcast Index: submitted, awaiting verification or indexing.

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
