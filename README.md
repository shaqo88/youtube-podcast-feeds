# youtube-podcast-feeds

Config-driven podcast RSS generator for YouTube channels and Google Drive
folders.

## Feed URLs

- Wechter: `https://shaqo88.github.io/youtube-podcast-feeds/wechter/feed.xml`
- Onboarding: `https://shaqo88.github.io/youtube-podcast-feeds/onboard/`

## How it works

1. Show configs live under `shows/<slug>/config.yml`.
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

It supports YouTube channels and Google Drive folders. The page opens an email
request to Torah Pod and includes a prefilled GitHub issue link for maintainer
approval. The page defaults to Hebrew and includes an English toggle. Podcast
name is optional; if it is blank, the speaker/rabbi name is used.

Requests can also be opened directly through GitHub issue forms:

```text
Issues -> New issue
```

Submitted requests are advisory only. A maintainer must approve the request and
add the show config before a feed is created.

Use this source config shape:

```yaml
source:
  type: drive
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
