# youtube-podcast-feeds

Config-driven YouTube channel to podcast RSS generator.

## Feed URLs

- Wechter: `https://shaqo88.github.io/youtube-podcast-feeds/wechter/feed.xml`

## How it works

1. Show configs live under `shows/<slug>/config.yml`.
2. `python -m podcast_feeds.sync --show <slug>` discovers YouTube channel items,
   downloads new audio, converts it to 64 kbps MP3, uploads it to Cloudflare R2,
   and updates `shows/<slug>/episodes.json`.
3. `python -m podcast_feeds.build --show <slug>` writes static RSS and artwork
   files under `public/<slug>/`.
4. GitHub Pages serves `public/` as the published podcast site.

## Required secrets

- `YOUTUBE_COOKIES`
- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY`
- `R2_SECRET_KEY`
- `R2_BUCKET`
- `R2_PUBLIC_URL`
- `GMAIL_USER` and `GMAIL_APP_PASSWORD` are optional for failure mail.

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

