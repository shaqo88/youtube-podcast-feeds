# Podcast Platform Publication

Torah Pod can generate and host a valid public RSS feed automatically. Public
directory submission is still an account-owner task for the major platforms.
Do not try to automate login flows with browser scripts unless there is a
specific platform API and a stable service account for it.

## When to Run

Run this checklist after a new hosted Torah Pod podcast is approved and the
feed is live at:

```text
https://torah-pod.pages.dev/<slug>/feed.xml
```

Confirm the feed exists before submitting:

```powershell
Invoke-WebRequest -UseBasicParsing -Uri "https://torah-pod.pages.dev/<slug>/feed.xml"
```

For a linked existing-feed show, do not submit a Torah Pod feed URL. Use the
original upstream RSS feed URL from `shows/<slug>/config.yml` instead. Torah Pod
only lists that podcast on the website and redirects old local `/feed.xml` URLs
to the upstream feed on Cloudflare Pages.

## Submit to Platforms

Apple Podcasts:

1. Open `https://podcastsconnect.apple.com`.
2. Sign in with the Torah Pod Apple account.
3. Add a show by RSS feed.
4. Paste `https://torah-pod.pages.dev/<slug>/feed.xml`.
5. Confirm title, artwork, description, category, and owner email.
6. Submit and wait for review/ingestion.
7. Copy the public Apple Podcasts URL after it is available.

Spotify for Creators:

1. Open `https://creators.spotify.com`.
2. Sign in with the Torah Pod Spotify account.
3. Add or claim a podcast by RSS feed.
4. Paste `https://torah-pod.pages.dev/<slug>/feed.xml`.
5. Confirm title, artwork, description, and ownership.
6. Submit and wait for ingestion.
7. Copy the public Spotify show URL after it is available.

Amazon Music for Podcasters:

1. Open `https://podcasters.amazon.com`.
2. Sign in with the Torah Pod Amazon account.
3. Add a podcast by RSS feed.
4. Paste `https://torah-pod.pages.dev/<slug>/feed.xml`.
5. Confirm ownership, title, artwork, and description.
6. Submit and wait for validation/import.
7. Copy the public Amazon Music URL after it is available.

Podcast Index:

1. Open `https://podcastindex.org/add`.
2. Paste `https://torah-pod.pages.dev/<slug>/feed.xml`.
3. Submit and complete any email verification.
4. Copy the public Podcast Index URL after it is available.

## Store Platform Links

After a platform publishes the show, add its public URL under
`podcast.platforms` in `shows/<slug>/config.yml`:

```yaml
podcast:
  platforms:
    apple: "https://podcasts.apple.com/..."
    spotify: "https://open.spotify.com/show/..."
    amazon: "https://music.amazon.com/podcasts/..."
    podcast_index: "https://podcastindex.org/podcast/..."
```

Then rebuild and validate:

```powershell
.\.venv\Scripts\python.exe -m podcast_feeds.build --show <slug>
.\.venv\Scripts\python.exe -m podcast_feeds.validate --show <slug>
git add shows\<slug>\config.yml public
git commit -m "Add platform links for <slug>"
git push
```

The site will show the platform buttons after the push deploys.

## Why This Is Manual

- Apple Podcasts requires an Apple Podcasts Connect account and requires the
  RSS feed to meet Apple requirements before submission.
- Spotify notes that podcasts may need separate submission to other platforms,
  and that platforms can take time or manually approve before publication.
- Amazon Music for Podcasters is an authenticated web app.
- Each platform returns its own final public URL only after ingestion, so Torah
  Pod cannot know the correct URL at initial feed generation time.

## Practical Rule

For each new podcast:

1. Publish the Torah Pod feed.
2. Submit the feed to Apple, Spotify, Amazon, and Podcast Index.
3. Wait for each platform URL.
4. Add the URLs to `shows/<slug>/config.yml`.
5. Rebuild, validate, commit, and push.
