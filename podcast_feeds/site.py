from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import PUBLIC_DIR, ShowConfig
from .episodes import available_episodes, load_episodes

BRAND = "Torah Pod"
HE = {
    "dir": "rtl",
    "lang": "he",
    "home": "&#1489;&#1497;&#1514;",
    "shows": "&#1508;&#1493;&#1491;&#1511;&#1488;&#1505;&#1496;&#1497;&#1501;",
    "latest": "&#1508;&#1512;&#1511;&#1497;&#1501; &#1495;&#1491;&#1513;&#1497;&#1501;",
    "all_shows": "&#1499;&#1500; &#1492;&#1508;&#1493;&#1491;&#1511;&#1488;&#1505;&#1496;&#1497;&#1501;",
    "listen": "&#1492;&#1488;&#1494;&#1504;&#1492;",
    "feed": "RSS",
    "onboard": "&#1492;&#1510;&#1496;&#1512;&#1508;&#1493;&#1514;",
    "episodes": "&#1508;&#1512;&#1511;&#1497;&#1501;",
    "source": "&#1502;&#1511;&#1493;&#1512;",
    "search": "&#1495;&#1497;&#1508;&#1493;&#1513;",
    "search_placeholder": "&#1495;&#1508;&#1513;&#1493; &#1513;&#1497;&#1506;&#1493;&#1512; &#1488;&#1493; &#1512;&#1489;",
    "empty": "&#1506;&#1491;&#1497;&#1497;&#1503; &#1488;&#1497;&#1503; &#1508;&#1512;&#1511;&#1497;&#1501; &#1500;&#1492;&#1510;&#1490;&#1492;.",
    "intro": "&#1513;&#1497;&#1506;&#1493;&#1512;&#1497; &#1514;&#1493;&#1512;&#1492; &#1500;&#1492;&#1488;&#1494;&#1504;&#1492; &#1502;&#1499;&#1500; &#1502;&#1511;&#1493;&#1501;.",
    "language": "English",
}
EN = {
    "dir": "ltr",
    "lang": "en",
    "home": "Home",
    "shows": "Podcasts",
    "latest": "Latest Episodes",
    "all_shows": "All Podcasts",
    "listen": "Listen",
    "feed": "RSS",
    "onboard": "Onboard",
    "episodes": "Episodes",
    "source": "Source",
    "search": "Search",
    "search_placeholder": "Search lessons or speakers",
    "empty": "No episodes yet.",
    "intro": "Torah lessons for listening anywhere.",
    "language": "&#1506;&#1489;&#1512;&#1497;&#1514;",
}


def _escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _date(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return _escape(value)
    return parsed.strftime("%Y-%m-%d")


def _duration(seconds: int | str | None) -> str:
    try:
        total = int(seconds or 0)
    except (TypeError, ValueError):
        total = 0
    if total <= 0:
        return ""
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _load_show_episodes(show: ShowConfig) -> list[dict[str, Any]]:
    return sorted(
        available_episodes(load_episodes(show.episodes_path)),
        key=lambda episode: episode.get("published") or "",
        reverse=True,
    )


def _page(title: str, body: str, *, relative_prefix: str = "") -> str:
    css = f"{relative_prefix}assets/site.css"
    home = f"{relative_prefix}index.html"
    onboard = f"{relative_prefix}onboard/"
    return f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(title)} | {BRAND}</title>
  <link rel="stylesheet" href="{css}">
</head>
<body>
  <header class="site-header">
    <nav class="nav" aria-label="Primary">
      <a class="brand" href="{home}">{BRAND}</a>
      <div class="nav-actions">
        <a href="{home}" data-i18n="home">{HE["home"]}</a>
        <a href="{onboard}" data-i18n="onboard">{HE["onboard"]}</a>
        <button class="language-toggle" type="button" data-language-toggle>{HE["language"]}</button>
      </div>
    </nav>
  </header>
  <main>
{body}
  </main>
  <script>
    const labels = {json.dumps({"he": HE, "en": EN}, ensure_ascii=False)};
    const html = document.documentElement;
    const toggle = document.querySelector("[data-language-toggle]");
    function setLanguage(lang) {{
      const next = labels[lang] || labels.he;
      html.lang = next.lang;
      html.dir = next.dir;
      document.querySelectorAll("[data-i18n]").forEach((node) => {{
        const value = next[node.dataset.i18n];
        if (value) node.innerHTML = value;
      }});
      document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {{
        const value = next[node.dataset.i18nPlaceholder];
        if (value) node.setAttribute("placeholder", value);
      }});
      localStorage.setItem("torahpod-language", lang);
    }}
    toggle?.addEventListener("click", () => {{
      setLanguage(html.lang === "he" ? "en" : "he");
    }});
    setLanguage(localStorage.getItem("torahpod-language") || "he");
    document.querySelectorAll("[data-search]").forEach((input) => {{
      input.addEventListener("input", () => {{
        const term = input.value.trim().toLowerCase();
        document.querySelectorAll("[data-search-item]").forEach((item) => {{
          item.hidden = term && !item.dataset.searchItem.toLowerCase().includes(term);
        }});
      }});
    }});
  </script>
</body>
</html>
"""


def _show_card(show: ShowConfig, episodes: list[dict[str, Any]], *, prefix: str = "") -> str:
    artwork = f"{prefix}{show.slug}/assets/podcast-cover.png"
    latest = episodes[0] if episodes else {}
    return f"""
      <article class="show-card" data-search-item="{_escape(show.podcast.title)} {_escape(show.podcast.author)}">
        <a class="show-art" href="{prefix}{show.slug}/index.html">
          <img src="{artwork}" alt="">
        </a>
        <div>
          <h3><a href="{prefix}{show.slug}/index.html">{_escape(show.podcast.title)}</a></h3>
          <p>{_escape(show.podcast.author)}</p>
          <p class="muted">{len(episodes)} <span data-i18n="episodes">{HE["episodes"]}</span></p>
          {f'<p class="latest-line">{_escape(latest.get("title"))}</p>' if latest else ''}
        </div>
      </article>
"""


def _episode_item(episode: dict[str, Any]) -> str:
    duration = _duration(episode.get("duration"))
    meta = " · ".join(part for part in (_date(str(episode.get("published") or "")), duration) if part)
    return f"""
      <article class="episode" data-search-item="{_escape(episode.get("title"))} {_escape(episode.get("description"))}">
        <div class="episode-head">
          <h3>{_escape(episode.get("title"))}</h3>
          <p>{_escape(meta)}</p>
        </div>
        <audio controls preload="none" src="{_escape(episode.get("url"))}"></audio>
        <div class="episode-links">
          {f'<a href="{_escape(episode.get("source_url"))}" target="_blank" rel="noopener noreferrer" data-i18n="source">{HE["source"]}</a>' if episode.get("source_url") else ''}
        </div>
      </article>
"""


def _write_css() -> None:
    assets = PUBLIC_DIR / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "site.css").write_text(
        """* {
  box-sizing: border-box;
}

:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --text: #172033;
  --muted: #5e6a7d;
  --line: #d9dee7;
  --accent: #0f766e;
  --accent-dark: #115e59;
  --focus: rgba(15, 118, 110, 0.2);
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: Arial, Helvetica, sans-serif;
  font-size: 16px;
  line-height: 1.5;
}

a {
  color: inherit;
}

.site-header {
  position: sticky;
  top: 0;
  z-index: 5;
  border-bottom: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(10px);
}

.nav,
.section {
  width: min(1120px, calc(100% - 28px));
  margin: 0 auto;
}

.nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 64px;
  gap: 16px;
}

.brand {
  color: var(--accent-dark);
  font-size: 24px;
  font-weight: 800;
  text-decoration: none;
}

.nav-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.nav-actions a,
.language-toggle,
.button {
  min-height: 38px;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 8px 12px;
  background: #fff;
  color: var(--text);
  font: inherit;
  text-decoration: none;
  cursor: pointer;
}

.button.primary {
  border-color: var(--accent);
  background: var(--accent);
  color: #fff;
}

.hero {
  padding: 42px 0 24px;
}

.hero h1 {
  max-width: 760px;
  margin: 0 0 10px;
  font-size: clamp(34px, 6vw, 58px);
  line-height: 1.08;
  letter-spacing: 0;
}

.hero p {
  max-width: 720px;
  margin: 0;
  color: var(--muted);
  font-size: 19px;
}

.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin: 16px 0;
}

.search {
  width: min(440px, 100%);
  min-height: 42px;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 9px 12px;
  font: inherit;
}

.search:focus,
.language-toggle:focus,
.button:focus {
  border-color: var(--accent);
  outline: 3px solid var(--focus);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
}

.show-card,
.episode,
.show-hero {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}

.show-card {
  display: grid;
  grid-template-columns: 92px 1fr;
  gap: 14px;
  padding: 14px;
}

.show-art img,
.show-hero img {
  width: 100%;
  aspect-ratio: 1;
  border-radius: 6px;
  object-fit: cover;
}

.show-card h3,
.episode h3 {
  margin: 0 0 4px;
  font-size: 18px;
  line-height: 1.25;
}

.show-card p,
.episode p {
  margin: 0 0 6px;
}

.muted,
.latest-line {
  color: var(--muted);
}

.show-hero {
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 22px;
  padding: 18px;
  margin: 24px 0;
}

.show-hero h1 {
  margin: 0 0 8px;
  font-size: clamp(30px, 5vw, 46px);
  line-height: 1.1;
  letter-spacing: 0;
}

.show-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.episode-list {
  display: grid;
  gap: 12px;
  padding-bottom: 42px;
}

.episode {
  padding: 14px;
}

.episode-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

audio {
  width: 100%;
  margin-top: 10px;
}

.episode-links {
  margin-top: 8px;
  color: var(--accent-dark);
  font-size: 14px;
}

[hidden] {
  display: none !important;
}

@media (max-width: 640px) {
  .nav {
    align-items: flex-start;
    flex-direction: column;
    padding: 12px 0;
  }

  .hero {
    padding-top: 30px;
  }

  .toolbar,
  .episode-head {
    align-items: stretch;
    flex-direction: column;
  }

  .show-hero {
    grid-template-columns: 1fr;
  }

  .show-hero img {
    max-width: 180px;
  }
}
""",
        encoding="utf-8",
    )


def build_site(shows: list[ShowConfig]) -> None:
    _write_css()
    show_episodes = {show.slug: _load_show_episodes(show) for show in shows}
    all_episodes = sorted(
        (
            {**episode, "show_slug": show.slug, "show_title": show.podcast.title}
            for show in shows
            for episode in show_episodes[show.slug]
        ),
        key=lambda episode: episode.get("published") or "",
        reverse=True,
    )

    cards = "\n".join(_show_card(show, show_episodes[show.slug]) for show in shows)
    latest = "\n".join(_episode_item(episode) for episode in all_episodes[:12])
    index_body = f"""
    <section class="section hero">
      <h1>{BRAND}</h1>
      <p data-i18n="intro">{HE["intro"]}</p>
    </section>
    <section class="section">
      <div class="toolbar">
        <h2 data-i18n="all_shows">{HE["all_shows"]}</h2>
        <input class="search" type="search" data-search data-i18n-placeholder="search_placeholder" placeholder="&#1495;&#1508;&#1513;&#1493; &#1513;&#1497;&#1506;&#1493;&#1512; &#1488;&#1493; &#1512;&#1489;">
      </div>
      <div class="grid">
{cards}
      </div>
    </section>
    <section class="section">
      <div class="toolbar">
        <h2 data-i18n="latest">{HE["latest"]}</h2>
      </div>
      <div class="episode-list">
{latest or f'<p class="muted" data-i18n="empty">{HE["empty"]}</p>'}
      </div>
    </section>
"""
    (PUBLIC_DIR / "index.html").write_text(_page("Home", index_body), encoding="utf-8")

    catalog = []
    for show in shows:
        episodes = show_episodes[show.slug]
        show.public_dir.mkdir(parents=True, exist_ok=True)
        catalog.append(
            {
                "slug": show.slug,
                "title": show.podcast.title,
                "author": show.podcast.author,
                "description": show.podcast.description,
                "feed_url": show.podcast.feed_url,
                "artwork_url": show.podcast.artwork_url,
                "episode_count": len(episodes),
            }
        )
        episode_items = "\n".join(_episode_item(episode) for episode in episodes)
        body = f"""
    <section class="section">
      <article class="show-hero">
        <img src="assets/podcast-cover.png" alt="">
        <div>
          <h1>{_escape(show.podcast.title)}</h1>
          <p>{_escape(show.podcast.author)}</p>
          <p class="muted">{_escape(show.podcast.description)}</p>
          <div class="show-actions">
            <a class="button primary" href="feed.xml" data-i18n="feed">{HE["feed"]}</a>
            <a class="button" href="{_escape(show.podcast.website_url)}" target="_blank" rel="noopener noreferrer" data-i18n="source">{HE["source"]}</a>
          </div>
        </div>
      </article>
    </section>
    <section class="section">
      <div class="toolbar">
        <h2 data-i18n="episodes">{HE["episodes"]}</h2>
        <input class="search" type="search" data-search data-i18n-placeholder="search_placeholder" placeholder="&#1495;&#1508;&#1513;&#1493; &#1513;&#1497;&#1506;&#1493;&#1512; &#1488;&#1493; &#1512;&#1489;">
      </div>
      <div class="episode-list">
{episode_items or f'<p class="muted" data-i18n="empty">{HE["empty"]}</p>'}
      </div>
    </section>
"""
        (show.public_dir / "index.html").write_text(
            _page(show.podcast.title, body, relative_prefix="../"),
            encoding="utf-8",
        )

    (PUBLIC_DIR / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{PUBLIC_DIR / 'index.html'} written with {len(shows)} show(s)")
