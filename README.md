# youtube-podcast-feeds

Config-driven podcast RSS generator for YouTube channels, YouTube playlists,
Google Drive folders, and combined YouTube + Drive shows.

## Feed URLs

- Wechter: `https://shaqo88.github.io/youtube-podcast-feeds/wechter/feed.xml`
- Nachmanson: `https://shaqo88.github.io/youtube-podcast-feeds/nachmanson/feed.xml`
- Onboarding: `https://shaqo88.github.io/youtube-podcast-feeds/onboard/`

## How it works

1. Show configs live under `shows/<slug>/config.yml`.
   A show may have one source or multiple sources.
2. `python -m podcast_feeds.sync --show <slug>` discovers new source items,
   normalizes them to podcast MP3 where needed, uploads audio to Cloudflare R2,
   and updates `shows/<slug>/episodes.json`.
3. `python -m podcast_feeds.build --show <slug>` writes static RSS and artwork
   files under `public/<slug>/`.
4. GitHub Pages serves `public/` as the published podcast site.

## Required secrets

- `YOUTUBE_COOKIES`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY`
- `R2_SECRET_KEY`
- `R2_BUCKET`
- `R2_PUBLIC_URL`
- `GMAIL_USER` and `GMAIL_APP_PASSWORD` are optional for failure mail.

`YOUTUBE_COOKIES` is required for YouTube shows. `GOOGLE_SERVICE_ACCOUNT_JSON`
is required for Drive shows.

## Google Drive Shows

Drive folders are treated as staging inboxes. The published podcast uses R2
copies, not Drive URLs.

New podcasts can be requested through the public onboarding page:

```text
https://shaqo88.github.io/youtube-podcast-feeds/onboard/
```

It supports YouTube channels, YouTube playlists, Google Drive folders, and
YouTube + Drive combinations. The page submits to a Cloudflare Worker that
creates a GitHub issue for maintainer approval. The page defaults to Hebrew and
includes an English toggle. Podcast name is optional; if it is blank, the
speaker/rabbi name is used. The short English URL name is required and becomes
the show slug and feed path. To add a source to an existing podcast, submit the
same slug; approval appends only missing sources. Worker setup is documented in
`docs/ONBOARDING_WORKER.md`.

Requests can also be opened directly through GitHub issue forms:

```text
Issues -> New issue
```

Submitted requests are advisory only. A maintainer approves a request by adding
the `approved` label. For Drive requests, run the folder check workflow first.
The approval workflow creates the show config, runs the first sync, deploys the
feed, comments on the issue, removes `needs-approval`, and closes the issue.

Use this source config shape for one source:

```yaml
source:
  type: drive
  folder_id: "<google-drive-folder-id>"
  start_date: "2026-06-11"
  filename_pattern: "date_dash_title"
```

Use `sources:` for a combined podcast:

```yaml
sources:
  - type: youtube
    channel_url: "https://www.youtube.com/@example"
    channel_id: "UC..."
    tabs: ["videos", "streams", "shorts"]
    start_date: "2026-06-11"
    scan_limit_per_tab: 300
  - type: drive
    folder_id: "<google-drive-folder-id>"
    start_date: "2026-06-11"
    filename_pattern: "date_dash_title"
```

Setup:

1. Create a Google service account.
2. Store its JSON credential as the GitHub Actions secret
   `GOOGLE_SERVICE_ACCOUNT_JSON`.
3. Share the Drive folder with the service account email as Viewer.
4. Ask the creator to upload audio or video files and rename only finished
   files to:

   ```text
   YYYY-MM-DD - Episode Title.ext
   ```

Supported source files include `.mp3`, `.m4a`, `.aac`, `.wav`, `.flac`, `.ogg`,
`.opus`, `.mp4`, `.mov`, `.mkv`, `.webm`, and `.m4v`.

Draft or generic filenames are ignored. Renames are detected by Drive file ID.
After a successful sync, the creator may delete the source file from Drive
because R2 is the durable media copy.

Before approving a Drive request, run the manual GitHub workflow:

```text
Actions -> Check Drive Folder -> Run workflow
```

Paste the Drive folder URL. The workflow verifies service-account access and
prints which files are publishable versus skipped.

To approve a Drive or YouTube issue, add this label after review:

```text
approved
```

## Local usage

```bash
python -m pip install -r requirements.txt
python -m podcast_feeds.build --show wechter
python -m podcast_feeds.validate --show wechter
```

Network sync requires R2 credentials:

```bash
python -m podcast_feeds.sync --show wechter
```
