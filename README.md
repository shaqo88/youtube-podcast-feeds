# youtube-podcast-feeds

Torah Pod turns approved YouTube channels, YouTube playlists, Google Drive
folders, and existing podcast feeds into a public podcast catalog. Hosted
sources are normalized and published as RSS feeds; linked feeds remain hosted
by their original provider.

## Public Service

- Website: <https://torah-pod.pages.dev/>
- Onboarding: <https://torah-pod.pages.dev/onboard/>
- Wechter feed: <https://torah-pod.pages.dev/wechter/feed.xml>
- Nachmanson feed: <https://torah-pod.pages.dev/nachmanson/feed.xml>

## Repository Contents

- `podcast_feeds/`: source discovery, synchronization, feed generation, and
  validation.
- `shows/<slug>/config.yml`: public show and source configuration.
- `shows/<slug>/episodes.json`: durable metadata for hosted feeds and selected
  remote/mirrored feeds.
- `public/`: generated website, catalog, artwork, and RSS output.
- `workers/onboarding/`: public intake endpoint used by the onboarding form.
- `android-wrapper/`: the current Android WebView client.
- `.github/workflows/`: synchronization, validation, and deployment automation.

The public repository intentionally does not contain internal roadmaps,
operator runbooks, infrastructure setup details, incident notes, or private
onboarding data. Those are maintained in the private operations repository.
See [Project Governance](docs/PROJECT_GOVERNANCE.md) for the boundary.

## How Publishing Works

1. A show is described by `shows/<slug>/config.yml`.
2. `python -m podcast_feeds.sync --show <slug>` discovers source items,
   normalizes hosted media, uploads it to Cloudflare R2, and updates episode
   metadata. Linked existing feeds do not copy media.
3. `python -m podcast_feeds.build --show <slug>` generates the public catalog,
   show pages, artwork, and hosted RSS feeds.
4. `python -m podcast_feeds.validate --show <slug>` validates generated output.
5. GitHub Actions publishes `public/` to the live site.

## Request a Podcast

Use <https://torah-pod.pages.dev/onboard/>. A request may contain a YouTube
channel or playlist, a Google Drive folder, or an existing RSS/Atom feed.

Requests are reviewed privately. Submission does not guarantee publication.
The requester must confirm that they own the content or are authorized to let
Torah Pod host and distribute it. Do not put contact information, credentials,
private Drive links, or podcast requests in public GitHub issues.

## Source Configuration

A single hosted source uses `source`:

```yaml
source:
  type: drive
  folder_id: "<google-drive-folder-id>"
  start_date: "2026-06-11"
```

A combined show uses `sources`:

```yaml
sources:
  - type: youtube
    channel_url: "https://www.youtube.com/@example"
    channel_id: "UC..."
    tabs: ["videos", "streams"]
    start_date: "2026-06-11"
  - type: drive
    folder_id: "<google-drive-folder-id>"
    start_date: "2026-06-11"
```

Existing feeds support three delivery modes:

- `linked`: list the show and use its upstream RSS and media URLs without
  keeping a local episode snapshot.
- `remote`: generate a Torah Pod RSS feed using upstream enclosure URLs.
- `mirror`: copy and normalize upstream media into Torah Pod storage.

`linked` is the default for public existing-feed onboarding.

## Local Development

```bash
python -m pip install -r requirements.txt
python -m podcast_feeds.build
python -m podcast_feeds.validate
python -m unittest discover -s tests
node --test workers/onboarding/test/submit.test.mjs
```

Network synchronization additionally requires the relevant source and storage
credentials in the local environment.

## Rights and Contributions

Material first published after July 19, 2026 is all rights reserved; see
[LICENSE](LICENSE). Earlier MIT-licensed releases remain available under the
terms that accompanied them. Third-party recordings, artwork, trademarks, and
other supplied content remain the property of their respective owners.

Developer bug reports and suggestions are welcome through public GitHub Issues.
Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing code changes.
