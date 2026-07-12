from __future__ import annotations

import html
import hashlib
import json
import shutil
from datetime import date
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .config import (
    PUBLIC_DIR,
    ROOT,
    DonationOption,
    ShowConfig,
    SiteConfig,
    is_linked_existing_feed_source,
    is_linked_existing_feed_show,
    public_feed_url,
    load_site_config,
)
from .episodes import available_episodes, load_episodes
from .existing_feed import ExistingFeedItem, list_existing_feed_items

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
    "onboard": "צירוף פודקאסט",
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
    "filter_library_toggle": "רק הספרייה שלי",
    "filter_group": "סינון פודקאסטים",
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
    "continue_listening": "המשך האזנה",
    "library": "הספרייה שלי",
    "queue": "תור",
    "follow": "מעקב",
    "following": "במעקב",
    "empty_library": "עוד לא עקבת אחרי פודקאסטים.",
    "browse_podcasts": "מצאו פודקאסטים למעקב",
    "empty_queue": "התור ריק.",
    "add_to_queue": "הוספה לתור",
    "play_next": "נגן הבא",
    "remove_from_queue": "הסרה מהתור",
    "move_up": "למעלה",
    "move_down": "למטה",
    "clear_queue": "ניקוי התור",
    "now_playing": "מתנגן עכשיו",
    "remove_from_library": "הסרה מהספרייה",
    "mark_played": "סמן כנשמע",
    "mark_unplayed": "סמן כלא נשמע",
    "played": "נשמע",
    "player_close": "סגירה",
    "pause": "עצירה",
    "playback_speed": "מהירות",
    "previous_queue": "הקודם בתור",
    "next_queue": "הבא בתור",
    "skip_back": "חזרה 15 שניות",
    "skip_forward": "קדימה 30 שניות",
    "saved_progress": "נשמר",
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
    "onboard": "Add a Podcast",
    "status": "Status",
    "contact": "Contact",
    "contact_title": "Contact",
    "contact_text": "Questions, suggestions, or podcast requests can be sent directly to Torah Pod.",
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
    "filter_library_toggle": "My Library only",
    "filter_group": "Podcast filters",
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
    "continue_listening": "Continue Listening",
    "library": "My Library",
    "queue": "Queue",
    "follow": "Follow",
    "following": "Following",
    "empty_library": "You are not following any podcasts yet.",
    "browse_podcasts": "Find podcasts to follow",
    "empty_queue": "Your queue is empty.",
    "add_to_queue": "Add to Queue",
    "play_next": "Play Next",
    "remove_from_queue": "Remove from Queue",
    "move_up": "Move Up",
    "move_down": "Move Down",
    "clear_queue": "Clear Queue",
    "now_playing": "Now Playing",
    "remove_from_library": "Remove from Library",
    "mark_played": "Mark Played",
    "mark_unplayed": "Mark Unplayed",
    "played": "Played",
    "player_close": "Close",
    "pause": "Pause",
    "playback_speed": "Speed",
    "previous_queue": "Previous in Queue",
    "next_queue": "Next in Queue",
    "skip_back": "Back 15 seconds",
    "skip_forward": "Forward 30 seconds",
    "saved_progress": "Saved",
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


def _episode_identity(episode: dict[str, Any]) -> str:
    show_slug = str(episode.get("show_slug") or "show")
    value = str(episode.get("guid") or episode.get("id") or episode.get("url") or episode.get("title") or "")
    return f"{show_slug}:{value}"


def _episode_dom_id(episode: dict[str, Any]) -> str:
    return "episode-" + hashlib.sha256(_episode_identity(episode).encode("utf-8")).hexdigest()[:16]


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
        source.type == "existing_feed" and source.delivery_mode in ("remote", "linked")
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


def _show_feed_href(show: ShowConfig) -> str:
    feed_url = public_feed_url(show)
    if is_linked_existing_feed_show(show):
        return feed_url
    if feed_url == show.podcast.feed_url:
        return "feed.xml"
    return feed_url


def _show_feed_attrs(show: ShowConfig) -> str:
    return ' target="_blank" rel="noopener noreferrer"' if _show_feed_href(show).startswith("http") else ""


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
    return """<svg class="brand-mark" viewBox="0 0 96 96" aria-hidden="true" focusable="false">
        <path class="mark-book-page" d="M14 23c12-6 25-5 34 2v50c-9-7-22-9-34-3Z"/>
        <path class="mark-book-page" d="M82 23c-12-6-25-5-34 2v50c9-7 22-9 34-3Z"/>
        <path class="mark-book-spine" d="M48 25v50"/>
        <path class="mark-book-line" d="M25 35c5-1 9-1 13 1M25 45c5-1 9-1 13 1M58 36c4-2 9-2 14-1M58 46c4-2 9-2 14-1"/>
      </svg>"""


def _linked_feed_episode(item: ExistingFeedItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "guid": item.guid,
        "source_type": "existing_feed",
        "delivery_mode": "linked",
        "title": item.title,
        "description": item.description,
        "published": item.published,
        "duration": item.duration,
        "url": item.enclosure_url,
        "size": item.enclosure_size,
        "mime_type": item.enclosure_type or "audio/mpeg",
        "source_url": item.source_url,
        "source_enclosure_url": item.enclosure_url,
        "source_enclosure_type": item.enclosure_type,
    }


def _load_show_episodes(show: ShowConfig) -> list[dict[str, Any]]:
    episodes = list(available_episodes(load_episodes(show.episodes_path)))
    for source in show.sources:
        if not is_linked_existing_feed_source(source):
            continue
        if not source.feed_url:
            continue
        try:
            items = list_existing_feed_items(source.feed_url, source.scan_limit_per_tab)
        except Exception as exc:
            print(f"{show.slug}: failed to scan linked feed {source.feed_url}: {exc}")
            continue
        for item in items:
            if item.published and datetime.strptime(item.published, "%Y%m%d").date() < source.start_date:
                continue
            episodes.append(_linked_feed_episode(item))
    return sorted(
        episodes,
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
    app_js = f"{relative_prefix}assets/app.js"
    manifest = f"{relative_prefix}manifest.webmanifest"
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
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#12284d">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="{BRAND}">
  <title>{_escape(title)} | {BRAND}</title>
  <link rel="manifest" href="{manifest}">
  <link rel="apple-touch-icon" href="{relative_prefix}assets/icon-192.png">
  <link rel="stylesheet" href="{css}">
</head>
<body>
  <header class="site-header">
    <nav class="nav" aria-label="Primary">
      <a class="brand" href="{home}">{_brand_mark()}<span>{BRAND}</span></a>
      <div class="nav-actions">
        <a href="{home}" data-i18n="home">{HE["home"]}</a>
        <button class="nav-button" type="button" data-library-open data-i18n="library">{HE["library"]}</button>
        <button class="nav-button" type="button" data-queue-open><span data-i18n="queue">{HE["queue"]}</span> <span class="nav-count" data-queue-count hidden></span></button>
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
  <aside class="app-drawer" data-library-drawer hidden aria-label="{HE["library"]}">
    <div class="drawer-head">
      <h2 data-i18n="library">{HE["library"]}</h2>
      <button class="drawer-close" type="button" data-drawer-close data-i18n-aria="player_close" aria-label="{HE["player_close"]}">×</button>
    </div>
    <div class="drawer-list" data-library-list></div>
    <div class="drawer-empty" data-library-empty>
      <p class="muted" data-i18n="empty_library">{HE["empty_library"]}</p>
      <a class="button" href="{home}#podcasts" data-browse-podcasts data-i18n="browse_podcasts">{HE["browse_podcasts"]}</a>
    </div>
  </aside>
  <aside class="app-drawer" data-queue-drawer hidden aria-label="{HE["queue"]}">
    <div class="drawer-head">
      <h2 data-i18n="queue">{HE["queue"]}</h2>
      <div class="drawer-head-actions">
        <button class="button secondary drawer-clear" type="button" data-queue-clear data-i18n="clear_queue" hidden>{HE["clear_queue"]}</button>
        <button class="drawer-close" type="button" data-drawer-close data-i18n-aria="player_close" aria-label="{HE["player_close"]}">×</button>
      </div>
    </div>
    <div class="drawer-list" data-queue-list></div>
    <p class="muted drawer-empty" data-queue-empty data-i18n="empty_queue">{HE["empty_queue"]}</p>
  </aside>
  <aside class="resume-card" data-resume hidden>
    <div>
      <span class="resume-label" data-i18n="continue_listening">{HE["continue_listening"]}</span>
      <strong data-resume-title></strong>
      <span data-resume-show></span>
    </div>
    <button class="button primary" type="button" data-resume-play data-i18n="listen">{HE["listen"]}</button>
    <button class="resume-close" type="button" data-resume-close data-i18n-aria="player_close" aria-label="{HE["player_close"]}">×</button>
  </aside>
  <section class="app-player" data-player hidden aria-label="Audio player">
    <button class="player-toggle" type="button" data-player-toggle aria-label="{HE["listen"]}">▶</button>
    <div class="player-main">
      <strong data-player-title></strong>
      <span data-player-show></span>
      <input class="player-seek" type="range" min="0" max="1" value="0" step="1" data-player-seek aria-label="Progress">
    </div>
    <span class="player-time" data-player-time>0:00 / 0:00</span>
    <button class="player-queue-nav" type="button" data-player-prev data-i18n-aria="previous_queue" aria-label="{HE["previous_queue"]}">‹</button>
    <button class="player-speed" type="button" data-player-speed data-i18n-aria="playback_speed" aria-label="{HE["playback_speed"]}">1x</button>
    <button class="player-queue-nav" type="button" data-player-next data-i18n-aria="next_queue" aria-label="{HE["next_queue"]}">›</button>
    <button class="player-skip" type="button" data-player-skip="-15" data-i18n-aria="skip_back" aria-label="{HE["skip_back"]}">-15</button>
    <button class="player-skip" type="button" data-player-skip="30" data-i18n-aria="skip_forward" aria-label="{HE["skip_forward"]}">+30</button>
    <button class="player-close" type="button" data-player-close data-i18n-aria="player_close" aria-label="{HE["player_close"]}">×</button>
  </section>
  <script>
    window.TORAH_POD_LABELS = {json.dumps({"he": HE, "en": EN}, ensure_ascii=False)};
    window.TORAH_POD_BASE = "{relative_prefix}";
  </script>
  <script src="{app_js}" defer></script>
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
      <article class="show-card" data-list-item data-show-card data-show-slug="{_escape(show.slug)}" data-show-title="{_escape(show.podcast.title)}" data-show-author="{_escape(show.podcast.author)}" data-show-artwork="{_escape(artwork)}" data-show-url="{_escape(prefix + show.slug + '/index.html')}" data-filter-value="{hosting_key}" data-search-item="{_search_text(show.podcast.title, show.podcast.author)}">
        <a class="show-art" href="{prefix}{show.slug}/index.html">
          <img src="{artwork}" alt="">
        </a>
        <div class="show-card-body">
          <div class="show-card-topline">{source_badge}</div>
          <h3><a href="{prefix}{show.slug}/index.html">{_escape(show.podcast.title)}</a></h3>
          <p>{_escape(show.podcast.author)}</p>
          <p class="muted episode-count">{len(episodes)} <span data-i18n="episodes">{HE["episodes"]}</span></p>{latest_line}
          <button class="button follow-button" type="button" data-follow-show data-i18n="follow">{HE["follow"]}</button>
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
    episode_id = _episode_identity(episode)
    dom_id = _episode_dom_id(episode)
    artwork = episode.get("artwork_url") or ""
    return f"""
      <article id="{dom_id}" class="episode" data-list-item data-episode-id="{_escape(episode_id)}" data-episode-title="{_escape(episode.get("title"))}" data-episode-show="{_escape(show_title or episode.get("show_author") or BRAND)}" data-episode-show-slug="{_escape(episode.get("show_slug"))}" data-episode-artwork="{_escape(artwork)}" data-episode-duration="{_escape(episode.get("duration"))}" data-episode-src="{_escape(episode.get("url"))}" data-search-item="{_search_text(episode.get("title"), episode.get("description"), show_title, episode.get("show_author"))}">
        <div class="episode-head">
          <div>
            <h3>{_escape(episode.get("title"))}</h3>{show_title_line}
          </div>
          <p class="episode-meta">{_escape(meta)}</p>
        </div>
        <audio controls preload="none" data-audio-src="{_escape(episode.get("url"))}"></audio>
        <p class="episode-progress" data-episode-progress hidden></p>
        <div class="episode-actions">
          <button class="button episode-play" type="button" data-episode-play data-i18n="listen">{HE["listen"]}</button>
          <button class="button secondary episode-queue" type="button" data-queue-add data-i18n="add_to_queue">{HE["add_to_queue"]}</button>
          <button class="button secondary episode-queue-next" type="button" data-queue-next data-i18n="play_next">{HE["play_next"]}</button>
          <button class="button secondary episode-played" type="button" data-toggle-played data-i18n="mark_played">{HE["mark_played"]}</button>
          <div class="episode-links">{source_link}</div>
        </div>
      </article>
"""


def _write_app_js() -> None:
    assets = PUBLIC_DIR / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    _write_text(
        assets / "app.js",
        r"""(() => {
  const labels = window.TORAH_POD_LABELS || {};
  const html = document.documentElement;
  const basePath = window.TORAH_POD_BASE || "";
  const progressPrefix = "torahpod-progress:";
  const lastKey = "torahpod-last-episode";
  const followsKey = "torahpod:v1:follows";
  const queueKey = "torahpod:v1:queue";
  const episodeStateKey = "torahpod:v1:episode-state";
  const speedKey = "torahpod:v1:playback-rate";
  const playbackRates = [1, 1.25, 1.5, 1.75, 2];
  const player = document.querySelector("[data-player]");
  const playerToggle = document.querySelector("[data-player-toggle]");
  const playerTitle = document.querySelector("[data-player-title]");
  const playerShow = document.querySelector("[data-player-show]");
  const playerTime = document.querySelector("[data-player-time]");
  const playerSeek = document.querySelector("[data-player-seek]");
  const playerPrev = document.querySelector("[data-player-prev]");
  const playerNext = document.querySelector("[data-player-next]");
  const playerSpeed = document.querySelector("[data-player-speed]");
  const playerClose = document.querySelector("[data-player-close]");
  const resume = document.querySelector("[data-resume]");
  const resumeTitle = document.querySelector("[data-resume-title]");
  const resumeShow = document.querySelector("[data-resume-show]");
  const resumeButton = document.querySelector("[data-resume-play]");
  const resumeClose = document.querySelector("[data-resume-close]");
  const parser = new DOMParser();
  const audioDock = document.createElement("div");
  let activeAudio = null;
  let activeEpisode = null;
  let activeState = null;
  let renderedActiveQueueId = "";
  let closingAudio = null;
  let playerClosed = false;
  let seeking = false;
  let resumeDismissedAt = Number(safeGet("torahpod-resume-dismissed-at") || 0);
  let resumeDismissedId = String(safeGet("torahpod-resume-dismissed-id") || "");
  let resumeShownId = "";
  let resumeVisibleForId = "";

  try {
    resumeShownId = sessionStorage.getItem("torahpod-resume-shown-id") || "";
  } catch {
    resumeShownId = "";
  }

  audioDock.hidden = true;
  audioDock.dataset.audioDock = "";
  document.body.append(audioDock);

  function t(key) {
    const lang = html.lang === "en" ? "en" : "he";
    return (labels[lang] && labels[lang][key]) || (labels.he && labels.he[key]) || key;
  }

  function formatTime(value) {
    const total = Math.max(0, Math.floor(Number(value) || 0));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    if (hours) return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    return `${minutes}:${String(seconds).padStart(2, "0")}`;
  }

  function playbackRate() {
    const saved = Number(safeGet(speedKey) || 1);
    return playbackRates.includes(saved) ? saved : 1;
  }

  function formatRate(rate) {
    return `${Number(rate).toString()}x`;
  }

  function applyPlaybackRate(audio = activeAudio) {
    const rate = playbackRate();
    if (audio) audio.playbackRate = rate;
    if (playerSpeed) {
      const label = `${t("playback_speed")} ${formatRate(rate)}`;
      playerSpeed.textContent = formatRate(rate);
      playerSpeed.setAttribute("aria-label", label);
      playerSpeed.setAttribute("title", label);
    }
  }

  function cyclePlaybackRate() {
    const current = playbackRate();
    const index = playbackRates.indexOf(current);
    const next = playbackRates[(index + 1) % playbackRates.length];
    safeSet(speedKey, next);
    applyPlaybackRate();
  }

  function escapeHtml(value) {
    const node = document.createElement("span");
    node.textContent = String(value || "");
    return node.innerHTML;
  }

  function progressKey(id) {
    return `${progressPrefix}${id}`;
  }

  function safeGet(key) {
    try {
      return JSON.parse(localStorage.getItem(key) || "null");
    } catch {
      return null;
    }
  }

  function safeSet(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Storage can be unavailable in private modes.
    }
  }

  function safeRemove(key) {
    try {
      localStorage.removeItem(key);
    } catch {
      // Storage can be unavailable in private modes.
    }
  }

  function safeArray(key) {
    const value = safeGet(key);
    return Array.isArray(value) ? value : [];
  }

  function safeObject(key) {
    const value = safeGet(key);
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function showState(card) {
    if (!card) return null;
    const slug = card.dataset.showSlug || "";
    if (!slug) return null;
    return {
      slug,
      title: card.dataset.showTitle || slug,
      author: card.dataset.showAuthor || "",
      artwork: card.dataset.showArtwork ? new URL(card.dataset.showArtwork, location.href).href : "",
      url: card.dataset.showUrl ? new URL(card.dataset.showUrl, location.href).href : `${basePath}${slug}/index.html`,
    };
  }

  function episodeState(article) {
    if (!article) return null;
    const artwork = article.dataset.episodeArtwork || "";
    return {
      id: article.dataset.episodeId || "",
      title: article.dataset.episodeTitle || "",
      show: article.dataset.episodeShow || "",
      showSlug: article.dataset.episodeShowSlug || "",
      artwork: artwork ? new URL(artwork, location.href).href : "",
      src: article.dataset.episodeSrc || "",
      duration: Number(article.dataset.episodeDuration || 0),
      href: `${location.href.split("#")[0]}#${article.id}`,
    };
  }

  function followedShows() {
    return safeArray(followsKey).filter((item) => item && item.slug);
  }

  function saveFollowedShows(items) {
    const unique = [];
    const seen = new Set();
    items.forEach((item) => {
      if (!item?.slug || seen.has(item.slug)) return;
      seen.add(item.slug);
      unique.push(item);
    });
    safeSet(followsKey, unique);
    updateFollowButtons();
    renderLibrary();
    document.dispatchEvent(new CustomEvent("torahpod:librarychange"));
  }

  function isFollowing(slug) {
    return followedShows().some((item) => item.slug === slug);
  }

  function toggleFollow(card) {
    const state = showState(card);
    if (!state) return;
    const items = followedShows();
    if (items.some((item) => item.slug === state.slug)) {
      saveFollowedShows(items.filter((item) => item.slug !== state.slug));
    } else {
      saveFollowedShows([...items, state]);
    }
  }

  function updateFollowButtons() {
    document.querySelectorAll("[data-show-card]").forEach((card) => {
      const state = showState(card);
      const button = card.querySelector("[data-follow-show]");
      if (!state || !button) return;
      const following = isFollowing(state.slug);
      button.dataset.following = String(following);
      button.setAttribute("aria-pressed", String(following));
      button.textContent = following ? t("following") : t("follow");
    });
  }

  function queueEntries() {
    return safeArray(queueKey).filter((item) => item && item.id);
  }

  function saveQueue(entries) {
    const unique = [];
    const seen = new Set();
    entries.forEach((item) => {
      if (!item?.id || seen.has(item.id)) return;
      seen.add(item.id);
      unique.push(item);
    });
    safeSet(queueKey, unique);
    updateQueueUi();
  }

  function isQueued(id) {
    return queueEntries().some((item) => item.id === id);
  }

  function toggleQueued(article) {
    const state = episodeState(article);
    if (!state?.id) return;
    const entries = queueEntries();
    if (entries.some((item) => item.id === state.id)) {
      saveQueue(entries.filter((item) => item.id !== state.id));
    } else {
      saveQueue([...entries, state]);
    }
  }

  function promoteQueueEntry(state) {
    if (!state?.id) return;
    const entries = queueEntries().filter((item) => item.id !== state.id);
    saveQueue([state, ...entries]);
  }

  function queueNext(article) {
    const state = episodeState(article);
    if (!state?.id) return;
    const entries = queueEntries().filter((item) => item.id !== state.id);
    const activeId = activeState?.id || "";
    if (activeId && activeId !== state.id) {
      const activeIndex = entries.findIndex((item) => item.id === activeId);
      if (activeIndex >= 0) {
        entries.splice(activeIndex + 1, 0, state);
        saveQueue(entries);
        return;
      }
    }
    saveQueue([state, ...entries]);
  }

  function episodeStateMap() {
    return safeObject(episodeStateKey);
  }

  function isPlayed(article) {
    const state = episodeState(article);
    if (!state?.id) return false;
    const saved = safeGet(progressKey(state.id));
    if (saved?.completed) return true;
    return Boolean(episodeStateMap()[state.id]?.played);
  }

  function setPlayed(article, played) {
    const state = episodeState(article);
    if (!state?.id) return;
    const states = episodeStateMap();
    states[state.id] = { played, updatedAt: Date.now() };
    safeSet(episodeStateKey, states);
    updateEpisodeActions(article);
  }

  function updateEpisodeActions(article) {
    const state = episodeState(article);
    if (!state?.id) return;
    const queueButton = article.querySelector("[data-queue-add]");
    const playedButton = article.querySelector("[data-toggle-played]");
    const queued = isQueued(state.id);
    const played = isPlayed(article);
    article.dataset.played = String(played);
    if (queueButton) {
      queueButton.textContent = queued ? t("remove_from_queue") : t("add_to_queue");
      queueButton.setAttribute("aria-pressed", String(queued));
    }
    if (playedButton) {
      playedButton.textContent = played ? t("mark_unplayed") : t("mark_played");
      playedButton.setAttribute("aria-pressed", String(played));
    }
  }

  function updateAllEpisodeActions() {
    document.querySelectorAll("[data-episode-id]").forEach(updateEpisodeActions);
  }

  function drawerItemImage(src, alt) {
    if (!src) return "";
    return `<img src="${escapeHtml(src)}" alt="${escapeHtml(alt)}">`;
  }

  function renderLibrary() {
    const list = document.querySelector("[data-library-list]");
    const empty = document.querySelector("[data-library-empty]");
    if (!list) return;
    const items = followedShows();
    list.innerHTML = items.map((item) => `
      <article class="drawer-item">
        ${drawerItemImage(item.artwork || "", "")}
        <div>
          <h3><a href="${escapeHtml(item.url)}">${escapeHtml(item.title)}</a></h3>
          <p>${escapeHtml(item.author || "")}</p>
        </div>
        <button class="button secondary" type="button" data-library-remove="${escapeHtml(item.slug)}">${t("remove_from_library")}</button>
      </article>
    `).join("");
    if (empty) empty.hidden = items.length > 0;
  }

  function renderQueue() {
    const list = document.querySelector("[data-queue-list]");
    const empty = document.querySelector("[data-queue-empty]");
    if (!list) return;
    const clear = document.querySelector("[data-queue-clear]");
    const activeId = activeState?.id || "";
    const items = queueEntries();
    list.innerHTML = items.map((item, index) => `
      <article class="drawer-item${item.id === activeId ? " is-current" : ""}">
        ${drawerItemImage(item.artwork || "", "")}
        <div>
          <h3>${escapeHtml(item.title)}${item.id === activeId ? ` <span class="queue-current">${t("now_playing")}</span>` : ""}</h3>
          <p>${escapeHtml(item.show || "")}</p>
        </div>
        <div class="drawer-actions">
          <button class="button primary" type="button" data-queue-play="${escapeHtml(item.id)}">${t("listen")}</button>
          <button class="button secondary" type="button" data-queue-move="${escapeHtml(item.id)}" data-queue-delta="-1" ${index === 0 ? "disabled" : ""}>${t("move_up")}</button>
          <button class="button secondary" type="button" data-queue-move="${escapeHtml(item.id)}" data-queue-delta="1" ${index === items.length - 1 ? "disabled" : ""}>${t("move_down")}</button>
          <button class="button secondary" type="button" data-queue-remove="${escapeHtml(item.id)}">${t("remove_from_queue")}</button>
        </div>
      </article>
    `).join("");
    if (empty) empty.hidden = items.length > 0;
    if (clear) clear.hidden = items.length === 0;
    document.querySelectorAll("[data-queue-count]").forEach((node) => {
      node.textContent = String(items.length);
      node.hidden = items.length === 0;
    });
  }

  function updateQueueUi() {
    renderQueue();
    updateAllEpisodeActions();
    updateQueueNavButtons();
  }

  function updateLibraryAndQueueUi() {
    updateFollowButtons();
    renderLibrary();
    updateQueueUi();
  }

  async function playQueuedEntry(entry) {
    if (!entry?.id) return;
    let article = Array.from(document.querySelectorAll("[data-episode-id]"))
      .find((candidate) => candidate.dataset.episodeId === entry.id);
    if (!article && entry.href) {
      await navigateTo(entry.href);
      article = Array.from(document.querySelectorAll("[data-episode-id]"))
        .find((candidate) => candidate.dataset.episodeId === entry.id);
    }
    if (article) playEpisode(article);
  }

  function removeFromQueue(id) {
    saveQueue(queueEntries().filter((item) => item.id !== id));
  }

  function clearQueue() {
    saveQueue([]);
  }

  function moveQueueItem(id, delta) {
    const entries = queueEntries();
    const index = entries.findIndex((item) => item.id === id);
    const nextIndex = index + delta;
    if (index < 0 || nextIndex < 0 || nextIndex >= entries.length) return;
    const [item] = entries.splice(index, 1);
    entries.splice(nextIndex, 0, item);
    saveQueue(entries);
  }

  function playNextQueuedAfter(currentId) {
    const remaining = queueEntries().filter((item) => item.id !== currentId);
    saveQueue(remaining);
    if (remaining[0]) playQueuedEntry(remaining[0]);
  }

  function updateQueueNavButtons() {
    const entries = queueEntries();
    const activeId = activeState?.id || "";
    const index = entries.findIndex((item) => item.id === activeId);
    if (playerPrev) playerPrev.disabled = index <= 0;
    if (playerNext) playerNext.disabled = index < 0 || index >= entries.length - 1;
  }

  function playAdjacentQueued(delta) {
    const entries = queueEntries();
    const activeId = activeState?.id || "";
    const index = entries.findIndex((item) => item.id === activeId);
    const next = entries[index + delta];
    if (!next) return;
    playQueuedEntry(next);
  }

  function openDrawer(drawer) {
    if (!drawer) return;
    document.querySelectorAll("[data-library-drawer], [data-queue-drawer]").forEach((node) => {
      node.hidden = node !== drawer;
    });
    drawer.hidden = false;
  }

  function closeDrawers() {
    document.querySelectorAll("[data-library-drawer], [data-queue-drawer]").forEach((node) => {
      node.hidden = true;
    });
  }

  function loadAudio(audio) {
    if (!audio.src && audio.dataset.audioSrc) {
      audio.src = audio.dataset.audioSrc;
      audio.preload = "metadata";
    }
    applyPlaybackRate(audio);
  }

  function savedProgress(article) {
    const state = episodeState(article);
    return state?.id ? safeGet(progressKey(state.id)) : null;
  }

  function updateEpisodeProgress(article) {
    const marker = article?.querySelector("[data-episode-progress]");
    const saved = savedProgress(article);
    if (!marker || !saved || saved.position < 10 || (saved.duration && saved.duration - saved.position < 20)) {
      if (marker) marker.hidden = true;
      return;
    }
    marker.textContent = `${t("saved_progress")}: ${formatTime(saved.position)}`;
    marker.hidden = false;
  }

  function updateAllEpisodeProgress() {
    document.querySelectorAll("[data-episode-id]").forEach(updateEpisodeProgress);
  }

  function saveCurrentProgress(audio, article) {
    const state = episodeState(article);
    if (!state?.id || !audio || !Number.isFinite(audio.currentTime)) return null;
    const duration = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : state.duration;
    const payload = {
      ...state,
      position: audio.currentTime,
      duration,
      updatedAt: Date.now(),
    };
    if (duration && duration - payload.position < 20) {
      payload.position = 0;
      payload.completed = true;
    }
    safeSet(progressKey(state.id), payload);
    safeSet(lastKey, payload);
    updateEpisodeProgress(article);
    updateEpisodeActions(article);
    updateResume();
    return payload;
  }

  function rememberCurrentEpisode(audio, article) {
    const state = episodeState(article);
    if (!state?.id) return null;
    const saved = safeGet(progressKey(state.id));
    const duration = Number.isFinite(audio?.duration) && audio.duration > 0
      ? audio.duration
      : Number(article?.dataset.episodeDuration || saved?.duration || 0);
    const position = Number.isFinite(audio?.currentTime)
      ? audio.currentTime
      : Number(saved?.position || 0);
    const payload = {
      ...state,
      position,
      duration,
      completed: false,
      updatedAt: Date.now(),
    };
    safeSet(lastKey, payload);
    resumeDismissedId = "";
    resumeShownId = "";
    resumeVisibleForId = "";
    safeRemove("torahpod-resume-dismissed-id");
    safeRemove("torahpod-resume-dismissed-at");
    try {
      sessionStorage.removeItem("torahpod-resume-shown-id");
    } catch {
      // Ignore unavailable storage.
    }
    updateResume();
    return payload;
  }

  function dismissResumeFor(saved) {
    const id = saved?.id || resumeVisibleForId || resumeShownId;
    if (!id) {
      resumeVisibleForId = "";
      if (resume) resume.hidden = true;
      return;
    }
    resumeDismissedId = id;
    resumeDismissedAt = Number(saved?.updatedAt || Date.now());
    resumeVisibleForId = "";
    resumeShownId = id;
    safeSet("torahpod-resume-dismissed-id", resumeDismissedId);
    safeSet("torahpod-resume-dismissed-at", resumeDismissedAt);
    safeRemove(lastKey);
    try {
      sessionStorage.setItem("torahpod-resume-shown-id", resumeShownId);
    } catch {
      // Ignore unavailable storage.
    }
    if (resume) resume.hidden = true;
  }

  function updateMediaSession(audio, state) {
    if (!("mediaSession" in navigator) || !state) return;
    const artwork = state.artwork
      ? [{ src: state.artwork, sizes: "512x512", type: "image/png" }]
      : [];
    navigator.mediaSession.metadata = new MediaMetadata({
      title: state.title,
      artist: state.show || "Torah Pod",
      album: "Torah Pod",
      artwork,
    });
    navigator.mediaSession.playbackState = audio.paused ? "paused" : "playing";
    const handlers = {
      play: () => audio.play(),
      pause: () => audio.pause(),
      seekbackward: () => {
        audio.currentTime = Math.max(0, audio.currentTime - 15);
      },
      seekforward: () => {
        audio.currentTime = Math.min(audio.duration || audio.currentTime + 30, audio.currentTime + 30);
      },
    };
    Object.entries(handlers).forEach(([name, handler]) => {
      try {
        navigator.mediaSession.setActionHandler(name, handler);
      } catch {
        // Some browsers expose Media Session partially.
      }
    });
    if (navigator.mediaSession.setPositionState && Number.isFinite(audio.duration) && audio.duration > 0) {
      try {
        navigator.mediaSession.setPositionState({
          duration: audio.duration,
          playbackRate: audio.playbackRate || 1,
          position: Math.min(audio.currentTime, audio.duration),
        });
      } catch {
        // Position state is best-effort.
      }
    }
  }

  function setPlayerState(audio, article) {
    if (playerClosed) return;
    if (audio === closingAudio) return;
    activeAudio = audio;
    activeEpisode = article;
    activeState = episodeState(article);
    if (!player || !activeState) return;
    document.body.classList.add("has-player");
    playerTitle.textContent = activeState.title;
    playerShow.textContent = activeState.show;
    player.hidden = false;
    playerToggle.textContent = audio.paused ? "▶" : "Ⅱ";
    playerToggle.setAttribute("aria-label", audio.paused ? t("listen") : t("pause"));
    applyPlaybackRate(audio);
    updatePlayerProgress();
    updateMediaSession(audio, activeState);
    updateQueueNavButtons();
    if (renderedActiveQueueId !== activeState.id) {
      renderedActiveQueueId = activeState.id;
      updateQueueUi();
    }
    updateResume();
  }

  function updatePlayerProgress() {
    if (!player || !activeAudio) return;
    const duration = Number.isFinite(activeAudio.duration) && activeAudio.duration > 0
      ? activeAudio.duration
      : Number(activeEpisode?.dataset.episodeDuration || 0);
    const position = activeAudio.currentTime || 0;
    playerTime.textContent = `${formatTime(position)} / ${formatTime(duration)}`;
    if (playerSeek && !seeking) {
      playerSeek.max = String(Math.max(1, Math.floor(duration || 1)));
      playerSeek.value = String(Math.floor(position));
    }
    if (activeState) updateMediaSession(activeAudio, activeState);
  }

  function dockActiveAudio() {
    if (activeAudio && activeAudio.parentElement !== audioDock) {
      audioDock.append(activeAudio);
    }
  }

  function stopOtherAudio(nextAudio) {
    document.querySelectorAll("audio").forEach((candidate) => {
      if (candidate === nextAudio || candidate.paused) return;
      candidate.pause();
    });
    if (activeAudio && activeAudio !== nextAudio) {
      activeAudio.pause();
      saveCurrentProgress(activeAudio, activeEpisode);
    }
  }

  function restoreProgress(audio, article) {
    if (audio.dataset.progressRestored === "true") return;
    const saved = savedProgress(article);
    const duration = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : Number(article.dataset.episodeDuration || 0);
    if (saved && saved.position > 10 && (!duration || duration - saved.position > 20)) {
      try {
        audio.currentTime = saved.position;
      } catch {
        // Some streams only become seekable after more metadata arrives.
      }
    }
    audio.dataset.progressRestored = "true";
  }

  function playEpisode(article) {
    const audio = article?.querySelector("audio[data-audio-src]");
    if (!audio) return;
    closingAudio = null;
    playerClosed = false;
    loadAudio(audio);
    stopOtherAudio(audio);
    restoreProgress(audio, article);
    rememberCurrentEpisode(audio, article);
    promoteQueueEntry(episodeState(article));
    audio.play().then(() => setPlayerState(audio, article)).catch(() => {});
  }

  function updateResume() {
    if (!resume) return;
    const saved = safeGet(lastKey);
    const valid = saved && saved.position > 10 && (!saved.duration || saved.duration - saved.position > 20);
    const dismissed = saved && resumeDismissedId === saved.id;
    const alreadyShown = saved && resumeShownId === saved.id && resumeVisibleForId !== saved.id;
    const playerActive = Boolean(activeState) || (player && !player.hidden);
    if (!valid || dismissed || alreadyShown || playerActive) {
      resumeVisibleForId = "";
      resume.hidden = true;
      return;
    }
    resumeTitle.textContent = saved.title || "";
    resumeShow.textContent = `${saved.show || ""} · ${formatTime(saved.position)}`;
    resumeVisibleForId = saved.id;
    resumeShownId = saved.id;
    try {
      sessionStorage.setItem("torahpod-resume-shown-id", resumeShownId);
    } catch {
      // Ignore unavailable storage.
    }
    resume.hidden = false;
  }

  function resumeLast() {
    const saved = safeGet(lastKey);
    if (!saved?.id) return;
    const article = Array.from(document.querySelectorAll("[data-episode-id]"))
      .find((candidate) => candidate.dataset.episodeId === saved.id);
    if (article) {
      article.scrollIntoView({ behavior: "smooth", block: "center" });
      playEpisode(article);
    } else if (saved.href) {
      navigateTo(saved.href).then(() => {
        const nextArticle = Array.from(document.querySelectorAll("[data-episode-id]"))
          .find((candidate) => candidate.dataset.episodeId === saved.id);
        if (nextArticle) playEpisode(nextArticle);
      });
    }
  }

  function setupEpisodes() {
    document.querySelectorAll("[data-episode-id]").forEach((article) => {
      const audio = article.querySelector("audio[data-audio-src]");
      const play = article.querySelector("[data-episode-play]");
      const queue = article.querySelector("[data-queue-add]");
      const queueNextButton = article.querySelector("[data-queue-next]");
      const played = article.querySelector("[data-toggle-played]");
      updateEpisodeProgress(article);
      updateEpisodeActions(article);
      play?.addEventListener("click", () => playEpisode(article));
      queue?.addEventListener("click", () => toggleQueued(article));
      queueNextButton?.addEventListener("click", () => queueNext(article));
      played?.addEventListener("click", () => setPlayed(article, !isPlayed(article)));
      audio?.addEventListener("loadedmetadata", () => restoreProgress(audio, article));
      audio?.addEventListener("play", () => {
        closingAudio = null;
        playerClosed = false;
        stopOtherAudio(audio);
        restoreProgress(audio, article);
        rememberCurrentEpisode(audio, article);
        setPlayerState(audio, article);
      });
      audio?.addEventListener("pause", () => {
        if (playerClosed && closingAudio === audio) return;
        saveCurrentProgress(audio, article);
        if (closingAudio === audio) return;
        setPlayerState(audio, article);
      });
      audio?.addEventListener("timeupdate", () => {
        if (playerClosed) return;
        if (closingAudio === audio) return;
        setPlayerState(audio, article);
        if (!audio.dataset.lastSavedAt || Date.now() - Number(audio.dataset.lastSavedAt) > 4000) {
          audio.dataset.lastSavedAt = String(Date.now());
          saveCurrentProgress(audio, article);
        }
      });
      audio?.addEventListener("ended", () => {
        if (playerClosed) return;
        if (closingAudio === audio) return;
        saveCurrentProgress(audio, article);
        setPlayed(article, true);
        updatePlayerProgress();
        playNextQueuedAfter(article.dataset.episodeId || "");
      });
    });
  }

  function setupPlayerControls() {
    const closePlayer = () => {
      let saved = activeState;
      const audio = activeAudio;
      const article = activeEpisode;
      if (player) player.hidden = true;
      playerClosed = true;
      activeAudio = null;
      activeState = null;
      activeEpisode = null;
      renderedActiveQueueId = "";
      document.body.classList.remove("has-player");
      updateQueueUi();
      updateQueueNavButtons();
      if (audio) {
        closingAudio = audio;
        audio.pause();
        saved = saveCurrentProgress(audio, article) || saved;
      }
      dismissResumeFor(saved);
    };

    const closeResume = () => {
      if (resume) resume.hidden = true;
      const saved = safeGet(lastKey);
      dismissResumeFor(saved);
    };

    const bindClosePress = (button, handler) => {
      if (!button) return;
      let lastPressAt = 0;
      const run = (event) => {
        const now = Date.now();
        event.preventDefault();
        event.stopPropagation();
        if (now - lastPressAt < 700) return;
        lastPressAt = now;
        handler();
      };
      ["touchstart", "pointerdown", "mousedown", "click"].forEach((type) => {
        button.addEventListener(type, run, { capture: true, passive: false });
      });
    };

    playerToggle?.addEventListener("click", () => {
      if (!activeAudio) return;
      if (activeAudio.paused) activeAudio.play().catch(() => {});
      else activeAudio.pause();
    });
    playerPrev?.addEventListener("click", () => playAdjacentQueued(-1));
    playerNext?.addEventListener("click", () => playAdjacentQueued(1));
    playerSpeed?.addEventListener("click", cyclePlaybackRate);
    document.querySelectorAll("[data-player-skip]").forEach((button) => {
      button.addEventListener("click", () => {
        if (!activeAudio) return;
        const delta = Number(button.dataset.playerSkip || 0);
        activeAudio.currentTime = Math.max(0, Math.min(activeAudio.duration || activeAudio.currentTime + delta, activeAudio.currentTime + delta));
      });
    });
    playerSeek?.addEventListener("input", () => {
      seeking = true;
      if (activeAudio) activeAudio.currentTime = Number(playerSeek.value || 0);
      seeking = false;
    });
    bindClosePress(playerClose, closePlayer);
    resumeButton?.addEventListener("click", resumeLast);
    bindClosePress(resumeClose, closeResume);
  }

  function setupLists() {
    document.querySelectorAll("[data-list]").forEach((list) => {
      const pageSize = Number(list.dataset.pageSize || "24");
      let visibleLimit = pageSize;
      const controls = document.querySelector(`[data-list-controls="${list.id}"]`);
      const search = document.querySelector(`[data-search-target="${list.id}"]`);
      const filterToggle = document.querySelector(`[data-filter-toggle="${list.id}"]`);
      const libraryToggle = document.querySelector(`[data-library-filter-toggle="${list.id}"]`);
      const more = document.querySelector(`[data-load-more="${list.id}"]`);
      const items = Array.from(list.querySelectorAll("[data-list-item]"));
      if (!items.length) {
        controls?.setAttribute("hidden", "");
        if (more) more.hidden = true;
        return;
      }
      function matches(item) {
        const term = search?.value.trim().toLowerCase() || "";
        const hostedOnly = filterToggle?.getAttribute("aria-pressed") === "true";
        const libraryOnly = libraryToggle?.getAttribute("aria-pressed") === "true";
        const itemFilter = item.dataset.filterValue || "";
        const showSlug = item.dataset.showSlug || item.dataset.episodeShowSlug || "";
        const matchesTerm = !term || item.dataset.searchItem.toLowerCase().includes(term);
        const matchesFilter = !hostedOnly || itemFilter === "hosted_by_torahpod" || itemFilter === "mixed_sources";
        const matchesLibrary = !libraryOnly || isFollowing(showSlug);
        return matchesTerm && matchesFilter && matchesLibrary;
      }
      function render() {
        const matched = items.filter(matches);
        items.forEach((item) => {
          item.hidden = true;
        });
        matched.slice(0, visibleLimit).forEach((item) => {
          item.hidden = false;
          item.querySelectorAll("audio[data-audio-src]").forEach(loadAudio);
        });
        if (more) more.hidden = matched.length <= visibleLimit;
        updateAllEpisodeProgress();
      }
      search?.addEventListener("input", () => {
        visibleLimit = pageSize;
        render();
      });
      filterToggle?.addEventListener("click", () => {
        const nextPressed = filterToggle.getAttribute("aria-pressed") !== "true";
        filterToggle.setAttribute("aria-pressed", String(nextPressed));
        visibleLimit = pageSize;
        render();
      });
      libraryToggle?.addEventListener("click", () => {
        const nextPressed = libraryToggle.getAttribute("aria-pressed") !== "true";
        libraryToggle.setAttribute("aria-pressed", String(nextPressed));
        visibleLimit = pageSize;
        render();
      });
      document.addEventListener("torahpod:librarychange", () => {
        visibleLimit = pageSize;
        render();
      });
      more?.addEventListener("click", () => {
        visibleLimit += pageSize;
        render();
      });
      render();
    });
  }

  function setupLibraryQueueControls() {
    document.addEventListener("click", (event) => {
      const follow = event.target.closest?.("[data-follow-show]");
      if (follow) {
        event.preventDefault();
        toggleFollow(follow.closest("[data-show-card]"));
        return;
      }

      const libraryOpen = event.target.closest?.("[data-library-open]");
      if (libraryOpen) {
        event.preventDefault();
        renderLibrary();
        openDrawer(document.querySelector("[data-library-drawer]"));
        return;
      }

      const browsePodcasts = event.target.closest?.("[data-browse-podcasts]");
      if (browsePodcasts) {
        closeDrawers();
        return;
      }

      const queueOpen = event.target.closest?.("[data-queue-open]");
      if (queueOpen) {
        event.preventDefault();
        renderQueue();
        openDrawer(document.querySelector("[data-queue-drawer]"));
        return;
      }

      const close = event.target.closest?.("[data-drawer-close]");
      if (close) {
        event.preventDefault();
        closeDrawers();
        return;
      }

      const removeLibrary = event.target.closest?.("[data-library-remove]");
      if (removeLibrary) {
        event.preventDefault();
        const slug = removeLibrary.dataset.libraryRemove;
        saveFollowedShows(followedShows().filter((item) => item.slug !== slug));
        return;
      }

      const removeQueue = event.target.closest?.("[data-queue-remove]");
      if (removeQueue) {
        event.preventDefault();
        removeFromQueue(removeQueue.dataset.queueRemove);
        return;
      }

      const moveQueue = event.target.closest?.("[data-queue-move]");
      if (moveQueue) {
        event.preventDefault();
        moveQueueItem(moveQueue.dataset.queueMove, Number(moveQueue.dataset.queueDelta || 0));
        return;
      }

      const clearQueueButton = event.target.closest?.("[data-queue-clear]");
      if (clearQueueButton) {
        event.preventDefault();
        clearQueue();
        return;
      }

      const playQueue = event.target.closest?.("[data-queue-play]");
      if (playQueue) {
        event.preventDefault();
        const entry = queueEntries().find((item) => item.id === playQueue.dataset.queuePlay);
        if (entry) {
          closeDrawers();
          playQueuedEntry(entry);
        }
      }
    });
  }

  function setupLanguage() {
    const toggle = document.querySelector("[data-language-toggle]");
    function setLanguage(lang) {
      const next = labels[lang] || labels.he;
      html.lang = next.lang;
      html.dir = next.dir;
      document.querySelectorAll("[data-i18n]").forEach((node) => {
        const value = next[node.dataset.i18n];
        if (value) node.innerHTML = value;
      });
      document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
        const value = next[node.dataset.i18nPlaceholder];
        if (value) node.setAttribute("placeholder", value);
      });
      document.querySelectorAll("[data-i18n-aria]").forEach((node) => {
        const value = next[node.dataset.i18nAria];
        if (value) node.setAttribute("aria-label", value);
      });
      applyPlaybackRate();
      try {
        localStorage.setItem("torahpod-language", lang);
      } catch {
        // Ignore unavailable storage.
      }
      updateAllEpisodeProgress();
      updateLibraryAndQueueUi();
      updateResume();
    }
    toggle?.addEventListener("click", () => {
      setLanguage(html.lang === "he" ? "en" : "he");
    });
    let stored = "he";
    try {
      stored = localStorage.getItem("torahpod-language") || "he";
    } catch {
      stored = "he";
    }
    setLanguage(stored);
  }

  function setupContactForms() {
    document.querySelectorAll("[data-contact-form]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const data = new FormData(form);
        const email = form.dataset.contactEmail;
        const subject = html.lang === "en" ? "Torah Pod contact" : "פנייה ל-Torah Pod";
        const lines = [
          `Name: ${data.get("name") || ""}`,
          `Email: ${data.get("email") || ""}`,
          "",
          `${data.get("message") || ""}`,
        ];
        window.location.href = `mailto:${email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(lines.join("\n"))}`;
      });
    });
  }

  function normalizePagePath(pathname) {
    let path = pathname.replace(/\/+$/, "");
    path = path.replace(/\/index\.html$/i, "");
    return path || "/";
  }

  function isSamePageUrl(url) {
    return (
      url.origin === location.origin &&
      url.search === location.search &&
      normalizePagePath(url.pathname) === normalizePagePath(location.pathname)
    );
  }

  function shouldHandleNavigation(event, link) {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      link.target ||
      link.hasAttribute("download")
    ) {
      return false;
    }
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin) return false;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return false;
    if (url.pathname.endsWith(".xml") || url.pathname.endsWith(".json") || url.pathname.endsWith(".png")) return false;
    const lastSegment = url.pathname.split("/").filter(Boolean).pop() || "";
    return url.pathname.endsWith("/") || url.pathname.endsWith(".html") || !lastSegment.includes(".");
  }

  async function navigateTo(target, { push = true } = {}) {
    const url = new URL(target, location.href);
    document.body.classList.add("app-loading");
    try {
      const response = await fetch(url.href, { headers: { "X-Torah-Pod-Navigation": "1" } });
      if (!response.ok) throw new Error(`Navigation failed: ${response.status}`);
      const nextDocument = parser.parseFromString(await response.text(), "text/html");
      const nextHeader = nextDocument.querySelector(".site-header");
      const nextMain = nextDocument.querySelector("main");
      const nextFooter = nextDocument.querySelector(".footer");
      if (!nextMain) throw new Error("Navigation response had no main content");

      dockActiveAudio();
      closeDrawers();
      document.title = nextDocument.title || document.title;
      if (nextHeader) document.querySelector(".site-header")?.replaceWith(nextHeader);
      document.querySelector("main")?.replaceWith(nextMain);
      if (nextFooter) document.querySelector(".footer")?.replaceWith(nextFooter);
      if (push) history.pushState({}, "", url.href);
      setupLanguage();
      setupLists();
      setupEpisodes();
      setupContactForms();
      updateLibraryAndQueueUi();
      updateResume();
      const hashTarget = url.hash ? document.querySelector(url.hash) : null;
      if (hashTarget) hashTarget.scrollIntoView({ block: "center" });
      else window.scrollTo(0, 0);
      return true;
    } catch {
      location.href = url.href;
      return false;
    } finally {
      document.body.classList.remove("app-loading");
    }
  }

  function setupAppNavigation() {
    document.addEventListener("click", (event) => {
      const link = event.target.closest?.("a[href]");
      if (!link) return;
      const url = new URL(link.href, location.href);
      if (isSamePageUrl(url) && !url.hash) {
        event.preventDefault();
        window.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }
      if (!shouldHandleNavigation(event, link)) return;
      event.preventDefault();
      navigateTo(link.href);
    });
    window.addEventListener("popstate", () => {
      navigateTo(location.href, { push: false });
    });
  }

  function setupServiceWorker() {
    if (!("serviceWorker" in navigator) || location.protocol === "file:") return;
    window.addEventListener("load", () => {
      navigator.serviceWorker.register(`${basePath}sw.js`).catch(() => {});
    });
  }

  setupLanguage();
  setupLists();
  setupEpisodes();
  setupPlayerControls();
  setupLibraryQueueControls();
  setupContactForms();
  setupAppNavigation();
  setupServiceWorker();
  updateLibraryAndQueueUi();
  updateResume();
})();
""",
    )


def _write_pwa_assets() -> None:
    assets = PUBLIC_DIR / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        icon = Image.new("RGB", (size, size), "#12284d")
        draw = ImageDraw.Draw(icon)
        pad = size // 9
        draw.rounded_rectangle(
            [pad, pad, size - pad, size - pad],
            radius=size // 5,
            fill="#f6e4bd",
        )
        center = size // 2
        top = size * 29 // 100
        bottom = size * 70 // 100
        outer_left = size * 22 // 100
        outer_right = size * 78 // 100
        page_fill = "#fff8eb"
        page_outline = "#12284d"
        line_width = max(5, size // 32)
        left_page = [
            (outer_left, top),
            (center, top + size * 7 // 100),
            (center, bottom),
            (outer_left, bottom - size * 6 // 100),
        ]
        right_page = [
            (outer_right, top),
            (center, top + size * 7 // 100),
            (center, bottom),
            (outer_right, bottom - size * 6 // 100),
        ]
        draw.polygon(left_page, fill=page_fill)
        draw.polygon(right_page, fill=page_fill)
        draw.line(left_page + [left_page[0]], fill=page_outline, width=line_width, joint="curve")
        draw.line(right_page + [right_page[0]], fill=page_outline, width=line_width, joint="curve")
        draw.line((center, top + size * 7 // 100, center, bottom), fill="#c78a2f", width=max(4, size // 38))
        for offset in (0, size * 9 // 100):
            y = top + size * 16 // 100 + offset
            draw.arc(
                [outer_left + size * 7 // 100, y - size * 4 // 100, center - size * 5 // 100, y + size * 5 // 100],
                start=190,
                end=350,
                fill="#0f766e",
                width=max(3, size // 48),
            )
            draw.arc(
                [center + size * 5 // 100, y - size * 4 // 100, outer_right - size * 7 // 100, y + size * 5 // 100],
                start=190,
                end=350,
                fill="#0f766e",
                width=max(3, size // 48),
            )
        icon.save(assets / f"icon-{size}.png")

    _write_text(
        PUBLIC_DIR / "manifest.webmanifest",
        json.dumps(
            {
                "name": BRAND,
                "short_name": BRAND,
                "description": "Torah lessons for listening anywhere.",
                "lang": "he",
                "dir": "rtl",
                "start_url": "./",
                "scope": "./",
                "display": "standalone",
                "background_color": "#f7efdf",
                "theme_color": "#12284d",
                "icons": [
                    {
                        "src": "assets/icon-192.png",
                        "sizes": "192x192",
                        "type": "image/png",
                        "purpose": "any maskable",
                    },
                    {
                        "src": "assets/icon-512.png",
                        "sizes": "512x512",
                        "type": "image/png",
                        "purpose": "any maskable",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    _write_text(
        PUBLIC_DIR / "sw.js",
        """const CACHE_NAME = "torah-pod-shell-v11";
const SHELL_ASSETS = [
  "./",
  "./index.html",
  "./assets/site.css",
  "./assets/app.js",
  "./assets/icon-192.png",
  "./assets/icon-512.png",
  "./manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || request.destination === "audio") return;
  const url = new URL(request.url);
  if (url.origin !== location.origin) return;
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match("./index.html")))
    );
    return;
  }
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    })
  );
});
""",
    )


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
  --safe-top: env(safe-area-inset-top, 0px);
  --safe-bottom: env(safe-area-inset-bottom, 0px);
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
  padding-block: var(--safe-top) calc(116px + var(--safe-bottom));
  background:
    radial-gradient(circle at 8% 4%, rgba(199, 138, 47, 0.22), transparent 26rem),
    radial-gradient(circle at 88% 8%, rgba(15, 118, 110, 0.15), transparent 24rem),
    linear-gradient(145deg, #fff8eb 0%, var(--bg) 42%, #f0dfc2 100%);
  color: var(--text);
  font-family: "Assistant", Arial, sans-serif;
  font-size: 16px;
  line-height: 1.5;
}

html,
body {
  overflow-x: hidden;
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
  top: var(--safe-top);
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
  direction: ltr;
  unicode-bidi: isolate;
}

.brand span,
.footer-brand span {
  direction: ltr;
  unicode-bidi: isolate;
}

.brand-mark {
  width: 42px;
  height: 42px;
  color: var(--royal);
  flex: 0 0 auto;
  filter: drop-shadow(0 8px 10px rgba(38, 26, 16, 0.12));
}

.mark-book-page {
  fill: var(--gold-soft);
  stroke: currentColor;
  stroke-linejoin: round;
  stroke-width: 4.5;
}

.mark-book-spine,
.mark-book-line {
  fill: none;
  stroke: var(--accent);
  stroke-linecap: round;
  stroke-linejoin: round;
}

.mark-book-spine {
  stroke: var(--gold);
  stroke-width: 5;
}

.mark-book-line {
  stroke-width: 3.5;
}

.nav-actions {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
}

.nav-actions a,
.nav-button,
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
.nav-button:hover,
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

.nav-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.nav-count {
  display: inline-grid;
  place-items: center;
  min-width: 22px;
  height: 22px;
  border-radius: 999px;
  padding: 0 7px;
  background: var(--royal);
  color: #fff;
  font-size: 12px;
  font-weight: 900;
}

.follow-button[aria-pressed="true"],
.episode-queue[aria-pressed="true"],
.episode-played[aria-pressed="true"] {
  border-color: rgba(15, 118, 110, 0.45);
  background: var(--accent-soft);
  color: var(--accent-dark);
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

.onboard-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 18px;
  margin: 8px 0 54px;
}

.onboard-option {
  display: grid;
  align-content: start;
  gap: 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 22px;
  background: var(--panel);
  box-shadow: var(--shadow-soft);
}

.onboard-option h2,
.onboard-option p {
  margin: 0;
}

.onboard-option h2 {
  color: var(--royal);
  font-family: "Heebo", Arial, sans-serif;
}

.onboard-option p {
  color: var(--muted);
  font-weight: 700;
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
  direction: ltr;
  unicode-bidi: isolate;
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
  width: min(100%, 230px);
  min-height: 0;
  padding: 16px;
  border-radius: 28px;
}

.home-scroll-card .brand-mark {
  width: 44px;
  height: 44px;
}

.home-app-title {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 12px;
  color: var(--royal);
  font-family: "Heebo", Arial, sans-serif;
  font-size: 18px;
  font-weight: 900;
}

.home-app-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-top: 1px solid var(--line);
  padding: 9px 0;
  color: var(--muted);
  font-weight: 800;
}

.home-app-row strong {
  color: var(--accent-dark);
  font-size: 22px;
}

.home-app-chip {
  display: inline-flex;
  margin-top: 8px;
  border-radius: 999px;
  padding: 6px 10px;
  background: var(--accent-soft);
  color: var(--accent-dark);
  font-size: 13px;
  font-weight: 900;
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
  display: grid;
  grid-template-columns: minmax(0, 440px) max-content;
  align-items: flex-end;
  justify-content: flex-end;
  gap: 12px;
  width: min(620px, 100%);
}

.filter-group {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 3px;
  background: rgba(255, 252, 244, 0.82);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
}

.filter-toggle {
  align-self: center;
  min-height: 38px;
  border: 0;
  padding: 8px 12px;
  background: transparent;
  box-shadow: none;
  margin-bottom: 0;
}

.filter-toggle[aria-pressed="true"] {
  background: linear-gradient(135deg, var(--royal), #17436e);
  color: #fff;
  box-shadow: 0 8px 18px rgba(18, 40, 77, 0.16);
}

.filter-toggle:hover {
  border-color: transparent;
  box-shadow: none;
  transform: none;
}

.filter-toggle[aria-pressed="true"]:hover {
  box-shadow: 0 8px 18px rgba(18, 40, 77, 0.16);
}

.search-field {
  display: grid;
  gap: 5px;
  min-width: 0;
  width: 100%;
}

.search-field label {
  color: var(--muted);
  font-size: 13px;
  font-weight: 800;
}

.search {
  width: 100%;
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
.nav-button:focus,
.language-toggle:focus,
.button:focus,
.player-toggle:focus,
.player-queue-nav:focus,
.player-speed:focus,
.player-skip:focus,
.player-close:focus,
.resume-close:focus,
.drawer-close:focus,
.player-seek:focus {
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

.episode[data-played="true"] {
  opacity: 0.76;
}

.episode[data-played="true"] h3::after {
  display: inline-flex;
  margin-inline-start: 8px;
  border-radius: 999px;
  padding: 2px 7px;
  background: var(--accent-soft);
  color: var(--accent-dark);
  content: "✓";
  font-size: 12px;
  font-weight: 900;
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
  color: var(--accent-dark);
  font-size: 15px;
  font-weight: 800;
}

.episode-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.episode-actions .button {
  min-height: 44px;
  padding: 10px 15px;
}

.episode-play {
  min-height: 48px;
  padding: 11px 18px;
}

.episode-progress {
  width: fit-content;
  margin-top: 10px;
  border: 1px solid rgba(15, 118, 110, 0.24);
  border-radius: 999px;
  padding: 4px 10px;
  background: rgba(228, 243, 237, 0.72);
  color: var(--accent-dark);
  font-size: 13px;
  font-weight: 800;
}

.app-drawer {
  position: fixed;
  z-index: 25;
  inset-block: calc(86px + var(--safe-top)) calc(18px + var(--safe-bottom));
  inset-inline-end: 18px;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  width: min(430px, calc(100vw - 28px));
  border: 1px solid rgba(18, 40, 77, 0.18);
  border-radius: 26px;
  padding: 16px;
  background: rgba(255, 250, 240, 0.98);
  box-shadow: 0 24px 70px rgba(38, 26, 16, 0.24);
  backdrop-filter: blur(18px);
}

body.has-player .app-drawer {
  inset-block-end: calc(104px + var(--safe-bottom));
}

.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-bottom: 1px solid var(--line);
  padding-bottom: 10px;
}

.drawer-head h2 {
  margin: 0;
  color: var(--royal);
  font-family: "Heebo", Arial, sans-serif;
  font-size: 25px;
}

.drawer-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.drawer-clear {
  min-height: 36px;
  padding: 7px 10px;
}

.drawer-close {
  display: inline-grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(255, 252, 244, 0.86);
  color: var(--royal);
  font: inherit;
  font-weight: 900;
  cursor: pointer;
}

.drawer-list {
  display: grid;
  align-content: start;
  gap: 10px;
  overflow: auto;
  padding: 12px 2px;
}

.drawer-item {
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 10px;
  background: rgba(255, 252, 244, 0.78);
}

.drawer-item.is-current {
  border-color: rgba(15, 118, 110, 0.36);
  background: rgba(228, 243, 237, 0.72);
}

.drawer-item img {
  width: 58px;
  height: 58px;
  border-radius: 14px;
  object-fit: cover;
}

.drawer-item h3,
.drawer-item p {
  margin: 0;
}

.drawer-item h3 {
  color: var(--royal);
  font-size: 16px;
  line-height: 1.2;
}

.queue-current {
  display: inline-flex;
  margin-inline-start: 6px;
  border-radius: 999px;
  padding: 2px 7px;
  background: var(--accent-soft);
  color: var(--accent-dark);
  font-size: 11px;
  font-weight: 900;
  white-space: nowrap;
}

.drawer-item p {
  color: var(--muted);
  font-size: 13px;
  font-weight: 700;
}

.drawer-item > .button,
.drawer-actions {
  grid-column: 1 / -1;
}

.drawer-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.drawer-empty {
  margin: 0;
  padding: 14px 2px 2px;
}

.resume-card,
.app-player {
  position: fixed;
  z-index: 20;
  inset-inline: 16px;
  border: 1px solid rgba(18, 40, 77, 0.18);
  background: rgba(255, 250, 240, 0.96);
  box-shadow: 0 18px 46px rgba(38, 26, 16, 0.18);
  backdrop-filter: blur(18px);
}

.resume-card {
  bottom: 86px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  max-width: 720px;
  margin-inline: auto;
  border-radius: 22px;
  padding: 13px 15px;
}

.resume-close {
  display: inline-grid;
  place-items: center;
  flex: 0 0 auto;
  width: 44px;
  height: 44px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(255, 252, 244, 0.86);
  color: var(--royal);
  font: inherit;
  font-weight: 900;
  cursor: pointer;
  position: relative;
  z-index: 1;
  touch-action: manipulation;
}

.resume-card > div {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.resume-card strong,
.resume-card span:not(.resume-label) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resume-label {
  color: var(--accent-dark);
  font-size: 13px;
  font-weight: 900;
}

.app-player {
  bottom: calc(14px + var(--safe-bottom));
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr) max-content max-content max-content max-content max-content max-content 42px;
  align-items: center;
  gap: 10px;
  max-width: 980px;
  margin-inline: auto;
  border-radius: 24px;
  padding: 10px;
}

.player-toggle,
.player-queue-nav,
.player-speed,
.player-skip,
.player-close {
  display: inline-grid;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(255, 252, 244, 0.86);
  color: var(--royal);
  font: inherit;
  font-weight: 900;
  cursor: pointer;
  touch-action: manipulation;
}

.player-toggle {
  width: 52px;
  height: 52px;
  border-color: var(--royal);
  background: var(--royal);
  color: #fff;
  font-size: 20px;
}

.player-queue-nav,
.player-speed,
.player-skip,
.player-close {
  width: 42px;
  height: 42px;
}

.player-queue-nav {
  font-size: 22px;
}

.player-queue-nav:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.player-speed {
  min-width: 46px;
  padding-inline: 8px;
}

.player-main {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.player-main strong,
.player-main span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.player-main span,
.player-time {
  color: var(--muted);
  font-size: 13px;
  font-weight: 800;
}

.player-seek {
  width: 100%;
  accent-color: var(--accent);
}

.player-time {
  white-space: nowrap;
}

.footer {
  border-top: 1px solid var(--line);
  padding-bottom: var(--safe-bottom);
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

[hidden],
.hidden {
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
    min-height: 140px;
  }
}

@media (max-width: 640px) {
  body {
    padding-block: var(--safe-top) calc(174px + var(--safe-bottom));
  }

  .nav,
  .section {
    width: min(1180px, calc(100% - 24px));
  }

  .nav {
    align-items: stretch;
    flex-direction: column;
    padding: 12px 0;
  }

  .brand {
    max-width: 100%;
    font-size: 24px;
  }

  .nav-actions {
    display: flex;
    flex-wrap: nowrap;
    gap: 7px;
    overflow-x: auto;
    padding-bottom: 2px;
    width: 100%;
    max-width: 100%;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }

  .nav-actions::-webkit-scrollbar {
    display: none;
  }

  .nav-actions a,
  .nav-button,
  .language-toggle,
  .nav-actions .button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
    min-width: 0;
    width: auto;
    min-height: 36px;
    padding: 7px 11px;
    font-size: 14px;
    text-align: center;
    white-space: nowrap;
  }

  .hero {
    grid-template-columns: 1fr;
    padding-top: 30px;
  }

  .hero-actions {
    display: grid;
    grid-template-columns: 1fr;
  }

  .hero-actions .button {
    justify-content: center;
    text-align: center;
    white-space: normal;
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

  .filter-group {
    justify-content: center;
    width: 100%;
  }

  .filter-toggle {
    flex: 1 1 0;
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

  .resume-card {
    inset-inline: 10px;
    bottom: 132px;
    align-items: stretch;
    flex-direction: column;
  }

  .app-drawer {
    inset-block: calc(74px + var(--safe-top)) calc(8px + var(--safe-bottom));
    inset-inline: 12px;
    width: auto;
    border-radius: 22px;
  }

  body.has-player .app-drawer {
    inset-block-end: calc(156px + var(--safe-bottom));
  }

  .resume-card .button {
    justify-content: center;
  }

  .app-player {
    inset-inline: 12px;
    bottom: calc(10px + var(--safe-bottom));
    grid-template-columns: 48px minmax(0, 1fr) 40px 40px 40px 40px;
    gap: 8px;
    border-radius: 20px;
  }

  .player-main {
    grid-column: 2 / 6;
    grid-row: 1;
  }

  .player-toggle {
    grid-column: 1;
    grid-row: 1 / span 2;
    width: 48px;
    height: 48px;
  }

  .player-time {
    grid-column: 2;
    grid-row: 2;
  }

  .player-queue-nav,
  .player-speed,
  .player-skip,
  .player-close {
    width: 40px;
    height: 40px;
  }

  .player-queue-nav[data-player-prev] {
    grid-column: 3;
    grid-row: 2;
  }

  .player-speed {
    grid-column: 4;
    grid-row: 2;
    min-width: 40px;
    padding-inline: 4px;
  }

  .player-queue-nav[data-player-next] {
    grid-column: 5;
    grid-row: 2;
  }

  .player-skip[data-player-skip="-15"] {
    display: none;
  }

  .player-skip[data-player-skip="30"] {
    grid-column: 6;
    grid-row: 2;
  }

  .player-close {
    grid-column: 6;
    grid-row: 1;
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
            <td><a href="{_escape(item["feed_url"])}" target="_blank" rel="noopener noreferrer">RSS</a></td>
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
                "feed_url": public_feed_url(show),
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


def _build_onboarding_page(site_config: SiteConfig) -> None:
    onboard_dir = PUBLIC_DIR / "onboard"
    onboard_dir.mkdir(parents=True, exist_ok=True)
    repo = "https://github.com/shaqo88/youtube-podcast-feeds/issues/new"
    youtube_url = f"{repo}?template=youtube-podcast-onboarding.yml"
    drive_url = f"{repo}?template=drive-podcast-onboarding.yml"
    feed_url = f"{repo}?template=feed-podcast-onboarding.yml"
    body = f"""
    <section class="section hero compact-hero">
      <div class="hero-copy">
        <p class="kicker" data-i18n="onboard">{HE["onboard"]}</p>
        <h1>{HE["hero_cta_secondary"]}</h1>
        <p class="muted">בחרו את סוג המקור. הבקשה תיפתח כ-Issue מסודר ב-GitHub, ומשם אפשר לאשר ולהכניס למערכת.</p>
      </div>
      <div class="hero-visual home-visual" aria-hidden="true">
        <div class="scroll-card home-scroll-card">
          <div class="home-app-title">{_brand_mark()}<span>{BRAND}</span></div>
          <div class="home-app-chip">{HE["source_mix"]}</div>
        </div>
      </div>
    </section>
    <section class="section">
      <div class="onboard-options">
        <article class="onboard-option">
          <h2>יוטיוב</h2>
          <p>ערוץ או פלייליסט YouTube ש-Torah Pod יסנכרן אחרי אישור.</p>
          <a class="button primary" href="{youtube_url}" target="_blank" rel="noopener noreferrer">פתיחת בקשת YouTube</a>
        </article>
        <article class="onboard-option">
          <h2>Google Drive</h2>
          <p>תיקייה עם קבצי שמע מוכנים. צריך לשתף אותה כ-Viewer עם חשבון השירות.</p>
          <a class="button primary" href="{drive_url}" target="_blank" rel="noopener noreferrer">פתיחת בקשת Drive</a>
        </article>
        <article class="onboard-option">
          <h2>פיד קיים</h2>
          <p>RSS/Atom של פודקאסט קיים. ברירת המחדל היא קישור לפיד המקורי וסריקה להצגה באתר.</p>
          <a class="button primary" href="{feed_url}" target="_blank" rel="noopener noreferrer">פתיחת בקשת פיד קיים</a>
        </article>
      </div>
    </section>
"""
    _write_text(onboard_dir / "index.html", _page("Onboard", body, site_config=site_config, relative_prefix="../"))


def _write_linked_feed_redirects(shows: list[ShowConfig]) -> None:
    redirects = [
        f"/{show.slug}/feed.xml {public_feed_url(show)} 302"
        for show in shows
        if is_linked_existing_feed_show(show)
    ]
    redirects_path = PUBLIC_DIR / "_redirects"
    if redirects:
        _write_text(redirects_path, "\n".join(redirects) + "\n")
    elif redirects_path.exists():
        redirects_path.unlink()


def build_site(shows: list[ShowConfig]) -> None:
    site_config = load_site_config()
    _write_css()
    _write_app_js()
    _write_pwa_assets()
    _copy_donation_assets(site_config)
    show_episodes = {show.slug: _load_show_episodes(show) for show in shows}
    shows = sorted(
        shows,
        key=lambda show: show_episodes[show.slug][0].get("published", "") if show_episodes[show.slug] else "",
        reverse=True,
    )
    all_episodes = sorted(
        (
            {
                **episode,
                "show_slug": show.slug,
                "show_title": show.podcast.title,
                "show_author": show.podcast.author,
                "artwork_url": f"{show.slug}/assets/podcast-cover.png",
            }
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
          <div class="home-app-title">{_brand_mark()}<span>{BRAND}</span></div>
          <div class="home-app-row"><span>{HE["total_shows"]}</span><strong>{len(shows)}</strong></div>
          <div class="home-app-row"><span>{HE["total_episodes"]}</span><strong>{total_episodes}</strong></div>
          <div class="home-app-chip">{HE["queue"]} · {HE["library"]}</div>
        </div>
      </div>
    </section>
    <section class="section" id="podcasts">
      <div class="toolbar">
        <h2 data-i18n="all_shows">{HE["all_shows"]}</h2>
        <div class="toolbar-controls" data-list-controls="podcast-list">
          <div class="search-field">
            <label for="podcast-search" data-i18n="search_podcasts">{HE["search_podcasts"]}</label>
            <input id="podcast-search" class="search" type="search" data-search-target="podcast-list" data-i18n-placeholder="search_podcasts_placeholder" placeholder="{_escape(HE['search_podcasts_placeholder'])}">
          </div>
          <div class="filter-group" role="group" aria-label="{HE["filter_group"]}">
            <button class="button filter-toggle" type="button" data-filter-toggle="podcast-list" aria-pressed="false" data-i18n="filter_hosted_toggle">{HE["filter_hosted_toggle"]}</button>
            <button class="button filter-toggle" type="button" data-library-filter-toggle="podcast-list" aria-pressed="false" data-i18n="filter_library_toggle">{HE["filter_library_toggle"]}</button>
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
                "feed_url": public_feed_url(show),
                "artwork_url": show.podcast.artwork_url,
                "platforms": show.podcast.platforms,
                "episode_count": len(episodes),
            }
        )
        platform_buttons = _platform_buttons(show.podcast.platforms)
        if platform_buttons:
            platform_buttons = f"\n            {platform_buttons}"
        source_badge = _show_hosting_badge(show)
        episode_items = "\n".join(
            _episode_item(
                {
                    **episode,
                    "show_slug": show.slug,
                    "show_title": show.podcast.title,
                    "show_author": show.podcast.author,
                    "artwork_url": "assets/podcast-cover.png",
                }
            )
            for episode in episodes
        )
        body = f"""
    <section class="section">
      <article class="show-hero" data-show-card data-show-slug="{_escape(show.slug)}" data-show-title="{_escape(show.podcast.title)}" data-show-author="{_escape(show.podcast.author)}" data-show-artwork="assets/podcast-cover.png" data-show-url="index.html">
        <img src="assets/podcast-cover.png" alt="">
        <div>
          <div class="show-page-meta">{source_badge}</div>
          <h1>{_escape(show.podcast.title)}</h1>
          <p>{_escape(show.podcast.author)}</p>
          <p class="muted">{_escape(show.podcast.description)}</p>
          <div class="show-actions">
            <button class="button follow-button" type="button" data-follow-show data-i18n="follow">{HE["follow"]}</button>
            <a class="button primary" href="{_escape(_show_feed_href(show))}"{_show_feed_attrs(show)} data-i18n="feed">{HE["feed"]}</a>
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
    _build_onboarding_page(site_config)
    _build_donation_page(site_config)
    _build_contact_page(site_config)
    _write_linked_feed_redirects(shows)
    print(f"{PUBLIC_DIR / 'index.html'} written with {len(shows)} show(s)")
