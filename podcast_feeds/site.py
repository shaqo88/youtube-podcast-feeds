from __future__ import annotations

import html
import json
import shutil
from datetime import date
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from .config import PUBLIC_DIR, ROOT, DonationOption, ShowConfig, SiteConfig, load_site_config
from .episodes import available_episodes, load_episodes

BRAND = "Torah Pod"
PLATFORM_LABELS = {
    "apple": "Apple Podcasts",
    "spotify": "Spotify",
    "amazon": "Amazon Music",
    "podcast_index": "Podcast Index",
    "zinc": "Zinc Music",
}
PLATFORM_ORDER = ("apple", "spotify", "amazon", "podcast_index", "zinc")
PLATFORM_ICONS = {
    "apple": """<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 3.5c4.1 0 7.5 3.2 7.5 7.2 0 2.8-1.5 5.2-3.8 6.4l-.8-1.5c1.8-.9 3-2.8 3-4.9 0-3.1-2.6-5.6-5.9-5.6s-5.9 2.5-5.9 5.6c0 2.1 1.2 4 3 4.9l-.8 1.5c-2.3-1.2-3.8-3.6-3.8-6.4 0-4 3.4-7.2 7.5-7.2Zm0 4.4a2.8 2.8 0 1 1 0 5.6 2.8 2.8 0 0 1 0-5.6Zm0 7.2c1 0 1.8.8 1.7 1.8l-.4 3.5c-.1.7-.7 1.2-1.3 1.2s-1.2-.5-1.3-1.2l-.4-3.5c-.1-1 .7-1.8 1.7-1.8Z"/></svg>""",
    "spotify": """<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="9.5"/><path class="platform-icon-cut" d="M7.6 9.2c3.2-.7 6.3-.4 9.2 1.2M8.2 12.3c2.6-.5 5-.2 7.2 1M9 15.1c1.8-.3 3.5-.1 5.1.8"/></svg>""",
    "amazon": '<span class="platform-letter" aria-hidden="true">a</span>',
    "podcast_index": '<span class="platform-letter" aria-hidden="true">PI</span>',
    "zinc": '<span class="platform-letter" aria-hidden="true">Z</span>',
}
HE = {
    "dir": "rtl",
    "lang": "he",
    "home": "בית",
    "shows": "פודקאסטים",
    "latest": "פרקים חדשים",
    "all_shows": "כל הפודקאסטים",
    "listen": "האזנה",
    "feed": "RSS",
    "onboard": "צירוף",
    "status": "סטטוס",
    "contact": "יצירת קשר",
    "contact_title": "יצירת קשר",
    "contact_text": "יש שאלה, הצעה או בקשה לצירוף פודקאסט? אפשר לכתוב ישירות ל-Torah Pod.",
    "contact_name": "שם",
    "contact_email": "אימייל",
    "contact_message": "הודעה",
    "contact_submit": "פתיחת אימייל",
    "donate": "תרומה",
    "donate_title": "תמיכה ב-Torah Pod",
    "donate_text": "אם המיזם מועיל לך, אפשר להשתתף בהחזקת המערכת דרך Bit או PayBox.",
    "episodes": "פרקים",
    "source": "מקור",
    "search": "חיפוש",
    "search_placeholder": "חפשו שיעור או רב",
    "search_podcasts": "חיפוש פודקאסטים",
    "search_podcasts_placeholder": "חפשו לפי שם פודקאסט או רב",
    "filter_hosted_toggle": "רק Torah Pod",
    "search_episodes": "חיפוש פרקים",
    "search_episodes_placeholder": "חפשו לפי שם שיעור או תיאור",
    "show_more": "הצג עוד",
    "empty": "עדיין אין פרקים להצגה.",
    "intro": "שיעורי תורה להאזנה מכל מקום.",
    "hero_kicker": "בית פתוח לפודקאסטים של שיעורי תורה",
    "hero_cta_primary": "האזנה לפרקים",
    "hero_cta_secondary": "צירוף פודקאסט",
    "about": "על Torah Pod",
    "about_text": "מערכת פתוחה לפרסום שיעורי תורה כפודקאסטים מתוך יוטיוב, Google Drive ופידים קיימים, לאחר אישור.",
    "how_it_works": "איך זה עובד",
    "how_it_works_text": "מוסיפים מקור, המערכת מסנכרנת פרקים, והמאזינים מקבלים RSS פתוח שמתאים לאפליקציות הפודקאסטים.",
    "source_mix": "יוטיוב, Drive ופידים קיימים",
    "latest_episode": "פרק אחרון",
    "total_shows": "פודקאסטים",
    "total_episodes": "פרקים",
    "language": "English",
    "updated_at": "עודכן",
    "hosted_by_torahpod": "מאוחסן ב-Torah Pod",
    "external_feed": "פיד חיצוני",
    "mixed_sources": "מקורות משולבים",
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
    "status": "Status",
    "contact": "Contact",
    "contact_title": "Contact",
    "contact_text": "Questions, suggestions, or podcast onboarding requests can be sent directly to Torah Pod.",
    "contact_name": "Name",
    "contact_email": "Email",
    "contact_message": "Message",
    "contact_submit": "Open Email",
    "donate": "Donate",
    "donate_title": "Support Torah Pod",
    "donate_text": "If this project is useful to you, you can help support the platform through Bit or PayBox.",
    "episodes": "Episodes",
    "source": "Source",
    "search": "Search",
    "search_placeholder": "Search lessons or speakers",
    "search_podcasts": "Search Podcasts",
    "search_podcasts_placeholder": "Search by podcast name or rabbi",
    "filter_hosted_toggle": "Torah Pod only",
    "search_episodes": "Search Episodes",
    "search_episodes_placeholder": "Search by lesson title or description",
    "show_more": "Show More",
    "empty": "No episodes yet.",
    "intro": "Torah lessons for listening anywhere.",
    "hero_kicker": "An open home for Torah lesson podcasts",
    "hero_cta_primary": "Listen to Episodes",
    "hero_cta_secondary": "Add a Podcast",
    "about": "About Torah Pod",
    "about_text": "An open system for publishing approved Torah lessons as podcasts from YouTube, Google Drive, and existing feeds.",
    "how_it_works": "How it works",
    "how_it_works_text": "Add a source, let the system sync episodes, and give listeners an open RSS feed for podcast apps.",
    "source_mix": "YouTube, Drive, and existing feeds",
    "latest_episode": "Latest episode",
    "total_shows": "Podcasts",
    "total_episodes": "Episodes",
    "language": "עברית",
    "updated_at": "Updated",
    "hosted_by_torahpod": "Hosted by Torah Pod",
    "external_feed": "External feed",
    "mixed_sources": "Mixed sources",
}


def _escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _search_text(*values: Any) -> str:
    return _escape(" ".join(" ".join(str(value or "").split()) for value in values if value))


def _write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


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


def _utc_midnight(value: date) -> str:
    return (
        datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _episode_status_timestamp(
    shows: list[ShowConfig],
    show_episodes: dict[str, list[dict[str, Any]]],
) -> str:
    latest_published = max(
        (
            str(episode.get("published") or "")
            for episodes in show_episodes.values()
            for episode in episodes
            if episode.get("published")
        ),
        default="",
    )
    if latest_published:
        try:
            return _utc_midnight(datetime.strptime(latest_published, "%Y%m%d").date())
        except ValueError:
            pass

    latest_start = max(
        (source.start_date for show in shows for source in show.sources),
        default=None,
    )
    if latest_start is not None:
        return _utc_midnight(latest_start)
    return "1970-01-01T00:00:00Z"


def _source_identity(source: Any) -> str:
    if source.type == "youtube":
        return source.channel_url or source.channel_id or ""
    if source.type == "youtube_playlist":
        return source.playlist_id or ""
    if source.type == "drive":
        return source.folder_id or ""
    if source.type == "existing_feed":
        return source.feed_url or ""
    return ""


def _source_status(source: Any) -> dict[str, Any]:
    return {
        "type": source.type,
        "identity": _source_identity(source),
        "start_date": source.start_date.isoformat(),
        "delivery_mode": source.delivery_mode if source.type == "existing_feed" else "",
        "scan_limit_per_tab": source.scan_limit_per_tab,
        "max_episodes_per_run": source.max_episodes_per_run,
    }


def _show_hosting_key(show: ShowConfig) -> str:
    hosted = any(
        source.type in ("youtube", "youtube_playlist", "drive")
        or (source.type == "existing_feed" and source.delivery_mode == "mirror")
        for source in show.sources
    )
    external = any(
        source.type == "existing_feed" and source.delivery_mode == "remote"
        for source in show.sources
    )
    if hosted and external:
        return "mixed_sources"
    if hosted:
        return "hosted_by_torahpod"
    return "external_feed"


def _show_hosting_badge(show: ShowConfig) -> str:
    key = _show_hosting_key(show)
    return f'<span class="source-badge source-badge-{key}" data-i18n="{key}">{HE[key]}</span>'


def _platform_label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform.replace("_", " ").title())


def _platform_icon(platform: str) -> str:
    return PLATFORM_ICONS.get(
        platform,
        f'<span class="platform-letter" aria-hidden="true">{_escape(platform[:1].upper())}</span>',
    )


def _platform_buttons(platforms: dict[str, str]) -> str:
    if not platforms:
        return ""
    ordered = sorted(
        platforms.items(),
        key=lambda item: (
            PLATFORM_ORDER.index(item[0]) if item[0] in PLATFORM_ORDER else len(PLATFORM_ORDER),
            item[0],
        ),
    )
    return "".join(
        (
            f'<a class="button platform-button" href="{_escape(url)}" target="_blank" '
            f'rel="noopener noreferrer" aria-label="{_escape(_platform_label(platform))}" '
            f'title="{_escape(_platform_label(platform))}">'
            f'{_platform_icon(platform)}<span class="sr-only">{_escape(_platform_label(platform))}</span></a>'
        )
        for platform, url in ordered
        if url
    )


def _brand_mark() -> str:
    return """<svg class="brand-mark" viewBox="0 0 96 72" aria-hidden="true" focusable="false">
        <path class="mark-parchment" d="M27 15c6 4 12 4 18 0 6 4 12 4 18 0v42c-6-4-12-4-18 0-6-4-12-4-18 0Z"/>
        <path class="mark-roller" d="M18 10v52M78 10v52"/>
        <path class="mark-handle" d="M12 10h12M12 62h12M72 10h12M72 62h12"/>
        <path class="mark-side" d="M24 17c-5 5-5 33 0 38M72 17c5 5 5 33 0 38"/>
        <path class="mark-line" d="M36 27h24M36 36h24M36 45h16"/>
      </svg>"""


def _load_show_episodes(show: ShowConfig) -> list[dict[str, Any]]:
    return sorted(
        available_episodes(load_episodes(show.episodes_path)),
        key=lambda episode: episode.get("published") or "",
        reverse=True,
    )


def _has_donation(site_config: SiteConfig) -> bool:
    return bool(site_config.donations or site_config.donation_url)


def _donation_href(site_config: SiteConfig, relative_prefix: str) -> str:
    if site_config.donations:
        return f"{relative_prefix}donate/"
    return site_config.donation_url


def _donation_link(
    site_config: SiteConfig,
    relative_prefix: str,
    class_name: str = "button donation-button",
) -> str:
    if not _has_donation(site_config):
        return ""
    href = _donation_href(site_config, relative_prefix)
    external_attrs = ' target="_blank" rel="noopener noreferrer"' if not site_config.donations else ""
    return (
        f'<a class="{_escape(class_name)}" href="{_escape(href)}"'
        f'{external_attrs} data-i18n="donate">{HE["donate"]}</a>'
    )


def _page(title: str, body: str, *, site_config: SiteConfig, relative_prefix: str = "") -> str:
    css = f"{relative_prefix}assets/site.css"
    home = f"{relative_prefix}index.html"
    onboard = f"{relative_prefix}onboard/"
    status = f"{relative_prefix}status/"
    contact = f"{relative_prefix}contact/"
    catalog = f"{relative_prefix}catalog.json"
    donation_nav = _donation_link(site_config, relative_prefix)
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
      <a class="brand" href="{home}">{_brand_mark()}<span>{BRAND}</span></a>
      <div class="nav-actions">
        <a href="{home}" data-i18n="home">{HE["home"]}</a>
        <a href="{onboard}" data-i18n="onboard">{HE["onboard"]}</a>
        <a href="{status}" data-i18n="status">{HE["status"]}</a>
        <a href="{contact}" data-i18n="contact">{HE["contact"]}</a>{donation_nav}
        <button class="language-toggle" type="button" data-language-toggle data-i18n="language">{HE["language"]}</button>
      </div>
    </nav>
  </header>
  <main>
{body}
  </main>
  <footer class="footer">
    <div class="section footer-inner">
      <span class="footer-brand">{_brand_mark()}<span>{BRAND}</span></span>
      <a href="{catalog}">catalog.json</a>
      <a href="{onboard}" data-i18n="onboard">{HE["onboard"]}</a>
      <a href="{status}" data-i18n="status">{HE["status"]}</a>
      <a href="{contact}" data-i18n="contact">{HE["contact"]}</a>
    </div>
  </footer>
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
    document.querySelectorAll("[data-list]").forEach((list) => {{
      const pageSize = Number(list.dataset.pageSize || "24");
      let visibleLimit = pageSize;
      const controls = document.querySelector(`[data-list-controls="${{list.id}}"]`);
      const search = document.querySelector(`[data-search-target="${{list.id}}"]`);
      const filterToggle = document.querySelector(`[data-filter-toggle="${{list.id}}"]`);
      const more = document.querySelector(`[data-load-more="${{list.id}}"]`);
      const items = Array.from(list.querySelectorAll("[data-list-item]"));
      if (!items.length) {{
        controls?.setAttribute("hidden", "");
        if (more) {{
          more.hidden = true;
        }}
        return;
      }}
      function matches(item) {{
        const term = search?.value.trim().toLowerCase() || "";
        const hostedOnly = filterToggle?.getAttribute("aria-pressed") === "true";
        const itemFilter = item.dataset.filterValue || "";
        const matchesTerm = !term || item.dataset.searchItem.toLowerCase().includes(term);
        const matchesFilter =
          !hostedOnly ||
          itemFilter === "hosted_by_torahpod" ||
          itemFilter === "mixed_sources";
        return matchesTerm && matchesFilter;
      }}
      function render() {{
        const matched = items.filter(matches);
        items.forEach((item) => {{
          item.hidden = true;
        }});
        matched.slice(0, visibleLimit).forEach((item) => {{
          item.hidden = false;
          item.querySelectorAll("audio[data-audio-src]").forEach((audio) => {{
            if (!audio.src) {{
              audio.src = audio.dataset.audioSrc;
              audio.preload = "metadata";
            }}
          }});
        }});
        if (more) {{
          more.hidden = matched.length <= visibleLimit;
        }}
      }}
      search?.addEventListener("input", () => {{
        visibleLimit = pageSize;
        render();
      }});
      filterToggle?.addEventListener("click", () => {{
        const nextPressed = filterToggle.getAttribute("aria-pressed") !== "true";
        filterToggle.setAttribute("aria-pressed", String(nextPressed));
        visibleLimit = pageSize;
        render();
      }});
      more?.addEventListener("click", () => {{
        visibleLimit += pageSize;
        render();
      }});
      render();
    }});
    document.querySelectorAll("[data-contact-form]").forEach((form) => {{
      form.addEventListener("submit", (event) => {{
        event.preventDefault();
        const data = new FormData(form);
        const email = form.dataset.contactEmail;
        const subject = html.lang === "en" ? "Torah Pod contact" : "פנייה ל-Torah Pod";
        const lines = [
          `Name: ${{data.get("name") || ""}}`,
          `Email: ${{data.get("email") || ""}}`,
          "",
          `${{data.get("message") || ""}}`,
        ];
        window.location.href = `mailto:${{email}}?subject=${{encodeURIComponent(subject)}}&body=${{encodeURIComponent(lines.join("\\n"))}}`;
      }});
    }});
  </script>
</body>
</html>
"""


def _show_card(show: ShowConfig, episodes: list[dict[str, Any]], *, prefix: str = "") -> str:
    artwork = f"{prefix}{show.slug}/assets/podcast-cover.png"
    latest = episodes[0] if episodes else {}
    hosting_key = _show_hosting_key(show)
    source_badge = _show_hosting_badge(show)
    latest_line = ""
    if latest:
        latest_line = (
            f'<p class="latest-line"><span class="pill" data-i18n="latest_episode">'
            f'{HE["latest_episode"]}</span><span>{_escape(latest.get("title"))}</span></p>'
        )
    return f"""
      <article class="show-card" data-list-item data-filter-value="{hosting_key}" data-search-item="{_search_text(show.podcast.title, show.podcast.author)}">
        <a class="show-art" href="{prefix}{show.slug}/index.html">
          <img src="{artwork}" alt="">
        </a>
        <div class="show-card-body">
          <div class="show-card-topline">{source_badge}</div>
          <h3><a href="{prefix}{show.slug}/index.html">{_escape(show.podcast.title)}</a></h3>
          <p>{_escape(show.podcast.author)}</p>
          <p class="muted episode-count">{len(episodes)} <span data-i18n="episodes">{HE["episodes"]}</span></p>{latest_line}
        </div>
      </article>
"""


def _episode_item(episode: dict[str, Any]) -> str:
    duration = _duration(episode.get("duration"))
    meta = " · ".join(part for part in (_date(str(episode.get("published") or "")), duration) if part)
    show_title = episode.get("show_title")
    show_title_line = f'<p class="muted">{_escape(show_title)}</p>' if show_title else ""
    source_link = ""
    if episode.get("source_url"):
        source_link = (
            f'<a href="{_escape(episode.get("source_url"))}" target="_blank" '
            f'rel="noopener noreferrer" data-i18n="source">{HE["source"]}</a>'
        )
    return f"""
      <article class="episode" data-list-item data-search-item="{_search_text(episode.get("title"), episode.get("description"), show_title, episode.get("show_author"))}">
        <div class="episode-head">
          <div>
            <h3>{_escape(episode.get("title"))}</h3>{show_title_line}
          </div>
          <p class="episode-meta">{_escape(meta)}</p>
        </div>
        <audio controls preload="none" data-audio-src="{_escape(episode.get("url"))}"></audio>
        <div class="episode-links">{source_link}</div>
      </article>
"""


def _write_css() -> None:
    assets = PUBLIC_DIR / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    _write_text(
        assets / "site.css",
        """@import url("https://fonts.googleapis.com/css2?family=Assistant:wght@400;600;700;800&family=Heebo:wght@500;700;800;900&display=swap");

* {
  box-sizing: border-box;
}

:root {
  color-scheme: light;
  --bg: #f7efdf;
  --bg-deep: #ead7b7;
  --panel: rgba(255, 252, 244, 0.94);
  --panel-strong: #fffaf0;
  --text: #17213b;
  --muted: #6c604e;
  --line: rgba(92, 68, 36, 0.18);
  --accent: #0f766e;
  --accent-dark: #0f4f4b;
  --accent-soft: #e4f3ed;
  --royal: #12284d;
  --royal-soft: #e7edf7;
  --gold: #c78a2f;
  --gold-soft: #f6e4bd;
  --ink: #261a10;
  --danger: #b42318;
  --focus: rgba(199, 138, 47, 0.3);
  --shadow: 0 22px 60px rgba(54, 38, 20, 0.14);
  --shadow-soft: 0 12px 34px rgba(54, 38, 20, 0.1);
  --radius-lg: 24px;
  --radius-md: 16px;
  --radius-sm: 12px;
}

body {
  margin: 0;
  background:
    radial-gradient(circle at 8% 4%, rgba(199, 138, 47, 0.22), transparent 26rem),
    radial-gradient(circle at 88% 8%, rgba(15, 118, 110, 0.15), transparent 24rem),
    linear-gradient(145deg, #fff8eb 0%, var(--bg) 42%, #f0dfc2 100%);
  color: var(--text);
  font-family: "Assistant", Arial, sans-serif;
  font-size: 16px;
  line-height: 1.5;
}

body::before {
  position: fixed;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  content: "";
  background-image:
    linear-gradient(rgba(97, 72, 39, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(97, 72, 39, 0.035) 1px, transparent 1px);
  background-size: 34px 34px;
  mask-image: linear-gradient(to bottom, #000, transparent 72%);
}

a {
  color: inherit;
}

.site-header {
  position: sticky;
  top: 0;
  z-index: 5;
  border-bottom: 1px solid var(--line);
  background: rgba(255, 248, 235, 0.88);
  backdrop-filter: blur(18px);
  box-shadow: 0 10px 30px rgba(38, 26, 16, 0.06);
}

.nav,
.section {
  width: min(1180px, calc(100% - 32px));
  margin: 0 auto;
}

.section > h1 {
  max-width: 760px;
  margin: 0 0 12px;
  font-family: "Heebo", Arial, sans-serif;
  font-size: clamp(38px, 7vw, 68px);
  line-height: 0.98;
  letter-spacing: -0.035em;
  color: var(--royal);
}

.section > .muted {
  max-width: 720px;
  font-size: clamp(17px, 2vw, 21px);
}

.nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 74px;
  gap: 16px;
}

.brand,
.footer-brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--accent-dark);
  font-family: "Heebo", Arial, sans-serif;
  font-size: 27px;
  font-weight: 800;
  letter-spacing: -0.02em;
  text-decoration: none;
}

.brand-mark {
  width: 42px;
  height: 42px;
  color: var(--royal);
  flex: 0 0 auto;
  filter: drop-shadow(0 8px 10px rgba(38, 26, 16, 0.12));
}

.mark-parchment {
  fill: var(--gold-soft);
  stroke: var(--gold);
  stroke-width: 2.5;
}

.mark-roller,
.mark-handle,
.mark-side,
.mark-line {
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.mark-roller {
  stroke-width: 5;
}

.mark-handle {
  stroke-width: 3;
}

.mark-side,
.mark-line {
  stroke-width: 2.5;
}

.nav-actions {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
}

.nav-actions a,
.language-toggle,
.button {
  min-height: 40px;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 9px 15px;
  background: rgba(255, 252, 244, 0.82);
  color: var(--text);
  font: inherit;
  font-weight: 700;
  text-decoration: none;
  cursor: pointer;
  transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease, background 160ms ease;
}

.nav-actions a:hover,
.language-toggle:hover,
.button:hover {
  transform: translateY(-1px);
  border-color: rgba(199, 138, 47, 0.55);
  box-shadow: 0 8px 20px rgba(54, 38, 20, 0.08);
}

.button.primary {
  border-color: var(--royal);
  background: linear-gradient(135deg, var(--royal), #17436e);
  color: #fff;
  box-shadow: 0 14px 28px rgba(18, 40, 77, 0.18);
}

.donation-button {
  border-color: rgba(199, 138, 47, 0.7);
  background: linear-gradient(135deg, #f6e4bd, #fff7df);
  color: var(--ink);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.donation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 18px;
  margin: 24px 0 50px;
}

.donation-card {
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 22px;
  background: var(--panel);
  box-shadow: var(--shadow-soft);
}

.donation-card h2 {
  margin: 0 0 8px;
  color: var(--royal);
  font-family: "Heebo", Arial, sans-serif;
}

.donation-card p {
  margin: 0 0 16px;
  color: var(--muted);
}

.donation-card .button + .donation-qr {
  margin-top: 18px;
}

.contact-card {
  max-width: 760px;
  margin: 24px 0 54px;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: clamp(22px, 4vw, 34px);
  background: var(--panel);
  box-shadow: var(--shadow-soft);
}

.contact-form {
  display: grid;
  gap: 16px;
  margin-top: 22px;
}

.contact-form label {
  display: grid;
  gap: 7px;
  color: var(--ink);
  font-weight: 800;
}

.contact-form input,
.contact-form textarea {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 13px 15px;
  background: rgba(255, 252, 244, 0.9);
  color: var(--text);
  font: inherit;
}

.contact-form textarea {
  min-height: 170px;
  resize: vertical;
}

.donation-qr {
  width: min(100%, 320px);
  border-radius: 20px;
  border: 1px solid var(--line);
  background: #fff;
  display: block;
}

.hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.12fr) minmax(280px, 0.88fr);
  gap: 28px;
  align-items: center;
  padding: 58px 0 34px;
}

.hero::after {
  position: absolute;
  inset-inline: 4%;
  bottom: 2px;
  height: 1px;
  content: "";
  background: linear-gradient(90deg, transparent, rgba(199, 138, 47, 0.65), transparent);
}

.hero-copy {
  max-width: 770px;
}

.kicker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 13px;
  color: var(--accent-dark);
  font-weight: 800;
}

.kicker::before {
  width: 30px;
  height: 2px;
  border-radius: 999px;
  background: var(--gold);
  content: "";
}

.hero h1 {
  max-width: 760px;
  margin: 0 0 12px;
  font-family: "Heebo", Arial, sans-serif;
  font-size: clamp(42px, 8vw, 82px);
  line-height: 0.95;
  letter-spacing: -0.035em;
  color: var(--royal);
}

.hero p {
  max-width: 720px;
  margin: 0;
  color: var(--muted);
  font-size: clamp(18px, 2vw, 22px);
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 24px;
}

.hero-visual {
  position: relative;
  min-height: 300px;
  border: 1px solid rgba(199, 138, 47, 0.28);
  border-radius: 32px;
  background:
    radial-gradient(circle at 30% 18%, rgba(255, 255, 255, 0.9), transparent 9rem),
    linear-gradient(145deg, rgba(255, 252, 244, 0.95), rgba(237, 215, 177, 0.78));
  box-shadow: var(--shadow);
  overflow: hidden;
}

.hero-visual::before,
.hero-visual::after {
  position: absolute;
  content: "";
  border-radius: 999px;
}

.hero-visual::before {
  width: 260px;
  height: 260px;
  inset: 36px auto auto 50%;
  translate: -50% 0;
  background: conic-gradient(from 45deg, rgba(199, 138, 47, 0.18), rgba(15, 118, 110, 0.18), rgba(18, 40, 77, 0.18), rgba(199, 138, 47, 0.18));
}

.hero-visual::after {
  width: 130px;
  height: 130px;
  inset: auto 28px 24px auto;
  background: rgba(15, 118, 110, 0.12);
}

.scroll-card {
  position: absolute;
  inset: 58px 42px auto;
  min-height: 180px;
  border: 1px solid rgba(92, 68, 36, 0.18);
  border-radius: 24px;
  padding: 24px;
  background: rgba(255, 250, 240, 0.92);
  box-shadow: var(--shadow-soft);
}

.scroll-card .brand-mark {
  width: 84px;
  height: 84px;
}

.wave-line {
  position: absolute;
  inset-inline: 26px;
  bottom: 32px;
  height: 54px;
  border-radius: 999px;
  background:
    linear-gradient(90deg, transparent, rgba(18, 40, 77, 0.14), transparent),
    repeating-linear-gradient(90deg, var(--royal) 0 5px, transparent 5px 16px);
  mask-image: linear-gradient(to top, #000 0 48%, transparent 49% 100%);
  opacity: 0.5;
}

.home-hero {
  grid-template-columns: minmax(0, 1fr) minmax(170px, 260px);
  padding-bottom: 20px;
}

.home-visual {
  min-height: 190px;
  display: grid;
  place-items: center;
}

.home-scroll-card {
  position: relative;
  inset: auto;
  min-height: 0;
  padding: 26px;
  border-radius: 28px;
  text-align: center;
}

.home-scroll-card .brand-mark {
  width: 122px;
  height: 122px;
}

.stats {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 22px;
}

.stat {
  min-width: 136px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  padding: 15px;
  background: rgba(255, 252, 244, 0.72);
  box-shadow: 0 10px 24px rgba(54, 38, 20, 0.06);
}

.stat strong {
  display: block;
  color: var(--royal);
  font-size: 31px;
  line-height: 1;
}

.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin: 34px 0 16px;
}

.toolbar h2,
.about-panel h2 {
  margin: 0;
  font-family: "Heebo", Arial, sans-serif;
  font-size: clamp(27px, 4vw, 38px);
  line-height: 1;
  color: var(--royal);
}

.toolbar-controls {
  display: flex;
  align-items: end;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-toggle {
  align-self: end;
}

.filter-toggle[aria-pressed="true"] {
  border-color: var(--royal);
  background: linear-gradient(135deg, var(--royal), #17436e);
  color: #fff;
  box-shadow: 0 14px 28px rgba(18, 40, 77, 0.18);
}

.search-field {
  display: grid;
  gap: 5px;
  width: min(440px, 100%);
}

.search-field label {
  color: var(--muted);
  font-size: 13px;
  font-weight: 800;
}

.search {
  width: min(440px, 100%);
  min-height: 42px;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 10px 16px;
  background: rgba(255, 252, 244, 0.86);
  font: inherit;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
}

.load-more-row {
  display: flex;
  justify-content: center;
  margin: 22px 0 42px;
}

.search:focus,
.language-toggle:focus,
.button:focus {
  border-color: var(--accent);
  outline: 3px solid var(--focus);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(292px, 1fr));
  gap: 18px;
}

.show-card,
.episode,
.show-hero,
.about-panel {
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--panel);
  box-shadow: var(--shadow-soft);
}

.show-card {
  display: grid;
  grid-template-columns: 104px 1fr;
  gap: 16px;
  padding: 16px;
  overflow: hidden;
  position: relative;
}

.show-card::before,
.episode::before {
  position: absolute;
  inset: 0 0 auto;
  height: 4px;
  background: linear-gradient(90deg, var(--gold), var(--accent), var(--royal));
  content: "";
}

.show-art img,
.show-hero img {
  width: 100%;
  aspect-ratio: 1;
  border: 3px solid rgba(255, 252, 244, 0.9);
  border-radius: 18px;
  object-fit: cover;
  box-shadow: 0 14px 24px rgba(38, 26, 16, 0.16);
}

.show-card h3,
.episode h3 {
  margin: 0 0 6px;
  font-size: 20px;
  line-height: 1.25;
}

.show-card h3 a {
  color: var(--royal);
  text-decoration: none;
}

.show-card p,
.episode p {
  margin: 0 0 6px;
}

.show-card-topline,
.show-page-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.source-badge {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  border: 1px solid rgba(18, 40, 77, 0.14);
  border-radius: 999px;
  padding: 4px 10px;
  background: rgba(255, 252, 244, 0.82);
  color: var(--royal);
  font-size: 12px;
  font-weight: 900;
  line-height: 1.1;
}

.source-badge-hosted_by_torahpod {
  border-color: rgba(15, 118, 110, 0.28);
  background: var(--accent-soft);
  color: var(--accent-dark);
}

.source-badge-external_feed {
  border-color: rgba(18, 40, 77, 0.18);
  background: var(--royal-soft);
  color: var(--royal);
}

.source-badge-mixed_sources {
  border-color: rgba(199, 138, 47, 0.32);
  background: var(--gold-soft);
  color: var(--ink);
}

.muted,
.latest-line {
  color: var(--muted);
}

.latest-line {
  display: grid;
  gap: 5px;
  margin-top: 10px;
}

.pill,
.episode-meta {
  display: inline-flex;
  width: fit-content;
  border: 1px solid rgba(199, 138, 47, 0.32);
  border-radius: 999px;
  padding: 4px 9px;
  background: rgba(246, 228, 189, 0.58);
  color: var(--ink);
  font-size: 13px;
  font-weight: 800;
}

.episode-count {
  font-weight: 700;
}

.about-panel {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(220px, 0.8fr);
  gap: 20px;
  margin: 28px 0 10px;
  padding: 24px;
  background:
    linear-gradient(135deg, rgba(228, 243, 237, 0.92), rgba(255, 250, 240, 0.92)),
    var(--accent-soft);
}

.about-panel p {
  margin: 0;
  color: var(--muted);
}

.about-note {
  display: grid;
  gap: 9px;
  align-content: center;
  border-radius: 20px;
  padding: 18px;
  background: rgba(18, 40, 77, 0.08);
  color: var(--royal);
  font-weight: 800;
}

.show-hero {
  display: grid;
  grid-template-columns: 210px 1fr;
  gap: 26px;
  padding: 24px;
  margin: 30px 0 12px;
  overflow: hidden;
  position: relative;
}

.show-hero::before {
  position: absolute;
  inset: 0;
  z-index: -1;
  content: "";
  background:
    radial-gradient(circle at 18% 10%, rgba(199, 138, 47, 0.16), transparent 18rem),
    radial-gradient(circle at 88% 88%, rgba(15, 118, 110, 0.12), transparent 18rem);
}

.show-hero h1 {
  margin: 0 0 8px;
  font-family: "Heebo", Arial, sans-serif;
  font-size: clamp(34px, 6vw, 58px);
  line-height: 1.1;
  letter-spacing: -0.02em;
  color: var(--royal);
}

.show-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.platform-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  min-width: 42px;
  height: 42px;
  padding: 0;
  color: var(--royal);
  font-weight: 900;
  white-space: nowrap;
}

.platform-button svg {
  width: 22px;
  height: 22px;
  fill: currentColor;
}

.platform-button .platform-icon-cut {
  fill: none;
  stroke: #fff;
  stroke-width: 1.45;
  stroke-linecap: round;
}

.platform-letter {
  font-size: 16px;
  letter-spacing: -0.03em;
}

.episode-list {
  display: grid;
  gap: 14px;
  padding-bottom: 42px;
}

.episode {
  position: relative;
  padding: 18px;
  overflow: hidden;
}

.episode-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

audio {
  width: 100%;
  margin-top: 10px;
  filter: sepia(0.12) saturate(1.1);
}

.episode-links {
  margin-top: 10px;
  color: var(--accent-dark);
  font-size: 15px;
  font-weight: 800;
}

.footer {
  border-top: 1px solid var(--line);
  background: rgba(255, 248, 235, 0.85);
}

.footer-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 64px;
  gap: 12px;
  flex-wrap: wrap;
  color: var(--muted);
}

.footer-brand {
  color: var(--royal);
  font-size: 22px;
}

.footer-brand .brand-mark {
  width: 34px;
  height: 34px;
}

.footer a {
  color: var(--accent-dark);
  text-decoration: none;
  font-weight: 800;
}

.status-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--panel);
  overflow: hidden;
  box-shadow: var(--shadow-soft);
}

.status-table th,
.status-table td {
  border-bottom: 1px solid var(--line);
  padding: 10px;
  text-align: start;
  vertical-align: top;
}

.status-table th {
  background: linear-gradient(135deg, rgba(228, 243, 237, 0.95), rgba(246, 228, 189, 0.72));
  color: var(--royal);
  font-weight: 800;
}

.status-table tr:last-child td {
  border-bottom: 0;
}

.status-sources {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.status-sources span {
  border-radius: 999px;
  padding: 3px 8px;
  background: var(--royal-soft);
  color: var(--royal);
  font-size: 13px;
  font-weight: 800;
}

.status-platforms {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.status-platforms .button {
  min-height: 32px;
  padding: 5px 8px;
  font-size: 14px;
}

[hidden] {
  display: none !important;
}

@media (prefers-reduced-motion: no-preference) {
  .hero-copy,
  .hero-visual,
  .about-panel,
  .show-card,
  .episode,
  .show-hero {
    animation: rise-in 520ms ease both;
  }

  .show-card:nth-child(2n),
  .episode:nth-child(2n) {
    animation-delay: 80ms;
  }

  .show-card:nth-child(3n),
  .episode:nth-child(3n) {
    animation-delay: 140ms;
  }
}

@keyframes rise-in {
  from {
    opacity: 0;
    transform: translateY(14px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 900px) {
  .hero,
  .about-panel {
    grid-template-columns: 1fr;
  }

  .hero-visual {
    min-height: 250px;
  }

  .home-visual {
    min-height: 170px;
  }
}

@media (max-width: 640px) {
  .nav {
    align-items: flex-start;
    flex-direction: column;
    padding: 12px 0;
  }

  .hero {
    grid-template-columns: 1fr;
    padding-top: 30px;
  }

  .toolbar,
  .episode-head {
    align-items: stretch;
    flex-direction: column;
  }

  .toolbar-controls {
    align-items: stretch;
    justify-content: stretch;
  }

  .filter-toggle {
    width: 100%;
    justify-content: center;
  }

  .show-hero {
    grid-template-columns: 1fr;
  }

  .show-hero img {
    max-width: 180px;
  }

  .show-card {
    grid-template-columns: 86px 1fr;
  }

  .stat {
    width: 100%;
  }

  .status-table {
    display: block;
    overflow-x: auto;
  }
}
""",
    )


def _status_rows(status_items: list[dict[str, Any]]) -> str:
    rows = []
    for item in status_items:
        source_lines = "".join(
            f'<span>{_escape(source["type"])}{f" · {_escape(source["delivery_mode"])}" if source.get("delivery_mode") else ""}</span>'
            for source in item["sources"]
        )
        latest = item.get("latest_episode") or {}
        latest_text = ""
        if latest:
            latest_text = f'{_date(str(latest.get("published") or ""))}<br>{_escape(latest.get("title"))}'
        rows.append(
            f"""
          <tr>
            <td><a href="../{_escape(item["slug"])}/index.html">{_escape(item["title"])}</a></td>
            <td>{_escape(item["episode_count"])}</td>
            <td>{latest_text or "-"}</td>
            <td><div class="status-sources">{source_lines}</div></td>
            <td><div class="status-platforms">{_platform_buttons(item["platforms"]) or "-"}</div></td>
            <td><a href="{_escape(item["feed_url"])}">RSS</a></td>
          </tr>"""
        )
    return "\n".join(rows)


def _build_status(
    shows: list[ShowConfig],
    show_episodes: dict[str, list[dict[str, Any]]],
    site_config: SiteConfig,
) -> None:
    generated_at = _episode_status_timestamp(shows, show_episodes)
    items = []
    for show in shows:
        episodes = show_episodes[show.slug]
        latest = episodes[0] if episodes else None
        items.append(
            {
                "slug": show.slug,
                "enabled": show.enabled,
                "title": show.podcast.title,
                "author": show.podcast.author,
                "feed_url": show.podcast.feed_url,
                "website_url": show.podcast.website_url,
                "platforms": show.podcast.platforms,
                "episode_count": len(episodes),
                "latest_episode": (
                    {
                        "title": latest.get("title"),
                        "published": latest.get("published"),
                        "url": latest.get("url"),
                    }
                    if latest
                    else None
                ),
                "sources": [_source_status(source) for source in show.sources],
            }
        )

    status = {
        "generated_at": generated_at,
        "show_count": len(items),
        "episode_count": sum(item["episode_count"] for item in items),
        "shows": items,
    }
    _write_text(
        PUBLIC_DIR / "status.json",
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
    )

    status_dir = PUBLIC_DIR / "status"
    status_dir.mkdir(parents=True, exist_ok=True)
    rows = _status_rows(items)
    body = f"""
    <section class="section hero">
      <div class="hero-copy">
        <p class="kicker" data-i18n="updated_at">{HE["updated_at"]}</p>
        <h1>סטטוס</h1>
        <p>נתונים עד: {_escape(generated_at)}</p>
        <div class="stats">
          <div class="stat"><strong>{len(items)}</strong><span data-i18n="total_shows">{HE["total_shows"]}</span></div>
          <div class="stat"><strong>{status["episode_count"]}</strong><span data-i18n="total_episodes">{HE["total_episodes"]}</span></div>
        </div>
      </div>
      <div class="hero-visual" aria-hidden="true">
        <div class="scroll-card">
          {_brand_mark()}
          <p class="muted" data-i18n="source_mix">{HE["source_mix"]}</p>
        </div>
        <div class="wave-line"></div>
      </div>
    </section>
    <section class="section">
      <table class="status-table">
        <thead>
          <tr>
            <th>פודקאסט</th>
            <th>פרקים</th>
            <th>פרק אחרון</th>
            <th>מקורות</th>
            <th>פלטפורמות</th>
            <th>RSS</th>
          </tr>
        </thead>
        <tbody>
{rows}
        </tbody>
      </table>
    </section>
"""
    _write_text(status_dir / "index.html", _page("Status", body, site_config=site_config, relative_prefix="../"))


def _copy_donation_assets(site_config: SiteConfig) -> None:
    for donation in site_config.donations:
        if not donation.qr_image:
            continue
        source = ROOT / donation.qr_image
        if not source.exists():
            raise FileNotFoundError(f"Missing donation QR image: {source}")
        destination = PUBLIC_DIR / donation.qr_image
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def _donation_option_card(donation: DonationOption) -> str:
    description = f"<p>{_escape(donation.description)}</p>" if donation.description else ""
    button = ""
    if donation.url:
        button = (
            f'<a class="button primary" href="{_escape(donation.url)}" target="_blank" '
            f'rel="noopener noreferrer">{_escape(donation.label)}</a>'
        )
    qr = ""
    if donation.qr_image:
        qr = (
            f'<img class="donation-qr" src="../{_escape(donation.qr_image)}" '
            f'alt="{_escape(donation.label)} QR">'
        )
    return f"""
      <article class="donation-card">
        <h2>{_escape(donation.label)}</h2>
        {description}
        {button}
        {qr}
      </article>
"""


def _build_donation_page(site_config: SiteConfig) -> None:
    if not _has_donation(site_config):
        return
    donate_dir = PUBLIC_DIR / "donate"
    donate_dir.mkdir(parents=True, exist_ok=True)
    if site_config.donations:
        cards = "\n".join(_donation_option_card(donation) for donation in site_config.donations)
    else:
        cards = (
            f'<article class="donation-card"><h2>{HE["donate"]}</h2>'
            f'<a class="button primary" href="{_escape(site_config.donation_url)}" target="_blank" '
            f'rel="noopener noreferrer" data-i18n="donate">{HE["donate"]}</a></article>'
        )
    body = f"""
    <section class="section">
      <p class="kicker" data-i18n="donate">{HE["donate"]}</p>
      <h1 data-i18n="donate_title">{HE["donate_title"]}</h1>
      <p class="muted" data-i18n="donate_text">{HE["donate_text"]}</p>
    </section>
    <section class="section">
      <div class="donation-grid">
{cards}
      </div>
    </section>
"""
    _write_text(donate_dir / "index.html", _page("Donate", body, site_config=site_config, relative_prefix="../"))


def _build_contact_page(site_config: SiteConfig) -> None:
    if not site_config.contact_email:
        return
    contact_dir = PUBLIC_DIR / "contact"
    contact_dir.mkdir(parents=True, exist_ok=True)
    email = _escape(site_config.contact_email)
    body = f"""
    <section class="section">
      <p class="kicker" data-i18n="contact">{HE["contact"]}</p>
      <h1 data-i18n="contact_title">{HE["contact_title"]}</h1>
      <p class="muted" data-i18n="contact_text">{HE["contact_text"]}</p>
      <p><a class="button primary" href="mailto:{email}">{email}</a></p>
      <article class="contact-card">
        <form class="contact-form" data-contact-form data-contact-email="{email}">
          <label>
            <span data-i18n="contact_name">{HE["contact_name"]}</span>
            <input name="name" autocomplete="name">
          </label>
          <label>
            <span data-i18n="contact_email">{HE["contact_email"]}</span>
            <input name="email" type="email" autocomplete="email">
          </label>
          <label>
            <span data-i18n="contact_message">{HE["contact_message"]}</span>
            <textarea name="message" required></textarea>
          </label>
          <button class="button primary" type="submit" data-i18n="contact_submit">{HE["contact_submit"]}</button>
        </form>
      </article>
    </section>
"""
    _write_text(contact_dir / "index.html", _page("Contact", body, site_config=site_config, relative_prefix="../"))


def build_site(shows: list[ShowConfig]) -> None:
    site_config = load_site_config()
    _write_css()
    _copy_donation_assets(site_config)
    show_episodes = {show.slug: _load_show_episodes(show) for show in shows}
    shows = sorted(
        shows,
        key=lambda show: show_episodes[show.slug][0].get("published", "") if show_episodes[show.slug] else "",
        reverse=True,
    )
    all_episodes = sorted(
        (
            {**episode, "show_slug": show.slug, "show_title": show.podcast.title, "show_author": show.podcast.author}
            for show in shows
            for episode in show_episodes[show.slug]
        ),
        key=lambda episode: episode.get("published") or "",
        reverse=True,
    )

    cards = "\n".join(_show_card(show, show_episodes[show.slug]) for show in shows)
    latest = "\n".join(_episode_item(episode) for episode in all_episodes[:12])
    total_episodes = sum(len(episodes) for episodes in show_episodes.values())
    index_body = f"""
    <section class="section hero home-hero">
      <div class="hero-copy">
        <p class="kicker" data-i18n="hero_kicker">{HE["hero_kicker"]}</p>
        <h1>{BRAND}</h1>
        <p data-i18n="intro">{HE["intro"]}</p>
        <div class="hero-actions">
          <a class="button primary" href="#podcasts" data-i18n="all_shows">{HE["all_shows"]}</a>
          <a class="button" href="onboard/" data-i18n="hero_cta_secondary">{HE["hero_cta_secondary"]}</a>
        </div>
      </div>
      <div class="hero-visual home-visual" aria-hidden="true">
        <div class="scroll-card home-scroll-card">
          {_brand_mark()}
        </div>
      </div>
    </section>
    <section class="section" id="podcasts">
      <div class="toolbar">
        <h2 data-i18n="all_shows">{HE["all_shows"]}</h2>
        <div class="toolbar-controls" data-list-controls="podcast-list">
          <button class="button filter-toggle" type="button" data-filter-toggle="podcast-list" aria-pressed="false" data-i18n="filter_hosted_toggle">{HE["filter_hosted_toggle"]}</button>
          <div class="search-field">
            <label for="podcast-search" data-i18n="search_podcasts">{HE["search_podcasts"]}</label>
            <input id="podcast-search" class="search" type="search" data-search-target="podcast-list" data-i18n-placeholder="search_podcasts_placeholder" placeholder="{_escape(HE['search_podcasts_placeholder'])}">
          </div>
        </div>
      </div>
      <div id="podcast-list" class="grid" data-list data-page-size="12">
{cards}
      </div>
      <div class="load-more-row">
        <button class="button" type="button" data-load-more="podcast-list" data-i18n="show_more">{HE["show_more"]}</button>
      </div>
    </section>
    <section class="section" id="latest">
      <div class="toolbar">
        <h2 data-i18n="latest">{HE["latest"]}</h2>
        <div class="search-field" data-list-controls="latest-episode-list">
          <label for="latest-episode-search" data-i18n="search_episodes">{HE["search_episodes"]}</label>
          <input id="latest-episode-search" class="search" type="search" data-search-target="latest-episode-list" data-i18n-placeholder="search_episodes_placeholder" placeholder="{_escape(HE['search_episodes_placeholder'])}">
        </div>
      </div>
      <div id="latest-episode-list" class="episode-list" data-list data-page-size="12">
{latest or f'<p class="muted" data-i18n="empty">{HE["empty"]}</p>'}
      </div>
      <div class="load-more-row">
        <button class="button" type="button" data-load-more="latest-episode-list" data-i18n="show_more">{HE["show_more"]}</button>
      </div>
    </section>
    <section class="section">
      <div class="about-panel">
        <div>
          <h2 data-i18n="about">{HE["about"]}</h2>
          <p data-i18n="about_text">{HE["about_text"]}</p>
        </div>
        <div class="about-note">
          <span data-i18n="how_it_works">{HE["how_it_works"]}</span>
          <p data-i18n="how_it_works_text">{HE["how_it_works_text"]}</p>
          <div class="stats">
            <div class="stat"><strong>{len(shows)}</strong><span data-i18n="total_shows">{HE["total_shows"]}</span></div>
            <div class="stat"><strong>{total_episodes}</strong><span data-i18n="total_episodes">{HE["total_episodes"]}</span></div>
          </div>
        </div>
      </div>
    </section>
"""
    _write_text(PUBLIC_DIR / "index.html", _page("Home", index_body, site_config=site_config))

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
                "platforms": show.podcast.platforms,
                "episode_count": len(episodes),
            }
        )
        platform_buttons = _platform_buttons(show.podcast.platforms)
        if platform_buttons:
            platform_buttons = f"\n            {platform_buttons}"
        source_badge = _show_hosting_badge(show)
        episode_items = "\n".join(_episode_item({**episode, "show_author": show.podcast.author}) for episode in episodes)
        body = f"""
    <section class="section">
      <article class="show-hero">
        <img src="assets/podcast-cover.png" alt="">
        <div>
          <div class="show-page-meta">{source_badge}</div>
          <h1>{_escape(show.podcast.title)}</h1>
          <p>{_escape(show.podcast.author)}</p>
          <p class="muted">{_escape(show.podcast.description)}</p>
          <div class="show-actions">
            <a class="button primary" href="feed.xml" data-i18n="feed">{HE["feed"]}</a>
            <a class="button" href="{_escape(show.podcast.website_url)}" target="_blank" rel="noopener noreferrer" data-i18n="source">{HE["source"]}</a>{platform_buttons}
          </div>
        </div>
      </article>
    </section>
    <section class="section">
      <div class="toolbar">
        <h2 data-i18n="episodes">{HE["episodes"]}</h2>
        <div class="search-field" data-list-controls="episode-list">
          <label for="episode-search" data-i18n="search_episodes">{HE["search_episodes"]}</label>
          <input id="episode-search" class="search" type="search" data-search-target="episode-list" data-i18n-placeholder="search_episodes_placeholder" placeholder="{_escape(HE['search_episodes_placeholder'])}">
        </div>
      </div>
      <div id="episode-list" class="episode-list" data-list data-page-size="25">
{episode_items or f'<p class="muted" data-i18n="empty">{HE["empty"]}</p>'}
      </div>
      <div class="load-more-row">
        <button class="button" type="button" data-load-more="episode-list" data-i18n="show_more">{HE["show_more"]}</button>
      </div>
    </section>
"""
        _write_text(
            show.public_dir / "index.html",
            _page(show.podcast.title, body, site_config=site_config, relative_prefix="../"),
        )

    _write_text(
        PUBLIC_DIR / "catalog.json",
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
    )
    _build_status(shows, show_episodes, site_config)
    _build_donation_page(site_config)
    _build_contact_page(site_config)
    print(f"{PUBLIC_DIR / 'index.html'} written with {len(shows)} show(s)")
