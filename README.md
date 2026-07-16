# youtube-podcast-feeds

Config-driven podcast RSS generator for YouTube channels, YouTube playlists,
Google Drive folders, existing podcast feeds, and combined multi-source shows.

## Feed URLs

- Website: `https://torah-pod.pages.dev/`
- Wechter: `https://torah-pod.pages.dev/wechter/feed.xml`
- Nachmanson: `https://torah-pod.pages.dev/nachmanson/feed.xml`
- Onboarding: `https://torah-pod.pages.dev/onboard/`

## How it works

1. Show configs live under `shows/<slug>/config.yml`.
   A show may have one source or multiple sources.
2. `python -m podcast_feeds.sync --show <slug>` discovers new source items,
   normalizes them to podcast MP3 where needed, uploads audio to Cloudflare R2,
   and updates `shows/<slug>/episodes.json` for hosted Torah Pod feeds.
   Linked existing feeds skip metadata sync.
3. `python -m podcast_feeds.build --show <slug>` writes static RSS and artwork
   files under `public/<slug>/` for hosted feeds. Linked existing feeds keep
   only the show page/artwork and point RSS links to the upstream feed.
4. The build also generates the Torah Pod static website under `public/`,
   including the podcast catalog and show pages.
5. GitHub Pages serves `public/` as the published podcast site.

## Required secrets

- `YOUTUBE_COOKIES`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY`
- `R2_SECRET_KEY`
- `R2_BUCKET`
- `R2_PUBLIC_URL`
- `GMAIL_USER` and `GMAIL_APP_PASSWORD` are optional for email notification
  delivery. When mail is enabled, `GMAIL_USER` must be
  `torahyoupod@gmail.com`; workflows intentionally skip mail if another sender
  account is configured.
- `PODCAST_NOTIFY_EMAIL` is optional for failure, onboarding-request,
  added-podcast, new-episode, and weekly status email notifications.

`YOUTUBE_COOKIES` is required for YouTube shows. `GOOGLE_SERVICE_ACCOUNT_JSON`
is required for Drive shows.

## Google Drive Shows

Drive folders are treated as staging inboxes. The published podcast uses R2
copies, not Drive URLs.

New podcasts can be requested through the public onboarding page:

```text
https://torah-pod.pages.dev/onboard/
```

It supports one source per request: YouTube URL, Google Drive folder, or
existing podcast feed. A YouTube URL may be a channel or playlist; playlist
URLs are detected automatically. The page submits to a Cloudflare Worker that
creates a GitHub issue for maintainer approval. The page defaults to Hebrew and
includes an English toggle. Podcast name is optional for YouTube/Drive; if it
is blank, the speaker/rabbi name is used. Existing feed requests only ask for
the feed URL; approval reads the feed title, author, description, website link,
artwork, episodes, and enclosure URLs from the RSS/Atom feed. The short English
URL name is required for YouTube/Drive and generated from feed metadata for
existing-feed requests. To add a source to an existing podcast, submit or edit
the same slug; approval appends only missing sources. Worker setup is
documented in `docs/ONBOARDING_WORKER.md`.

Operator maintenance for sync monitoring, YouTube cookie refreshes, R2
credential rotation, and Drive access checks is documented in
`docs/OPERATIONS.md`.

Android app playback architecture and manual regression checks are documented in
`docs/APP_PLAYBACK_QA.md`.

Android app roadmap and native-shell staging are documented in
`docs/ANDROID_APP_ROADMAP.md`.

Free-tier guardrails for Cloudflare R2, GitHub Actions, Cloudflare Pages,
Workers, Google Drive, and notification dependencies are documented in
`docs/FREE_TIER_STABILITY.md`.

Requests can also be opened directly through GitHub issue forms:

```text
Issues -> New issue
```

Submitted requests are advisory only. A maintainer approves a request by adding
the `approved` label. For Drive requests, run the folder check workflow first.
The approval workflow creates the show config, runs the first sync, deploys the
feed, comments on the issue, removes `needs-approval`, and closes the issue.
New onboarding request issues also send an email from
`Torah Pod <torahyoupod@gmail.com>` when Gmail notification secrets are
configured.

When a new `shows/<slug>/config.yml` file is added on `main`, the
`Notify Added Podcast` workflow opens a GitHub issue assigned to the repository
owner with the show title, slug, and feed URL. If `GMAIL_USER` and
`GMAIL_APP_PASSWORD` are configured, it also sends an optional email to
`PODCAST_NOTIFY_EMAIL` when set, otherwise to `GMAIL_USER`. Notification email
is sent from `Torah Pod <torahyoupod@gmail.com>`.

After a new hosted Torah Pod feed is live, submit it manually to podcast
directories and add the accepted platform URLs under `podcast.platforms`.
Linked existing-feed shows should keep using the upstream feed URL. The
checklist is documented in `docs/PLATFORM_PUBLICATION.md` and is included in
the automatic "Podcast added" issue.

The sync workflow sends an email when it adds newly discovered YouTube or
Google Drive episodes to Torah Pod feeds. A separate push workflow covers
local/manual commits that add episode records. Existing-feed mirror updates are
not included in this notification. Sync failure emails and new-episode emails
are sent from `Torah Pod <torahyoupod@gmail.com>`.

## Donations

The website can show donation options without adding a payment backend. Configure
`donations` in `site_config.yml` with external links or QR images. Leave both
`donation_url` and `donations` blank to hide donation buttons.

The public contact page uses `contact_email` from `site_config.yml`. The form is
static: it opens the visitor's email client with the message prefilled.

Use this source config shape for one source:

```yaml
source:
  type: drive
  folder_id: "<google-drive-folder-id>"
  start_date: "2026-06-11"
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
  - type: existing_feed
    feed_url: "https://example.com/podcast/feed.xml"
    delivery_mode: linked
    start_date: "2026-06-11"
```

Existing feed sources use three delivery modes:

- `linked`: default for public onboarding. Torah Pod lists the podcast and
  scans the upstream RSS/Atom feed during website builds, but does not store an
  `episodes.json` snapshot and does not generate a Torah Pod RSS feed. The RSS
  button points to the upstream feed.
- `remote`: stores upstream episode metadata in `episodes.json` and generates a
  Torah Pod RSS feed that points to the upstream enclosure URLs.
- `mirror`: stores upstream episode metadata, normalizes enclosures to 64 kbps
  mono MP3, uploads a Torah Pod copy to R2, and publishes that copy in the
  generated feed.

New-show onboarding for an existing feed uses upstream podcast metadata as the
default Torah Pod show metadata.

Setup:

1. Create a Google service account.
2. Store its JSON credential as the GitHub Actions secret
   `GOOGLE_SERVICE_ACCOUNT_JSON`.
3. Share the Drive folder with the service account email as Viewer.
4. Ask the creator to upload audio or video files. Finished files publish
   automatically unless the filename starts with a draft prefix.

To set the episode date manually, prefix the filename with:

   ```text
   YYYY-MM-DD - Episode Title.ext
   ```

If that prefix is missing or invalid, Torah Pod uses the Drive file creation
date, falling back to modified date if needed.

Supported source files include `.mp3`, `.m4a`, `.aac`, `.wav`, `.flac`, `.ogg`,
`.opus`, `.mp4`, `.mov`, `.mkv`, `.webm`, and `.m4v`.

Draft filenames are ignored when they start with `draft`, `_draft`, `[draft]`,
`(draft)`, `טיוטה`, or `_טיוטה`. Renames are detected by Drive file ID and
update the episode title/date without creating a duplicate. Renaming a synced
file to a draft prefix, deleting it from the shared folder, or changing it to an
unsupported extension removes the episode from the generated feed on the next
sync. The uploaded R2 media copy is retained unless cleaned up separately.

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
