from __future__ import annotations

import html
import hashlib
import json
import re
import shutil
from datetime import date
from datetime import datetime
from datetime import timedelta
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
    "subscriptions": "הספרייה שלך",
    "subscriptions_recent": "חדש מהפודקאסטים שבחרת",
    "recent_from_library": "חדש מהספרייה",
    "all_subscriptions": "כל הפודקאסטים במעקב",
    "subscriptions_empty_title": "בחרו פודקאסטים למעקב",
    "subscriptions_empty_text": "אחרי שתעקבו אחרי פודקאסטים, הפרקים החדשים שלהם יופיעו כאן ראשונים.",
    "suggested_subscriptions": "הצעות להתחלה",
    "no_subscription_episodes": "אין עדיין פרקים חדשים מהספרייה שלך.",
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
    "about_text": "Torah Pod מרכז שיעורי תורה ופודקאסטים במקום אחד, עם ספרייה אישית, תור האזנה ו-RSS פתוח לאפליקציות פודקאסטים.",
    "how_it_works": "מה אפשר לעשות כאן",
    "how_it_works_text": "עקבו אחרי פודקאסטים, ראו פרקים חדשים מהספרייה שלכם, הוסיפו פרקים לתור והמשיכו להאזין מכל מכשיר.",
    "source_mix": "מאזינים חופשי, בלי חשבון",
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
    "player_minimize": "מזעור",
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
    "subscriptions": "Your Library",
    "subscriptions_recent": "New from podcasts you follow",
    "recent_from_library": "New from your library",
    "all_subscriptions": "All followed podcasts",
    "subscriptions_empty_title": "Choose podcasts to follow",
    "subscriptions_empty_text": "After you follow podcasts, their newest episodes appear here first.",
    "suggested_subscriptions": "Suggested follows",
    "no_subscription_episodes": "No recent episodes from your library yet.",
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
    "about_text": "Torah Pod brings Torah podcasts into one listening home, with a personal library, queue, and open RSS feeds for podcast apps.",
    "how_it_works": "What you can do here",
    "how_it_works_text": "Follow podcasts, see new episodes from your library, add episodes to your queue, and keep listening across devices.",
    "source_mix": "Listen freely, no account required",
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
    "player_minimize": "Minimize",
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


def _plain_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


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
    route_attr = ' data-app-route="/donate/"' if site_config.donations else ""
    return (
        f'<a class="{_escape(class_name)}" href="{_escape(href)}"'
        f'{external_attrs}{route_attr} data-i18n="donate">{HE["donate"]}</a>'
    )


def _page(title: str, body: str, *, site_config: SiteConfig, relative_prefix: str = "") -> str:
    css = f"{relative_prefix}assets/site.css"
    app_js = f"{relative_prefix}assets/app.js"
    manifest = f"{relative_prefix}manifest.webmanifest"
    home = f"{relative_prefix}index.html"
    onboard = f"{relative_prefix}onboard/"
    about = f"{relative_prefix}about/"
    contact = f"{relative_prefix}contact/"
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
      <a class="brand" href="{home}" data-app-route="/">{_brand_mark()}<span>{BRAND}</span></a>
      <div class="nav-actions">
        <a href="{onboard}" data-app-route="/onboard/" data-i18n="onboard">{HE["onboard"]}</a>
        <a href="{about}" data-app-route="/about/" data-i18n="about">{HE["about"]}</a>
        <a href="{contact}" data-app-route="/contact/" data-i18n="contact">{HE["contact"]}</a>{donation_nav}
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
      <a href="{contact}" data-app-route="/contact/" data-i18n="contact">{HE["contact"]}</a>
    </div>
  </footer>
  <nav class="app-bottom-nav" aria-label="App">
    <a class="bottom-nav-item" href="{home}" data-app-route="/">
      <span class="bottom-nav-icon" aria-hidden="true">⌂</span>
      <span data-i18n="home">{HE["home"]}</span>
    </a>
    <button class="bottom-nav-item" type="button" data-library-open>
      <span class="bottom-nav-icon" aria-hidden="true">▣</span>
      <span data-i18n="library">{HE["library"]}</span>
    </button>
    <button class="bottom-nav-item" type="button" data-queue-open>
      <span class="bottom-nav-icon" aria-hidden="true">≡</span>
      <span><span data-i18n="queue">{HE["queue"]}</span> <span class="nav-count" data-queue-count hidden></span></span>
    </button>
  </nav>
  <aside class="app-drawer" data-library-drawer hidden aria-label="{HE["library"]}">
    <div class="drawer-head">
      <h2 data-i18n="library">{HE["library"]}</h2>
      <button class="drawer-close" type="button" data-drawer-close data-i18n-aria="player_close" aria-label="{HE["player_close"]}">×</button>
    </div>
    <div class="drawer-list" data-library-list></div>
    <div class="drawer-empty" data-library-empty>
      <p class="muted" data-i18n="empty_library">{HE["empty_library"]}</p>
      <a class="button" href="{home}#podcasts" data-app-route="/#podcasts" data-browse-podcasts data-i18n="browse_podcasts">{HE["browse_podcasts"]}</a>
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
    <div class="player-main" role="button" tabindex="0" data-player-details aria-expanded="false">
      <img class="player-artwork" src="" alt="" data-player-artwork hidden>
      <strong data-player-title></strong>
      <span data-player-show></span>
      <input class="player-seek" type="range" min="0" max="1" value="0" step="1" data-player-seek aria-label="Progress">
      <p class="player-description" data-player-description hidden></p>
    </div>
    <span class="player-time" data-player-time>0:00 / 0:00</span>
    <button class="player-queue-nav" type="button" data-player-prev data-i18n-aria="previous_queue" aria-label="{HE["previous_queue"]}">‹</button>
    <button class="player-speed" type="button" data-player-speed data-i18n-aria="playback_speed" aria-label="{HE["playback_speed"]}">1x</button>
    <button class="player-queue-nav" type="button" data-player-next data-i18n-aria="next_queue" aria-label="{HE["next_queue"]}">›</button>
    <button class="player-skip" type="button" data-player-skip="-15" data-i18n-aria="skip_back" aria-label="{HE["skip_back"]}">-15</button>
    <button class="player-skip" type="button" data-player-skip="30" data-i18n-aria="skip_forward" aria-label="{HE["skip_forward"]}">+30</button>
    <button class="player-minimize" type="button" data-player-minimize data-i18n-aria="player_minimize" aria-label="{HE["player_minimize"]}">⌄</button>
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


def _episode_item(episode: dict[str, Any], *, id_suffix: str = "") -> str:
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
    dom_id = f"{_episode_dom_id(episode)}{id_suffix}"
    artwork = episode.get("artwork_url") or ""
    return f"""
      <article id="{dom_id}" class="episode" data-list-item data-episode-id="{_escape(episode_id)}" data-episode-title="{_escape(episode.get("title"))}" data-episode-show="{_escape(show_title or episode.get("show_author") or BRAND)}" data-episode-show-slug="{_escape(episode.get("show_slug"))}" data-filter-value="{_escape(episode.get("filter_value"))}" data-episode-artwork="{_escape(artwork)}" data-episode-duration="{_escape(episode.get("duration"))}" data-episode-src="{_escape(episode.get("url"))}" data-episode-description="{_escape(_plain_text(episode.get("description")))}" data-search-item="{_search_text(episode.get("title"), _plain_text(episode.get("description")), show_title, episode.get("show_author"))}">
        <div class="episode-head">
          <div>
            <h3>{_escape(episode.get("title"))}</h3>{show_title_line}
          </div>
          <p class="episode-meta">{_escape(meta)}</p>
        </div>
        <audio preload="none" data-audio-src="{_escape(episode.get("url"))}" hidden aria-hidden="true"></audio>
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


def _subscription_show_block(show: ShowConfig, episodes: list[dict[str, Any]]) -> str:
    return f"""
        <div class="subscription-show" data-subscription-show data-show-slug="{_escape(show.slug)}" hidden>
{_show_card(show, episodes)}
        </div>
"""


def _episode_with_show_context(show: ShowConfig, episode: dict[str, Any]) -> dict[str, Any]:
    return {
        **episode,
        "show_slug": show.slug,
        "show_title": show.podcast.title,
        "show_author": show.podcast.author,
        "artwork_url": f"{show.slug}/assets/podcast-cover.png",
        "filter_value": _show_hosting_key(show),
    }


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
  const playbackDebugKey = "torahpod:v1:playback-debug";
  const playbackRates = [1, 1.25, 1.5, 1.75, 2];
  const player = document.querySelector("[data-player]");
  const playerToggle = document.querySelector("[data-player-toggle]");
  const playerTitle = document.querySelector("[data-player-title]");
  const playerShow = document.querySelector("[data-player-show]");
  const playerArtwork = document.querySelector("[data-player-artwork]");
  const playerDescription = document.querySelector("[data-player-description]");
  const playerTime = document.querySelector("[data-player-time]");
  const playerSeek = document.querySelector("[data-player-seek]");
  const playerPrev = document.querySelector("[data-player-prev]");
  const playerNext = document.querySelector("[data-player-next]");
  const playerSpeed = document.querySelector("[data-player-speed]");
  const playerMinimize = document.querySelector("[data-player-minimize]");
  const playerClose = document.querySelector("[data-player-close]");
  const playerDetails = document.querySelector("[data-player-details]");
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
  let activeNativeState = null;
  let activeNativePlaying = false;
  let nativeFallbackTimer = 0;
  let nativePlaybackRequestId = 0;
  let nativeNotificationLastSentAt = 0;
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

  function recordPlaybackEvent(name, details = {}) {
    const event = {
      at: new Date().toISOString(),
      name,
      page: location.pathname,
      id: details.id || activeState?.id || "",
      title: details.title || activeState?.title || "",
      position: Math.max(0, Math.floor(Number(details.position || activeAudio?.currentTime || 0))),
      native: Boolean(window.TorahPodNative),
    };
    try {
      const events = safeArray(playbackDebugKey);
      events.push(event);
      safeSet(playbackDebugKey, events.slice(-80));
    } catch {
      // Diagnostics must never affect playback.
    }
  }

  window.TorahPodPlaybackDebug = () => safeArray(playbackDebugKey);

  function nativeAudioBridge() {
    let nativeAudioEnabled = false;
    try {
      nativeAudioEnabled = localStorage.getItem("torahpod-native-audio-enabled") === "true";
    } catch {
      nativeAudioEnabled = false;
    }
    if (!nativeAudioEnabled) return null;
    return window.TorahPodNative && typeof window.TorahPodNative.play === "function"
      ? window.TorahPodNative
      : null;
  }

  function nativeNotificationBridge() {
    return window.TorahPodNative && typeof window.TorahPodNative.htmlPlayback === "function"
      ? window.TorahPodNative
      : null;
  }

  function syncNativeNotification(audio, state, playing, options = {}) {
    const bridge = nativeNotificationBridge();
    if (!bridge || !state?.src || !audio) return;
    const now = Date.now();
    if (!options.force && now - nativeNotificationLastSentAt < 2000) return;
    nativeNotificationLastSentAt = now;
    const duration = Number.isFinite(audio.duration) && audio.duration > 0
      ? audio.duration
      : Number(state.duration || 0);
    const payload = {
      ...state,
      position: Math.max(0, Math.floor(audio.currentTime || 0)),
      duration: Math.max(0, Math.floor(duration || 0)),
      playing: playing === true,
    };
    try {
      bridge.htmlPlayback(JSON.stringify(payload));
      if (options.force) recordPlaybackEvent("notification-sync", { id: state.id, title: state.title, position: payload.position });
    } catch {
      // Native notification mirroring is best-effort.
    }
  }

  function stopNativeNotification() {
    nativeNotificationLastSentAt = 0;
    try {
      nativeNotificationBridge()?.htmlStop();
    } catch {
      // Native notification mirroring is best-effort.
    }
  }

  window.TorahPodNativeControl = (payload = {}) => {
    const command = payload?.command || "";
    if (command === "toggle") {
      if (activeAudio) {
        if (activeAudio.paused) activeAudio.play().catch(() => {});
        else activeAudio.pause();
      } else if (activeState?.src) {
        playHtmlState(activeState);
      }
    } else if (command === "play") {
      if (activeAudio) activeAudio.play().catch(() => {});
      else if (activeState?.src) playHtmlState(activeState);
    } else if (command === "pause") {
      if (activeAudio) activeAudio.pause();
    } else if (command === "stop") {
      if (activeAudio) activeAudio.pause();
      stopNativeNotification();
    }
  };

  function nativeSeekBy(seconds) {
    const bridge = nativeAudioBridge();
    if (!bridge || typeof bridge.seekBy !== "function") return;
    try {
      bridge.seekBy(Math.floor(Number(seconds) || 0));
    } catch {
      // Native seek is best-effort.
    }
  }

  function nativeSeekTo(seconds) {
    const bridge = nativeAudioBridge();
    if (!bridge || typeof bridge.seekTo !== "function") return;
    try {
      bridge.seekTo(Math.max(0, Math.floor(Number(seconds) || 0)));
    } catch {
      // Native seek is best-effort.
    }
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
      description: article.dataset.episodeDescription || "",
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
    renderSubscriptions();
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

  function includePlaybackEntry(state) {
    if (!state?.id) return;
    const entries = queueEntries();
    if (entries.some((item) => item.id === state.id)) return;
    const activeId = activeState?.id || "";
    const activeIndex = entries.findIndex((item) => item.id === activeId);
    if (activeIndex >= 0) {
      entries.splice(activeIndex + 1, 0, state);
    } else {
      entries.unshift(state);
    }
    saveQueue(entries);
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

  function isVisibleEpisode(article) {
    return Boolean(article && !article.hidden && !article.closest("[hidden]"));
  }

  function updateVisibleEpisodeActions() {
    document.querySelectorAll("[data-episode-id]").forEach((article) => {
      if (isVisibleEpisode(article)) updateEpisodeActions(article);
    });
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
      <article class="drawer-item library-tile">
        <a class="library-tile-art" href="${escapeHtml(item.url)}">${drawerItemImage(item.artwork || "", item.title || "")}</a>
        <div class="library-tile-copy">
          <h3><a href="${escapeHtml(item.url)}">${escapeHtml(item.title)}</a></h3>
          <p>${escapeHtml(item.author || "")}</p>
        </div>
        <button class="button secondary" type="button" data-library-remove="${escapeHtml(item.slug)}">${t("remove_from_library")}</button>
      </article>
    `).join("");
    if (empty) empty.hidden = items.length > 0;
  }

  function renderSubscriptions() {
    const section = document.querySelector("[data-subscriptions-section]");
    if (!section) return;
    const empty = section.querySelector("[data-subscriptions-empty]");
    const active = section.querySelector("[data-subscriptions-active]");
    const none = section.querySelector("[data-subscriptions-none]");
    const followedItems = followedShows();
    const followed = new Set(followedItems.map((item) => item.slug));
    const hasSubscriptions = followedItems.length > 0;
    if (empty) empty.hidden = hasSubscriptions;
    if (active) active.hidden = !hasSubscriptions;
    if (!hasSubscriptions) return;

    let visible = 0;
    let recentVisible = 0;
    section.querySelectorAll("[data-library-recent-episode]").forEach((item) => {
      const matches = followed.has(item.dataset.episodeShowSlug || "");
      item.hidden = !matches;
      if (matches) {
        recentVisible += 1;
        updateEpisodeProgress(item);
        updateEpisodeActions(item);
      }
    });
    section.querySelectorAll("[data-subscription-show]").forEach((block) => {
      const matches = followed.has(block.dataset.showSlug || "");
      block.hidden = !matches;
      if (matches) visible += 1;
    });
    if (none) none.hidden = visible > 0;
    section.querySelector("[data-library-recent-block]")?.toggleAttribute("hidden", recentVisible === 0);
    updateFollowButtons();
    updateVisibleEpisodeActions();
    updateVisibleEpisodeProgress();
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
          <button class="button primary icon-button queue-play-button" type="button" data-queue-play="${escapeHtml(item.id)}" aria-label="${t("listen")}" title="${t("listen")}"><span aria-hidden="true">▶</span><span class="sr-only">${t("listen")}</span></button>
          <button class="button secondary icon-button" type="button" data-queue-move="${escapeHtml(item.id)}" data-queue-delta="-1" aria-label="${t("move_up")}" title="${t("move_up")}" ${index === 0 ? "disabled" : ""}><span aria-hidden="true">↑</span><span class="sr-only">${t("move_up")}</span></button>
          <button class="button secondary icon-button" type="button" data-queue-move="${escapeHtml(item.id)}" data-queue-delta="1" aria-label="${t("move_down")}" title="${t("move_down")}" ${index === items.length - 1 ? "disabled" : ""}><span aria-hidden="true">↓</span><span class="sr-only">${t("move_down")}</span></button>
          <button class="button secondary icon-button" type="button" data-queue-remove="${escapeHtml(item.id)}" aria-label="${t("remove_from_queue")}" title="${t("remove_from_queue")}"><span aria-hidden="true">×</span><span class="sr-only">${t("remove_from_queue")}</span></button>
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
    updateVisibleEpisodeActions();
    updateQueueNavButtons();
  }

  function updateLibraryAndQueueUi() {
    updateFollowButtons();
    renderLibrary();
    renderSubscriptions();
    updateQueueUi();
  }

  async function playQueuedEntry(entry) {
    if (!entry?.id) return;
    if (nativeAudioBridge() && entry.src) {
      playNativeState(entry);
      return;
    }
    let article = Array.from(document.querySelectorAll("[data-episode-id]"))
      .find((candidate) => candidate.dataset.episodeId === entry.id);
    if (!article && entry.href) {
      await navigateTo(entry.href);
      article = Array.from(document.querySelectorAll("[data-episode-id]"))
        .find((candidate) => candidate.dataset.episodeId === entry.id);
    }
    if (article) playEpisode(article);
    else if (entry.src) playHtmlState(entry);
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
    const entries = queueEntries();
    const currentIndex = Math.max(0, entries.findIndex((item) => item.id === currentId));
    const remaining = entries.filter((item) => item.id !== currentId);
    saveQueue(remaining);
    const next = remaining[currentIndex] || remaining[0];
    if (next) playQueuedEntry(next);
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

  function setPlayerExpanded(expanded) {
    if (!player) return;
    player.classList.toggle("is-expanded", expanded);
    document.body.classList.toggle("has-expanded-player", expanded);
    playerDetails?.setAttribute("aria-expanded", String(expanded));
  }

  function setDrawerActiveState(drawer) {
    const libraryActive = Boolean(drawer?.matches("[data-library-drawer]"));
    const queueActive = Boolean(drawer?.matches("[data-queue-drawer]"));
    document.body.classList.toggle("app-drawer-open", libraryActive || queueActive);
    document.querySelectorAll("[data-library-open]").forEach((node) => {
      node.setAttribute("aria-pressed", String(libraryActive));
    });
    document.querySelectorAll("[data-queue-open]").forEach((node) => {
      node.setAttribute("aria-pressed", String(queueActive));
    });
  }

  function openDrawer(drawer) {
    if (!drawer) return;
    setPlayerExpanded(false);
    document.querySelectorAll("[data-library-drawer], [data-queue-drawer]").forEach((node) => {
      node.hidden = node !== drawer;
    });
    drawer.hidden = false;
    setDrawerActiveState(drawer);
  }

  function closeDrawers() {
    document.querySelectorAll("[data-library-drawer], [data-queue-drawer]").forEach((node) => {
      node.hidden = true;
    });
    setDrawerActiveState(null);
  }

  function loadAudio(audio) {
    if (!audio.src && audio.dataset.audioSrc) {
      audio.src = audio.dataset.audioSrc;
      audio.preload = "none";
    }
    applyPlaybackRate(audio);
  }

  function audioForEpisode(article) {
    if (!article) return null;
    let audio = article.querySelector("audio[data-audio-src]");
    if (audio) return audio;
    const state = episodeState(article);
    if (!state?.src) return null;
    audio = document.createElement("audio");
    audio.hidden = true;
    audio.setAttribute("aria-hidden", "true");
    audio.preload = "none";
    audio.dataset.audioSrc = state.src;
    article.append(audio);
    return audio;
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

  function updateVisibleEpisodeProgress() {
    document.querySelectorAll("[data-episode-id]").forEach((article) => {
      if (isVisibleEpisode(article)) updateEpisodeProgress(article);
    });
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

  function saveCurrentStateProgress(audio, state) {
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
      previoustrack: () => playAdjacentQueued(-1),
      nexttrack: () => playAdjacentQueued(1),
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
    activeNativeState = null;
    activeNativePlaying = false;
    activeAudio = audio;
    activeEpisode = article;
    activeState = episodeState(article);
    if (!player || !activeState) return;
    document.body.classList.add("has-player");
    playerTitle.textContent = activeState.title;
    playerShow.textContent = activeState.show;
    if (playerArtwork) {
      playerArtwork.src = activeState.artwork || "";
      playerArtwork.hidden = !activeState.artwork;
    }
    if (playerDescription) {
      playerDescription.textContent = activeState.description || "";
      playerDescription.hidden = !activeState.description;
    }
    player.hidden = false;
    player.classList.remove("is-buffering");
    playerDetails?.setAttribute("aria-expanded", player.classList.contains("is-expanded") ? "true" : "false");
    playerToggle.textContent = audio.paused ? "▶" : "Ⅱ";
    playerToggle.setAttribute("aria-label", audio.paused ? t("listen") : t("pause"));
    if (playerSeek) playerSeek.disabled = false;
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

  function setPlayerStateForState(audio, state) {
    if (playerClosed) return;
    if (audio === closingAudio) return;
    activeNativeState = null;
    activeNativePlaying = false;
    activeAudio = audio;
    activeEpisode = null;
    activeState = state;
    if (!player || !activeState) return;
    document.body.classList.add("has-player");
    playerTitle.textContent = activeState.title;
    playerShow.textContent = activeState.show;
    if (playerArtwork) {
      playerArtwork.src = activeState.artwork || "";
      playerArtwork.hidden = !activeState.artwork;
    }
    if (playerDescription) {
      playerDescription.textContent = activeState.description || "";
      playerDescription.hidden = !activeState.description;
    }
    player.hidden = false;
    player.classList.remove("is-buffering");
    playerDetails?.setAttribute("aria-expanded", player.classList.contains("is-expanded") ? "true" : "false");
    playerToggle.textContent = audio.paused ? "▶" : "Ⅱ";
    playerToggle.setAttribute("aria-label", audio.paused ? t("listen") : t("pause"));
    if (playerSeek) playerSeek.disabled = false;
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

  function setNativePlayerState(state) {
    if (!player || !state?.src) return;
    activeNativeState = state;
    activeNativePlaying = false;
    activeAudio = null;
    activeEpisode = null;
    activeState = state;
    document.body.classList.add("has-player");
    playerTitle.textContent = state.title || "";
    playerShow.textContent = state.show || "";
    if (playerArtwork) {
      playerArtwork.src = state.artwork || "";
      playerArtwork.hidden = !state.artwork;
    }
    if (playerDescription) {
      playerDescription.textContent = state.description || "";
      playerDescription.hidden = !state.description;
    }
    player.hidden = false;
    player.classList.add("is-buffering");
    playerToggle.textContent = "…";
    playerToggle.setAttribute("aria-label", t("listen"));
    playerTime.textContent = "0:00 / --";
    if (playerSeek) {
      playerSeek.max = "1";
      playerSeek.value = "0";
      playerSeek.disabled = true;
    }
    updateQueueNavButtons();
    if (renderedActiveQueueId !== state.id) {
      renderedActiveQueueId = state.id;
      updateQueueUi();
    }
    updateResume();
  }

  function setPendingHtmlPlayerState(audio, state, article = null) {
    if (playerClosed || !player || !state?.src) return;
    activeNativeState = null;
    activeNativePlaying = false;
    activeAudio = audio;
    activeEpisode = article;
    activeState = state;
    document.body.classList.add("has-player");
    playerTitle.textContent = state.title || "";
    playerShow.textContent = state.show || "";
    if (playerArtwork) {
      playerArtwork.src = state.artwork || "";
      playerArtwork.hidden = !state.artwork;
    }
    if (playerDescription) {
      playerDescription.textContent = state.description || "";
      playerDescription.hidden = !state.description;
    }
    player.hidden = false;
    player.classList.add("is-buffering");
    playerDetails?.setAttribute("aria-expanded", player.classList.contains("is-expanded") ? "true" : "false");
    playerToggle.textContent = "...";
    playerToggle.setAttribute("aria-label", t("listen"));
    playerTime.textContent = `0:00 / ${state.duration ? formatTime(state.duration) : "--"}`;
    if (playerSeek) {
      playerSeek.max = String(Math.max(1, Math.floor(state.duration || 1)));
      playerSeek.value = "0";
      playerSeek.disabled = true;
    }
    updateQueueNavButtons();
    if (renderedActiveQueueId !== state.id) {
      renderedActiveQueueId = state.id;
      updateQueueUi();
    }
    updateResume();
  }

  function saveNativeProgress(position, duration) {
    if (!activeNativeState?.id) return;
    const now = Date.now();
    if (activeNativeState.lastSavedAt && now - activeNativeState.lastSavedAt < 4000) return;
    activeNativeState.lastSavedAt = now;
    const payload = {
      ...activeNativeState,
      position,
      duration,
      completed: false,
      updatedAt: now,
    };
    if (duration && duration - position < 20) {
      payload.position = 0;
      payload.completed = true;
    }
    safeSet(progressKey(activeNativeState.id), payload);
    safeSet(lastKey, payload);
    updateResume();
  }

  function updateNativeProgress(payload = {}) {
    if (!activeNativeState || !player) return;
    const duration = Math.max(0, Number(payload.duration || activeNativeState.duration || 0));
    const position = Math.max(0, Number(payload.position || 0));
    activeNativeState.duration = duration || activeNativeState.duration || 0;
    activeNativePlaying = payload.playing === true;
    if (activeNativePlaying || position > 0 || duration > 0) clearNativeFallback();
    player.classList.toggle("is-buffering", !activeNativePlaying && position === 0 && duration === 0);
    playerToggle.textContent = activeNativePlaying ? "Ⅱ" : "▶";
    playerToggle.setAttribute("aria-label", activeNativePlaying ? t("pause") : t("listen"));
    playerTime.textContent = `${formatTime(position)} / ${duration ? formatTime(duration) : "--"}`;
    if (playerSeek) {
      playerSeek.disabled = duration <= 0;
      playerSeek.max = String(Math.max(1, Math.floor(duration || 1)));
      if (!seeking) playerSeek.value = String(Math.floor(Math.min(position, duration || position)));
    }
    saveNativeProgress(position, duration);
  }

  window.TorahPodNativeProgress = updateNativeProgress;

  function clearNativeFallback() {
    if (!nativeFallbackTimer) return;
    clearTimeout(nativeFallbackTimer);
    nativeFallbackTimer = 0;
  }

  function scheduleNativeFallback(state, requestId) {
    clearNativeFallback();
    nativeFallbackTimer = window.setTimeout(() => {
      nativeFallbackTimer = 0;
      if (requestId !== nativePlaybackRequestId) return;
      if (!activeNativeState || activeNativeState.id !== state.id) return;
      try {
        nativeAudioBridge()?.stop();
      } catch {
        // Native stop is best-effort before falling back to HTML audio.
      }
      activeNativeState = null;
      activeNativePlaying = false;
      player?.classList.remove("is-buffering");
      playHtmlState(state);
    }, 3200);
  }

  function updatePlayerProgress() {
    if (!player || !activeAudio) return;
    const duration = Number.isFinite(activeAudio.duration) && activeAudio.duration > 0
      ? activeAudio.duration
      : Number(activeEpisode?.dataset.episodeDuration || activeState?.duration || 0);
    const position = activeAudio.currentTime || 0;
    playerTime.textContent = `${formatTime(position)} / ${formatTime(duration)}`;
    if (playerSeek && !seeking) {
      playerSeek.max = String(Math.max(1, Math.floor(duration || 1)));
      playerSeek.value = String(Math.floor(position));
    }
    if (activeState) updateMediaSession(activeAudio, activeState);
  }

  function rememberCurrentState(state) {
    if (!state?.id) return null;
    const saved = safeGet(progressKey(state.id));
    const payload = {
      ...state,
      position: Number(saved?.position || 0),
      duration: Number(state.duration || saved?.duration || 0),
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

  function playNativeState(state) {
    const bridge = nativeAudioBridge();
    if (!bridge || !state?.src) return false;
    recordPlaybackEvent("native-play-request", { id: state.id, title: state.title });
    const requestId = ++nativePlaybackRequestId;
    closingAudio = null;
    playerClosed = false;
    stopOtherAudio(null);
    rememberCurrentState(state);
    setNativePlayerState(state);
    try {
      bridge.play(JSON.stringify(state));
      scheduleNativeFallback(state, requestId);
      return true;
    } catch {
      clearNativeFallback();
      activeNativeState = null;
      activeNativePlaying = false;
      return false;
    }
  }

  function playNativeEpisode(article) {
    const state = episodeState(article);
    if (!state?.src) return false;
    includePlaybackEntry(state);
    return playNativeState(state);
  }

  function playHtmlState(state) {
    if (!state?.src) return false;
    recordPlaybackEvent("html-state-play-request", { id: state.id, title: state.title });
    clearNativeFallback();
    nativePlaybackRequestId += 1;
    if (activeNativeState) {
      try {
        nativeAudioBridge()?.stop();
      } catch {
        // Native stop is best-effort before falling back to HTML audio.
      }
      activeNativeState = null;
      activeNativePlaying = false;
    }
    closingAudio = null;
    playerClosed = false;
    const audio = document.createElement("audio");
    audio.hidden = true;
    audio.setAttribute("aria-hidden", "true");
    audio.preload = "none";
    audio.dataset.audioSrc = state.src;
    audioDock.append(audio);
    loadAudio(audio);
    rememberCurrentState(state);
    includePlaybackEntry(state);
    setPendingHtmlPlayerState(audio, state);
    recordPlaybackEvent("pending-player-shown", { id: state.id, title: state.title });
    audio.addEventListener("play", () => {
      recordPlaybackEvent("audio-play", { id: state.id, title: state.title });
      stopOtherAudio(audio);
      setPlayerStateForState(audio, state);
      syncNativeNotification(audio, state, true, { force: true });
    });
    audio.addEventListener("pause", () => {
      recordPlaybackEvent("audio-pause", { id: state.id, title: state.title, position: audio.currentTime });
      saveCurrentStateProgress(audio, state);
      if (audio === activeAudio) {
        setPlayerStateForState(audio, state);
        if (closingAudio !== audio) syncNativeNotification(audio, state, false, { force: true });
      }
    });
    audio.addEventListener("timeupdate", () => {
      if (audio !== activeAudio) return;
      setPlayerStateForState(audio, state);
      syncNativeNotification(audio, state, !audio.paused);
      if (!audio.dataset.lastSavedAt || Date.now() - Number(audio.dataset.lastSavedAt) > 4000) {
        audio.dataset.lastSavedAt = String(Date.now());
        saveCurrentStateProgress(audio, state);
      }
    });
    audio.addEventListener("ended", () => {
      recordPlaybackEvent("audio-ended", { id: state.id, title: state.title });
      saveCurrentStateProgress(audio, state);
      stopNativeNotification();
      playNextQueuedAfter(state.id || "");
    });
    audio.play().then(() => setPlayerStateForState(audio, state)).catch(() => {
      recordPlaybackEvent("audio-play-failed", { id: state.id, title: state.title });
      if (audio.parentElement === audioDock) audio.remove();
      if (activeAudio === audio) {
        activeAudio = null;
        activeState = null;
        activeEpisode = null;
        player?.classList.remove("is-buffering");
        if (playerToggle) playerToggle.textContent = "▶";
      }
    });
    return true;
  }

  function dockActiveAudio() {
    if (activeAudio && activeAudio.parentElement !== audioDock) {
      audioDock.append(activeAudio);
    }
  }

  function stopOtherAudio(nextAudio) {
    document.querySelectorAll("audio").forEach((candidate) => {
      if (candidate === nextAudio || candidate.paused) return;
      if (candidate === activeAudio) closingAudio = candidate;
      candidate.pause();
    });
    if (activeAudio && activeAudio !== nextAudio) {
      closingAudio = activeAudio;
      activeAudio.pause();
      if (activeEpisode) {
        saveCurrentProgress(activeAudio, activeEpisode);
      } else if (activeState) {
        saveCurrentStateProgress(activeAudio, activeState);
      }
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
    const requestedState = episodeState(article);
    if (requestedState) recordPlaybackEvent("episode-play-tap", { id: requestedState.id, title: requestedState.title });
    if (playNativeEpisode(article)) return;
    const audio = audioForEpisode(article);
    if (!audio) return;
    closingAudio = null;
    playerClosed = false;
    if (activeNativeState) {
      try {
        nativeAudioBridge()?.stop();
      } catch {
        // Native stop is best-effort before falling back to HTML audio.
      }
      activeNativeState = null;
      activeNativePlaying = false;
    }
    loadAudio(audio);
    bindEpisodeAudio(audio, article);
    restoreProgress(audio, article);
    rememberCurrentEpisode(audio, article);
    const state = requestedState || episodeState(article);
    includePlaybackEntry(state);
    setPendingHtmlPlayerState(audio, state, article);
    recordPlaybackEvent("pending-player-shown", { id: state.id, title: state.title });
    audio.play().then(() => setPlayerState(audio, article)).catch(() => {
      recordPlaybackEvent("audio-play-failed", { id: state.id, title: state.title });
      if (activeAudio === audio) {
        activeAudio = null;
        activeState = null;
        activeEpisode = null;
        player?.classList.remove("is-buffering");
        if (playerToggle) playerToggle.textContent = "▶";
      }
    });
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
      if (!isVisibleEpisode(article)) return;
      updateEpisodeProgress(article);
      updateEpisodeActions(article);
    });
  }

  function bindEpisodeAudio(audio, article) {
    if (!audio || audio.dataset.bound === "true") return;
    audio.dataset.bound = "true";
    audio.addEventListener("loadedmetadata", () => restoreProgress(audio, article));
    audio.addEventListener("play", () => {
      const state = episodeState(article);
      recordPlaybackEvent("audio-play", { id: state?.id, title: state?.title });
      closingAudio = null;
      playerClosed = false;
      stopOtherAudio(audio);
      restoreProgress(audio, article);
      rememberCurrentEpisode(audio, article);
      setPlayerState(audio, article);
      syncNativeNotification(audio, episodeState(article), true, { force: true });
    });
    audio.addEventListener("pause", () => {
      const state = episodeState(article);
      recordPlaybackEvent("audio-pause", { id: state?.id, title: state?.title, position: audio.currentTime });
      if (playerClosed && closingAudio === audio) return;
      saveCurrentProgress(audio, article);
      if (closingAudio === audio) return;
      if (audio === activeAudio) {
        setPlayerState(audio, article);
        syncNativeNotification(audio, episodeState(article), false, { force: true });
      }
    });
    audio.addEventListener("timeupdate", () => {
      if (playerClosed) return;
      if (closingAudio === audio) return;
      if (audio !== activeAudio) return;
      setPlayerState(audio, article);
      syncNativeNotification(audio, episodeState(article), !audio.paused);
      if (!audio.dataset.lastSavedAt || Date.now() - Number(audio.dataset.lastSavedAt) > 4000) {
        audio.dataset.lastSavedAt = String(Date.now());
        saveCurrentProgress(audio, article);
      }
    });
    audio.addEventListener("ended", () => {
      const state = episodeState(article);
      recordPlaybackEvent("audio-ended", { id: state?.id, title: state?.title });
      if (playerClosed) return;
      if (closingAudio === audio) return;
      saveCurrentProgress(audio, article);
      setPlayed(article, true);
      updatePlayerProgress();
      stopNativeNotification();
      playNextQueuedAfter(article.dataset.episodeId || "");
    });
  }

  function setupPlayerControls() {
    const closePlayer = () => {
      let saved = activeState;
      const audio = activeAudio;
      const article = activeEpisode;
      const nativeState = activeNativeState;
      if (player) player.hidden = true;
      setPlayerExpanded(false);
      playerClosed = true;
      activeAudio = null;
      activeState = null;
      activeEpisode = null;
      activeNativeState = null;
      activeNativePlaying = false;
      renderedActiveQueueId = "";
      document.body.classList.remove("has-player");
      updateQueueUi();
      updateQueueNavButtons();
      if (audio) {
        closingAudio = audio;
        audio.pause();
        saved = saveCurrentProgress(audio, article) || saved;
        stopNativeNotification();
      }
      if (nativeState) {
        try {
          nativeAudioBridge()?.stop();
        } catch {
          // Native stop is best-effort.
        }
        saved = nativeState;
      }
      player?.classList.remove("is-buffering");
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
      if (activeNativeState) {
        try {
          nativeAudioBridge()?.toggle();
          activeNativePlaying = !activeNativePlaying;
          playerToggle.textContent = activeNativePlaying ? "Ⅱ" : "▶";
          playerToggle.setAttribute("aria-label", activeNativePlaying ? t("pause") : t("listen"));
        } catch {
          // Native toggle is best-effort.
        }
        return;
      }
      if (!activeAudio) return;
      if (activeAudio.paused) activeAudio.play().catch(() => {});
      else activeAudio.pause();
    });
    playerPrev?.addEventListener("click", () => playAdjacentQueued(-1));
    playerNext?.addEventListener("click", () => playAdjacentQueued(1));
    playerSpeed?.addEventListener("click", cyclePlaybackRate);
    playerMinimize?.addEventListener("click", () => setPlayerExpanded(false));
    document.querySelectorAll("[data-player-skip]").forEach((button) => {
      button.addEventListener("click", () => {
        const delta = Number(button.dataset.playerSkip || 0);
        if (activeNativeState) {
          nativeSeekBy(delta);
          return;
        }
        if (!activeAudio) return;
        activeAudio.currentTime = Math.max(0, Math.min(activeAudio.duration || activeAudio.currentTime + delta, activeAudio.currentTime + delta));
      });
    });
    playerSeek?.addEventListener("input", () => {
      seeking = true;
      if (activeNativeState) {
        nativeSeekTo(Number(playerSeek.value || 0));
        seeking = false;
        return;
      }
      if (activeAudio) activeAudio.currentTime = Number(playerSeek.value || 0);
      seeking = false;
    });
    bindClosePress(playerClose, closePlayer);
    playerDetails?.addEventListener("click", (event) => {
      if (!player) return;
      if (event.target?.closest("input, button, a, textarea, select")) return;
      if (player.classList.contains("is-expanded")) return;
      setPlayerExpanded(true);
    });
    playerDetails?.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      if (player?.classList.contains("is-expanded")) return;
      event.preventDefault();
      playerDetails.click();
    });
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
          if (item.matches("[data-episode-id]")) {
            updateEpisodeProgress(item);
            updateEpisodeActions(item);
          }
        });
        if (more) more.hidden = matched.length <= visibleLimit;
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
      const episodeAction = event.target.closest?.("[data-episode-play], [data-queue-add], [data-queue-next], [data-toggle-played]");
      if (episodeAction) {
        const article = episodeAction.closest("[data-episode-id]");
        if (!article) return;
        event.preventDefault();
        if (episodeAction.matches("[data-episode-play]")) {
          playEpisode(article);
        } else if (episodeAction.matches("[data-queue-add]")) {
          toggleQueued(article);
        } else if (episodeAction.matches("[data-queue-next]")) {
          queueNext(article);
        } else if (episodeAction.matches("[data-toggle-played]")) {
          setPlayed(article, !isPlayed(article));
        }
        return;
      }

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

  function setupLanguage(options = {}) {
    const refreshUi = options.refreshUi !== false;
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
      if (refreshUi) {
        updateVisibleEpisodeProgress();
        updateLibraryAndQueueUi();
      }
      setupOnboardingForms(lang);
      if (refreshUi) updateResume();
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

  function setupOnboardingForms(language = html.lang === "en" ? "en" : "he") {
    const form = document.querySelector("#onboarding-form");
    if (!form) return;

    const status = form.querySelector("#status");
    const submitButton = form.querySelector("#submit-button");
    const languageToggle = document.querySelector("[data-language-toggle]");
    const sourceInputs = Array.from(form.querySelectorAll('input[name="source"]'));
    const sourceYoutube = form.querySelector("#source-youtube");
    const youtubeUrl = form.querySelector("#youtube-url");
    const driveUrl = form.querySelector("#drive-url");
    const feedUrl = form.querySelector("#feed-url");
    const approvalInput = form.querySelector("#approval");
    const fields = {
      title: form.querySelector("#title"),
      slug: form.querySelector("#slug"),
      speaker: form.querySelector("#speaker"),
      startDate: form.querySelector("#start-date"),
      description: form.querySelector("#description"),
      artwork: form.querySelector("#artwork"),
      contact: form.querySelector("#contact"),
      notes: form.querySelector("#notes"),
      companyWebsite: form.querySelector("#company-website"),
    };
    const groups = {
      youtube: form.querySelector("#youtube-fields"),
      drive: form.querySelector("#drive-fields"),
      feed: form.querySelector("#feed-fields"),
      title: form.querySelector("#title-fields"),
      speaker: form.querySelector("#speaker-fields"),
      slug: form.querySelector("#slug-fields"),
      startDate: form.querySelector("#start-date-fields"),
      description: form.querySelector("#description-fields"),
      artwork: form.querySelector("#artwork-fields"),
      contact: form.querySelector("#contact-fields"),
      notes: form.querySelector("#notes-fields"),
      approval: form.querySelector("#approval-fields"),
    };
    const text = {
      he: {
        toggle: "English",
        heading: "צירוף פודקאסט",
        intro: "מלאו פרטים בסיסיים. Torah Pod יבדוק ויאשר לפני פרסום.",
        stepOne: "בחרו מאיפה השיעורים מגיעים.",
        stepTwo: "מלאו פרטי רב, קישור ותאריך התחלה.",
        stepThree: "אחרי אישור, Torah Pod יוצר RSS פתוח להאזנה.",
        sourceLegend: "איפה נמצאים השיעורים?",
        youtubeChoice: "יוטיוב",
        driveChoice: "תיקיית Google Drive",
        feedChoice: "פיד פודקאסט קיים",
        sourceHint: "בחרו מקור אחד כדי להמשיך. אחר כך יוצגו רק השדות הרלוונטיים.",
        sourceRequired: "בחרו מקור אחד.",
        titleLabel: "שם הפודקאסט (לא חובה)",
        titleHint: "אם נשאר ריק, נשתמש בשם הרב.",
        speakerLabel: "שם הרב / מוסר השיעור",
        slugLabel: "שם קצר לקישור באנגלית",
        slugHint: "אותיות באנגלית, מספרים ומקפים בלבד. זה יהיה חלק מקישור הפיד.",
        startDateLabel: "תאריך התחלה",
        startDateHint: "רק שיעורים מהתאריך הזה והלאה ייכנסו לפודקאסט.",
        youtubeUrlLabel: "קישור ליוטיוב",
        youtubeUrlHint: "אפשר להדביק ערוץ או פלייליסט.",
        driveUrlLabel: "קישור לתיקיית Google Drive",
        feedUrlLabel: "קישור לפיד פודקאסט קיים",
        feedUrlHint: "אפשר להדביק RSS או Atom. Torah Pod ייקח מהפיד את שם הפודקאסט, הקישור, התיאור, הרב/מחבר, התמונה והפרקים.",
        shareFolder: "שתפו את התיקייה עם החשבון הזה כ-Viewer:",
        fileNameHint: "קובץ מוכן לפרסום: YYYY-MM-DD - Episode Title.ext",
        descriptionLabel: "תיאור (לא חובה)",
        descriptionHint: "ביוטיוב אפשר להשאיר ריק, ו-Torah Pod יוכל להשתמש בתיאור הערוץ.",
        artworkLabel: "קישור לתמונת הפודקאסט (לא חובה)",
        contactLabel: "כתובת אימייל שלכם (לא חובה)",
        notesLabel: "הערות נוספות (לא חובה)",
        approvalLabel: "אני מבין/ה שצריך אישור של Torah Pod לפני יצירת הפודקאסט.",
        submitButton: "שלחו בקשה",
        sending: "שולח בקשה...",
        success: "הבקשה נשלחה ל-Torah Pod.",
        issueLink: "קישור לבקשה",
        notConfigured: "הטופס עדיין לא חובר לשירות השליחה. פנו ל-Torah Pod.",
        failure: "לא הצלחנו לשלוח את הבקשה. נסו שוב מאוחר יותר.",
      },
      en: {
        toggle: "עברית",
        heading: "Podcast Onboarding",
        intro: "Send the basic details. Torah Pod reviews and approves before anything is published.",
        stepOne: "Choose where the lessons come from.",
        stepTwo: "Add the speaker, source link, and start date.",
        stepThree: "After approval, Torah Pod creates an open RSS feed.",
        sourceLegend: "Where are the lessons?",
        youtubeChoice: "YouTube",
        driveChoice: "Google Drive folder",
        feedChoice: "Existing podcast feed",
        sourceHint: "Choose one source to continue. Only relevant fields will appear.",
        sourceRequired: "Choose one source.",
        titleLabel: "Podcast name (optional)",
        titleHint: "If this is blank, the rabbi/speaker name will be used.",
        speakerLabel: "Rabbi / speaker name",
        slugLabel: "Short English URL name",
        slugHint: "Use lowercase English letters, numbers, and hyphens. This becomes part of the feed URL.",
        startDateLabel: "Start date",
        startDateHint: "Only lessons from this date and later will be included.",
        youtubeUrlLabel: "YouTube URL",
        youtubeUrlHint: "Paste a channel or playlist URL.",
        driveUrlLabel: "Google Drive folder URL",
        feedUrlLabel: "Existing podcast feed URL",
        feedUrlHint: "Paste an RSS or Atom feed. Torah Pod will use the feed title, link, description, author, artwork, and episodes.",
        shareFolder: "Share the folder with this account as Viewer:",
        fileNameHint: "Published files should be named: YYYY-MM-DD - Episode Title.ext",
        descriptionLabel: "Description (optional)",
        descriptionHint: "For YouTube, this can be blank and Torah Pod can use the channel description.",
        artworkLabel: "Artwork image URL (optional)",
        contactLabel: "Your email (optional)",
        notesLabel: "Additional notes (optional)",
        approvalLabel: "I understand Torah Pod must approve this before a podcast feed is created.",
        submitButton: "Submit Request",
        sending: "Submitting request...",
        success: "The request was sent to Torah Pod.",
        issueLink: "Request link",
        notConfigured: "This form is not connected to the submission service yet. Contact Torah Pod.",
        failure: "Could not submit the request. Try again later.",
      },
    };
    let currentLanguage = language === "en" ? "en" : "he";

    function selectedSource() {
      return form.querySelector('input[name="source"]:checked')?.value || "";
    }
    function value(field) {
      return field?.value.trim() || "";
    }
    function sourceUrl() {
      const source = selectedSource();
      if (source === "drive") return value(driveUrl);
      if (source === "feed") return value(feedUrl);
      if (source === "youtube") return value(youtubeUrl);
      return "";
    }
    function updateSourceFields() {
      const source = selectedSource();
      const needsDrive = source === "drive";
      const needsYouTube = source === "youtube";
      const needsFeed = source === "feed";
      const sourceSelected = needsDrive || needsYouTube || needsFeed;
      groups.drive?.classList.toggle("hidden", !needsDrive);
      groups.youtube?.classList.toggle("hidden", !needsYouTube);
      groups.feed?.classList.toggle("hidden", !needsFeed);
      ["title", "speaker", "slug", "startDate", "description", "artwork", "contact", "notes"].forEach((key) => {
        groups[key]?.classList.toggle("hidden", !sourceSelected || needsFeed);
      });
      groups.approval?.classList.toggle("hidden", !sourceSelected);
      submitButton?.classList.toggle("hidden", !sourceSelected);
      if (driveUrl) driveUrl.required = needsDrive;
      if (youtubeUrl) youtubeUrl.required = needsYouTube;
      if (feedUrl) feedUrl.required = needsFeed;
      if (fields.speaker) fields.speaker.required = sourceSelected && !needsFeed;
      if (fields.slug) fields.slug.required = sourceSelected && !needsFeed;
      if (fields.startDate) fields.startDate.required = sourceSelected && !needsFeed;
      if (approvalInput) approvalInput.required = sourceSelected;
      sourceYoutube?.setCustomValidity(sourceSelected ? "" : text[currentLanguage].sourceRequired);
    }
    function applyOnboardingLanguage(language) {
      currentLanguage = language === "en" ? "en" : "he";
      const labels = text[currentLanguage];
      if (languageToggle) languageToggle.textContent = labels.toggle;
      form.closest("main")?.querySelectorAll("[data-i18n]").forEach((element) => {
        const nextText = labels[element.dataset.i18n];
        if (nextText) element.textContent = nextText;
      });
      if (status) {
        status.textContent = "";
        status.classList.remove("error", "success");
      }
      updateSourceFields();
    }
    function endpoint() {
      const value = (form.dataset.workerEndpoint || "").trim();
      return !value || value.startsWith("__") ? "" : value.replace(/\/$/, "");
    }
    function payload() {
      const source = selectedSource();
      const useFeedMetadata = source === "feed";
      return {
        source,
        sourceUrl: sourceUrl(),
        youtubeUrl: value(youtubeUrl),
        driveUrl: value(driveUrl),
        feedUrl: value(feedUrl),
        title: useFeedMetadata ? "" : value(fields.title),
        slug: useFeedMetadata ? "" : value(fields.slug).toLowerCase(),
        speaker: useFeedMetadata ? "" : value(fields.speaker),
        startDate: useFeedMetadata ? "" : value(fields.startDate),
        description: useFeedMetadata ? "" : value(fields.description),
        artwork: useFeedMetadata ? "" : value(fields.artwork),
        contact: useFeedMetadata ? "" : value(fields.contact),
        notes: useFeedMetadata ? "" : value(fields.notes),
        companyWebsite: value(fields.companyWebsite),
      };
    }
    function showStatus(message, kind, issueUrl = "") {
      if (!status) return;
      status.textContent = message;
      status.classList.toggle("error", kind === "error");
      status.classList.toggle("success", kind === "success");
      if (issueUrl) {
        const link = document.createElement("a");
        link.href = issueUrl;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = text[currentLanguage].issueLink;
        status.append(" ", link);
      }
    }

    if (form.dataset.onboardingBound !== "true") {
      form.dataset.onboardingBound = "true";
      form.addEventListener("change", updateSourceFields);
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        updateSourceFields();
        if (!form.reportValidity()) return;
        const target = endpoint();
        if (!target) {
          showStatus(text[currentLanguage].notConfigured, "error");
          return;
        }
        if (submitButton) submitButton.disabled = true;
        showStatus(text[currentLanguage].sending, "");
        try {
          const response = await fetch(`${target}/submit`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload()),
          });
          const body = await response.json().catch(() => ({}));
          if (!response.ok || !body.ok) {
            showStatus(body.error || text[currentLanguage].failure, "error", body.issueUrl);
            return;
          }
          showStatus(text[currentLanguage].success, "success", body.issueUrl);
          form.reset();
          updateSourceFields();
        } catch {
          showStatus(text[currentLanguage].failure, "error");
        } finally {
          if (submitButton) submitButton.disabled = false;
        }
      });
    }

    applyOnboardingLanguage(currentLanguage);
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

  function siteRootPath() {
    const first = location.pathname.split("/").filter(Boolean)[0] || "";
    return first === "youtube-podcast-feeds" ? "/youtube-podcast-feeds/" : "/";
  }

  function routeFromLink(link) {
    if (link.dataset.appRoute) return link.dataset.appRoute;
    if (link.hasAttribute("data-browse-podcasts")) return "/#podcasts";
    if (!link.closest(".site-header, .footer")) return "";
    const routes = {
      home: "/",
      onboard: "/onboard/",
      about: "/about/",
      contact: "/contact/",
      donate: "/donate/",
    };
    return routes[link.dataset.i18n] || "";
  }

  function appLinkUrl(link) {
    const route = routeFromLink(link);
    if (!route) return new URL(link.href, location.href);
    const root = siteRootPath();
    const path = route.replace(/^\/+/, "");
    return new URL(`${root}${path}`, location.origin);
  }

  function isSamePageUrl(url) {
    return (
      url.origin === location.origin &&
      url.search === location.search &&
      normalizePagePath(url.pathname) === normalizePagePath(location.pathname)
    );
  }

  function shouldHandleNavigation(event, link, url) {
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
      const nextBottomNav = nextDocument.querySelector(".app-bottom-nav");
      if (!nextMain) throw new Error("Navigation response had no main content");

      dockActiveAudio();
      closeDrawers();
      document.title = nextDocument.title || document.title;
      if (nextHeader) document.querySelector(".site-header")?.replaceWith(nextHeader);
      document.querySelector("main")?.replaceWith(nextMain);
      if (nextFooter) document.querySelector(".footer")?.replaceWith(nextFooter);
      if (nextBottomNav) document.querySelector(".app-bottom-nav")?.replaceWith(nextBottomNav);
      if (push) history.pushState({}, "", url.href);
      setupLanguage({ refreshUi: false });
      setupLists();
      setupEpisodes();
      setupContactForms();
      setupOnboardingForms();
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
      const url = appLinkUrl(link);
      if (isSamePageUrl(url) && !url.hash) {
        event.preventDefault();
        closeDrawers();
        setPlayerExpanded(false);
        window.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }
      if (!shouldHandleNavigation(event, link, url)) return;
      event.preventDefault();
      navigateTo(url.href);
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

  setupLanguage({ refreshUi: false });
  setupLists();
  setupEpisodes();
  setupPlayerControls();
  setupLibraryQueueControls();
  setupContactForms();
  setupOnboardingForms();
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
        """const CACHE_NAME = "torah-pod-shell-v28";
const SHELL_ASSETS = [
  "./",
  "./index.html",
  "./about/",
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
  --bottom-nav-height: 74px;
}

body {
  margin: 0;
  padding-block: var(--safe-top) calc(156px + var(--safe-bottom));
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

.nav-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  order: 20;
  min-height: 40px;
  border: 1px solid rgba(15, 118, 110, 0.24);
  border-radius: 999px;
  padding: 8px 13px;
  background: rgba(15, 118, 110, 0.07);
  color: var(--accent-dark);
  font: inherit;
  font-weight: 800;
  cursor: pointer;
  text-decoration: none;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.42);
  transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease, background 160ms ease;
}

.nav-button:hover {
  transform: translateY(-1px);
  border-color: rgba(15, 118, 110, 0.45);
  background: rgba(15, 118, 110, 0.11);
  box-shadow: 0 8px 20px rgba(15, 118, 110, 0.1);
}

.nav-button::before {
  display: inline-grid;
  place-items: center;
  width: 19px;
  height: 19px;
  border-radius: 7px;
  background: rgba(15, 118, 110, 0.14);
  color: var(--accent-dark);
  font-size: 13px;
  line-height: 1;
}

.nav-button[data-library-open]::before {
  content: "▣";
}

.nav-button[data-queue-open]::before {
  content: "≡";
  font-size: 17px;
  font-weight: 900;
}

.nav-actions a {
  order: 10;
}

.language-toggle {
  order: 30;
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

.app-bottom-nav {
  position: fixed;
  z-index: 22;
  inset-inline: max(16px, env(safe-area-inset-left, 0px)) max(16px, env(safe-area-inset-right, 0px));
  bottom: calc(10px + var(--safe-bottom));
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  max-width: 520px;
  min-height: var(--bottom-nav-height);
  margin-inline: auto;
  border: 1px solid rgba(18, 40, 77, 0.18);
  border-radius: 26px;
  padding: 8px;
  background: rgba(255, 250, 240, 0.96);
  box-shadow: 0 18px 46px rgba(38, 26, 16, 0.18);
  backdrop-filter: blur(18px);
}

.bottom-nav-item {
  display: grid;
  place-items: center;
  align-content: center;
  gap: 3px;
  min-width: 0;
  border: 0;
  border-radius: 20px;
  padding: 8px 6px;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 13px;
  font-weight: 900;
  text-align: center;
  text-decoration: none;
  cursor: pointer;
  touch-action: manipulation;
}

.bottom-nav-item:hover,
.bottom-nav-item:focus,
.bottom-nav-item[aria-pressed="true"] {
  background: var(--accent-soft);
  color: var(--accent-dark);
  outline: 0;
}

.bottom-nav-icon {
  display: inline-grid;
  place-items: center;
  width: 26px;
  height: 24px;
  border-radius: 10px;
  background: rgba(15, 118, 110, 0.1);
  color: var(--accent-dark);
  font-size: 17px;
  line-height: 1;
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

.onboard-shell {
  display: grid;
  grid-template-columns: minmax(280px, 0.78fr) minmax(0, 1.22fr);
  gap: 24px;
  align-items: start;
  margin: 24px 0 54px;
}

.onboard-intro,
.onboard-form {
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--panel);
  box-shadow: var(--shadow-soft);
}

.onboard-intro {
  position: sticky;
  top: 96px;
  overflow: hidden;
  padding: 26px;
}

.onboard-intro::before {
  display: block;
  width: 90px;
  height: 4px;
  margin-bottom: 20px;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--gold), var(--accent), var(--royal));
  content: "";
}

.onboard-intro h1 {
  margin: 0 0 8px;
  color: var(--royal);
  font-family: "Heebo", Arial, sans-serif;
  font-size: clamp(38px, 6vw, 64px);
  line-height: 1.15;
  letter-spacing: -0.035em;
}

.onboard-steps {
  display: grid;
  gap: 12px;
  margin: 22px 0 0;
  padding: 0;
  list-style: none;
}

.onboard-steps li {
  display: grid;
  grid-template-columns: 1fr 34px;
  gap: 11px;
  align-items: start;
  color: var(--muted);
}

.step-number {
  display: grid;
  grid-column: 2;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 999px;
  background: var(--royal);
  color: #fff;
  font-weight: 800;
}

.step-text {
  grid-column: 1;
  grid-row: 1;
}

html[dir="ltr"] .onboard-steps li {
  grid-template-columns: 34px 1fr;
}

html[dir="ltr"] .step-number {
  grid-column: 1;
}

html[dir="ltr"] .step-text {
  grid-column: 2;
}

.onboard-form {
  display: grid;
  gap: 14px;
  padding: 24px;
}

.onboard-form label,
.onboard-form legend {
  display: block;
  margin-bottom: 6px;
  color: var(--royal);
  font-size: 14px;
  font-weight: 700;
}

.onboard-form input,
.onboard-form textarea {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 11px 12px;
  background: rgba(255, 255, 255, 0.72);
  color: var(--text);
  font: inherit;
}

.onboard-form input:focus,
.onboard-form textarea:focus {
  outline: 3px solid var(--focus);
  border-color: var(--gold);
}

.onboard-form textarea {
  min-height: 96px;
  resize: vertical;
}

.onboard-form fieldset {
  margin: 0;
  padding: 0;
  border: 0;
}

.choices {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.choice,
.check {
  display: grid;
  grid-template-columns: 1fr 20px;
  gap: 9px;
  align-items: start;
  padding: 13px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: rgba(255, 250, 240, 0.86);
  color: var(--text);
  font-weight: 700;
  cursor: pointer;
  transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease, background 160ms ease;
}

.choice {
  min-height: 92px;
  align-content: space-between;
}

.choice:hover,
.check:hover {
  transform: translateY(-1px);
  border-color: rgba(199, 138, 47, 0.55);
  box-shadow: 0 8px 20px rgba(54, 38, 20, 0.08);
}

.choice:has(input:checked) {
  border-color: var(--gold);
  background: linear-gradient(135deg, var(--gold-soft), var(--accent-soft));
}

.choice input,
.check input {
  grid-column: 2;
  grid-row: 1;
  width: 18px;
  height: 18px;
  margin-top: 2px;
}

.choice span,
.check span {
  grid-column: 1;
  grid-row: 1;
}

html[dir="ltr"] .choice,
html[dir="ltr"] .check {
  grid-template-columns: 20px 1fr;
}

html[dir="ltr"] .choice input,
html[dir="ltr"] .check input {
  grid-column: 1;
}

html[dir="ltr"] .choice span,
html[dir="ltr"] .check span {
  grid-column: 2;
}

.hint {
  margin-top: 5px;
  color: var(--muted);
  font-size: 13px;
}

.service-account {
  display: inline-block;
  max-width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--royal-soft);
  color: var(--text);
  direction: ltr;
  font-family: Consolas, "Courier New", monospace;
  font-size: 14px;
  overflow-wrap: anywhere;
}

.source-note {
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: linear-gradient(135deg, var(--accent-soft), rgba(246, 228, 189, 0.55));
}

.onboard-form .status {
  margin: 0;
  color: var(--muted);
  font-size: 14px;
}

.onboard-form .status.error {
  color: var(--danger);
  font-weight: 700;
}

.onboard-form .status.success {
  color: var(--accent-dark);
  font-weight: 700;
}

.honeypot {
  position: fixed;
  inset: 0 auto auto 0;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  opacity: 0;
  pointer-events: none;
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

.dashboard-section {
  padding-top: 28px;
}

.dashboard-toolbar {
  align-items: end;
  margin-top: 18px;
}

.dashboard-toolbar h1 {
  margin: 0 0 8px;
  color: var(--royal);
  font-family: "Heebo", Arial, sans-serif;
  font-size: clamp(36px, 7vw, 66px);
  line-height: 0.98;
  letter-spacing: -0.035em;
}

.dashboard-toolbar .muted {
  max-width: 720px;
  margin: 0;
  font-size: clamp(16px, 2vw, 20px);
}

.subscription-empty {
  display: grid;
  grid-template-columns: minmax(240px, 0.42fr) minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.empty-library-card {
  display: grid;
  gap: 10px;
  border: 1px solid rgba(15, 118, 110, 0.22);
  border-radius: var(--radius-lg);
  padding: 20px;
  background:
    radial-gradient(circle at 16% 18%, rgba(255, 255, 255, 0.92), transparent 9rem),
    linear-gradient(135deg, rgba(228, 243, 237, 0.92), rgba(255, 250, 240, 0.92));
  box-shadow: var(--shadow-soft);
}

.empty-library-card h2,
.section-subtitle {
  margin: 0;
  color: var(--royal);
  font-family: "Heebo", Arial, sans-serif;
  font-size: clamp(24px, 3vw, 31px);
  line-height: 1.1;
}

.empty-library-card p {
  margin: 0;
  color: var(--muted);
}

.section-subtitle {
  margin-bottom: 12px;
}

.subscription-suggestions {
  grid-template-columns: repeat(auto-fill, minmax(236px, 1fr));
}

.subscription-suggestions .show-card {
  grid-template-columns: 76px 1fr;
  gap: 12px;
  padding: 12px;
}

.subscription-suggestions .show-card h3 {
  font-size: 17px;
}

.subscription-suggestions .latest-line,
.subscription-suggestions .show-card-topline {
  display: none;
}

.subscription-show-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 18px;
}

.subscription-show {
  min-width: 0;
}

.subscription-show .show-card {
  display: grid;
  grid-template-columns: 1fr;
  gap: 9px;
  height: 100%;
  padding: 10px;
}

.subscription-show .show-art img {
  border-radius: 20px;
}

.subscription-show .show-card-body {
  display: grid;
  gap: 4px;
}

.subscription-show .show-card h3 {
  font-size: 16px;
}

.subscription-show .show-card p,
.subscription-show .latest-line,
.subscription-show .show-card-topline {
  display: none;
}

.library-recent-block {
  margin-bottom: 26px;
}

.compact-episode-list {
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
}

.compact-episode-list .episode {
  padding: 16px;
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
.about-panel h2,
.creator-panel h2 {
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
.player-minimize:focus,
.player-close:focus,
.resume-close:focus,
.drawer-close:focus,
.player-seek:focus,
.bottom-nav-item:focus {
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
.about-panel,
.creator-panel {
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

.creator-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin: 18px 0 54px;
  padding: 20px;
}

.creator-panel p {
  margin: 6px 0 0;
  color: var(--muted);
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
  display: grid;
  grid-template-columns: auto repeat(3, minmax(112px, max-content)) 1fr;
  align-items: center;
  gap: 9px;
  margin-top: 12px;
}

.episode-actions .button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 42px;
  padding: 9px 13px;
  white-space: nowrap;
}

audio[data-audio-src] {
  display: none;
}

.episode-play {
  min-height: 48px;
  border-color: var(--royal);
  padding: 11px 20px;
  background: var(--royal);
  color: #fff;
}

.episode-play::before,
.episode-queue::before,
.episode-queue-next::before,
.episode-played::before {
  display: inline-grid;
  place-items: center;
  width: 19px;
  height: 19px;
  border-radius: 999px;
  font-size: 13px;
  line-height: 1;
}

.episode-play::before {
  content: "▶";
}

.episode-queue::before {
  content: "+";
  background: rgba(15, 118, 110, 0.12);
  color: var(--accent-dark);
}

.episode-queue[aria-pressed="true"]::before {
  content: "−";
}

.episode-queue-next::before {
  content: "›";
  background: rgba(18, 40, 77, 0.1);
  color: var(--royal);
}

.episode-played::before {
  content: "✓";
  background: rgba(15, 118, 110, 0.12);
  color: var(--accent-dark);
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

.episode-links {
  justify-self: end;
}

.app-drawer {
  position: fixed;
  z-index: 25;
  inset-block: auto calc(96px + var(--safe-bottom));
  inset-inline: max(16px, env(safe-area-inset-left, 0px)) max(16px, env(safe-area-inset-right, 0px));
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  width: min(760px, calc(100vw - 32px));
  max-height: min(70vh, 620px);
  margin-inline: auto;
  border: 1px solid rgba(18, 40, 77, 0.18);
  border-radius: 28px 28px 22px 22px;
  padding: 16px;
  background: rgba(255, 250, 240, 0.98);
  box-shadow: 0 24px 70px rgba(38, 26, 16, 0.24);
  backdrop-filter: blur(18px);
}

body.has-player .app-drawer {
  inset-block-end: calc(176px + var(--safe-bottom));
}

.app-drawer::before {
  justify-self: center;
  width: 46px;
  height: 5px;
  margin-bottom: 8px;
  border-radius: 999px;
  background: rgba(18, 40, 77, 0.18);
  content: "";
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

[data-library-list].drawer-list {
  grid-template-columns: repeat(auto-fill, minmax(126px, 1fr));
  gap: 12px;
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

.library-tile {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  align-content: start;
}

.library-tile .library-tile-art {
  display: block;
}

.library-tile img {
  width: 100%;
  height: auto;
  aspect-ratio: 1;
  border-radius: 18px;
}

.library-tile h3 {
  font-size: 15px;
}

.library-tile-copy {
  display: grid;
  gap: 3px;
}

.drawer-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.icon-button {
  display: inline-grid;
  place-items: center;
  width: 42px;
  min-width: 42px;
  height: 42px;
  padding: 0;
  line-height: 1;
}

.icon-button span[aria-hidden="true"] {
  display: inline-grid;
  place-items: center;
  font-size: 18px;
}

.queue-play-button span[aria-hidden="true"] {
  font-size: 15px;
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
  bottom: calc(24px + var(--bottom-nav-height) + var(--safe-bottom));
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
  bottom: calc(24px + var(--bottom-nav-height) + var(--safe-bottom));
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
.player-minimize,
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

.app-player.is-buffering .player-toggle {
  cursor: progress;
}

.app-player.is-buffering .player-toggle::after {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.45);
  border-top-color: #fff;
  border-radius: 999px;
  content: "";
  animation: spin 800ms linear infinite;
}

.app-player.is-buffering .player-toggle {
  font-size: 0;
}

.player-queue-nav,
.player-speed,
.player-skip,
.player-minimize,
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
  width: auto;
  min-width: 58px;
  padding-inline: 10px;
}

.player-main {
  display: grid;
  min-width: 0;
  gap: 4px;
  min-height: 44px;
  padding: 4px 6px;
  border-radius: 14px;
  cursor: pointer;
}

.player-main:hover,
.player-main:focus {
  background: rgba(255, 255, 255, 0.58);
}

.app-player.is-expanded .player-main {
  cursor: default;
}

.app-player.is-expanded .player-main:hover,
.app-player.is-expanded .player-main:focus {
  background: transparent;
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

.player-minimize,
.player-artwork,
.player-description {
  display: none;
}

.app-player.is-expanded .player-minimize {
  display: inline-grid;
}

.app-player.is-expanded .player-artwork {
  display: block;
  width: min(240px, 62vw);
  aspect-ratio: 1;
  justify-self: center;
  border-radius: 28px;
  object-fit: cover;
  box-shadow: 0 18px 42px rgba(38, 26, 16, 0.22);
}

.app-player.is-expanded .player-description {
  display: block;
  max-height: 28vh;
  overflow: auto;
  margin: 6px 0 0;
  color: var(--muted);
  white-space: normal;
}

.player-seek {
  width: 100%;
  accent-color: var(--accent);
}

.player-time {
  white-space: nowrap;
}

@media (min-width: 721px) {
  .app-player.is-expanded {
    padding-inline-end: 116px;
  }

  .app-player.is-expanded .player-minimize,
  .app-player.is-expanded .player-close {
    position: absolute;
    inset-block-start: 10px;
    z-index: 2;
  }

  .app-player.is-expanded .player-close {
    inset-inline-end: 10px;
  }

  .app-player.is-expanded .player-minimize {
    inset-inline-end: 62px;
  }
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

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 900px) {
  .hero,
  .about-panel,
  .subscription-empty,
  .subscription-show,
  .onboard-shell {
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
    padding-block: var(--safe-top) calc(238px + var(--safe-bottom));
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

  .episode-actions {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }

  .episode-actions .button {
    min-width: 0;
    min-height: 44px;
    padding-inline: 10px;
    white-space: normal;
  }

  .episode-play {
    grid-column: 1 / -1;
  }

  .episode-links {
    grid-column: 1 / -1;
    justify-self: start;
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

  .onboard-shell {
    gap: 14px;
    margin-top: 14px;
  }

  .onboard-intro,
  .onboard-form {
    border-radius: 22px;
    padding: 16px;
  }

  .onboard-intro h1 {
    font-size: 31px;
  }

  .choices {
    grid-template-columns: 1fr;
  }

  .choice {
    min-height: auto;
  }

  .onboard-form button[type="submit"] {
    width: 100%;
  }

  .stat {
    width: 100%;
  }

  .dashboard-section {
    padding-top: 14px;
  }

  .dashboard-toolbar {
    margin-top: 12px;
  }

  .subscription-suggestions {
    grid-template-columns: 1fr;
  }

  .creator-panel {
    align-items: stretch;
    flex-direction: column;
  }

  .subscription-show {
    padding: 10px;
  }

  .app-bottom-nav {
    inset-inline: 10px;
    bottom: calc(8px + var(--safe-bottom));
    min-height: 68px;
    border-radius: 22px;
    padding: 6px;
  }

  .bottom-nav-item {
    border-radius: 17px;
    font-size: 12px;
  }

  .status-table {
    display: block;
    overflow-x: auto;
  }

  .resume-card {
    inset-inline: 10px;
    bottom: calc(22px + var(--bottom-nav-height) + var(--safe-bottom));
    align-items: stretch;
    flex-direction: column;
  }

  .app-drawer {
    inset-block: auto calc(84px + var(--safe-bottom));
    inset-inline: 10px;
    width: auto;
    max-height: min(68vh, 560px);
    border-radius: 24px 24px 20px 20px;
  }

  body.has-player .app-drawer {
    inset-block-end: calc(174px + var(--safe-bottom));
  }

  .resume-card .button {
    justify-content: center;
  }

  .app-player {
    inset-inline: 12px;
    bottom: calc(22px + var(--bottom-nav-height) + var(--safe-bottom));
    grid-template-columns: 48px minmax(0, 1fr) 40px 58px 40px 40px;
    gap: 8px;
    border-radius: 20px;
  }

  .app-player.is-expanded {
    inset: 0;
    bottom: auto;
    z-index: 45;
    max-width: none;
    margin: 0;
    border-radius: 0;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 12px;
    align-content: start;
    overflow: auto;
    padding: calc(18px + var(--safe-top)) 16px calc(96px + var(--safe-bottom));
  }

  .player-main {
    grid-column: 2 / 6;
    grid-row: 1;
  }

  .app-player.is-expanded .player-main {
    grid-column: 1 / -1;
    grid-row: 2;
    min-height: 0;
    padding: 6px;
    text-align: center;
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
  .player-minimize,
  .player-close {
    width: 40px;
    height: 40px;
  }

  .app-player.is-expanded .player-queue-nav,
  .app-player.is-expanded .player-speed,
  .app-player.is-expanded .player-skip,
  .app-player.is-expanded .player-minimize,
  .app-player.is-expanded .player-close {
    width: 100%;
    min-width: 0;
    height: 44px;
  }

  .app-player.is-expanded .player-toggle {
    grid-column: 1;
    grid-row: 4;
    width: 100%;
    height: 54px;
  }

  .app-player.is-expanded .player-time {
    grid-column: 1 / -1;
    grid-row: 3;
    justify-self: center;
  }

  .player-queue-nav[data-player-prev] {
    grid-column: 3;
    grid-row: 2;
  }

  .player-speed {
    grid-column: 4;
    grid-row: 2;
    width: auto;
    min-width: 58px;
    padding-inline: 4px;
  }

  .player-queue-nav[data-player-next] {
    grid-column: 5;
    grid-row: 2;
  }

  .player-skip[data-player-skip="-15"] {
    display: none;
  }

  .app-player.is-expanded .player-skip[data-player-skip="-15"] {
    display: inline-grid;
    grid-column: 1;
    grid-row: 5;
  }

  .player-skip[data-player-skip="30"] {
    grid-column: 6;
    grid-row: 2;
  }

  .app-player.is-expanded .player-skip[data-player-skip="30"] {
    grid-column: 5;
    grid-row: 4;
  }

  .player-close {
    grid-column: 6;
    grid-row: 1;
    z-index: 1;
  }

  .app-player.is-expanded .player-minimize {
    grid-column: 1;
    grid-row: 1;
    justify-self: start;
    width: 48px;
  }

  .app-player.is-expanded .player-close {
    grid-column: 5;
    grid-row: 1;
    justify-self: end;
    width: 48px;
  }

  .app-player.is-expanded .player-queue-nav[data-player-prev] {
    grid-column: 2;
    grid-row: 4;
  }

  .app-player.is-expanded .player-speed {
    grid-column: 3;
    grid-row: 4;
    padding-inline: 6px;
  }

  .app-player.is-expanded .player-queue-nav[data-player-next] {
    grid-column: 4;
    grid-row: 4;
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
    body = f"""
    <section class="section">
      <div class="onboard-shell">
        <aside class="onboard-intro">
          <h1 data-i18n="heading">צירוף פודקאסט</h1>
          <p data-i18n="intro">מלאו פרטים בסיסיים. Torah Pod יבדוק ויאשר לפני פרסום.</p>
          <ul class="onboard-steps" aria-label="Onboarding steps">
            <li>
              <span class="step-number">1</span>
              <span class="step-text" data-i18n="stepOne">בחרו מאיפה השיעורים מגיעים.</span>
            </li>
            <li>
              <span class="step-number">2</span>
              <span class="step-text" data-i18n="stepTwo">מלאו פרטי רב, קישור ותאריך התחלה.</span>
            </li>
            <li>
              <span class="step-number">3</span>
              <span class="step-text" data-i18n="stepThree">אחרי אישור, Torah Pod יוצר RSS פתוח להאזנה.</span>
            </li>
          </ul>
        </aside>

        <form id="onboarding-form" class="onboard-form" data-worker-endpoint="https://youtube-podcast-onboarding.shauldr.workers.dev">
          <div class="honeypot" aria-hidden="true">
            <label for="company-website">Website</label>
            <input id="company-website" name="company-website" tabindex="-1" autocomplete="off">
          </div>

          <fieldset>
            <legend data-i18n="sourceLegend">איפה נמצאים השיעורים?</legend>
            <div class="choices">
              <label class="choice">
                <span data-i18n="youtubeChoice">יוטיוב</span>
                <input id="source-youtube" type="radio" name="source" value="youtube" required>
              </label>
              <label class="choice">
                <span data-i18n="driveChoice">תיקיית Google Drive</span>
                <input id="source-drive" type="radio" name="source" value="drive">
              </label>
              <label class="choice">
                <span data-i18n="feedChoice">פיד פודקאסט קיים</span>
                <input id="source-feed" type="radio" name="source" value="feed">
              </label>
            </div>
            <div class="hint" data-i18n="sourceHint">בחרו מקור אחד כדי להמשיך. אחר כך יוצגו רק השדות הרלוונטיים.</div>
          </fieldset>

          <div id="youtube-fields" class="hidden">
            <label for="youtube-url" data-i18n="youtubeUrlLabel">קישור ליוטיוב</label>
            <input id="youtube-url" name="youtube-url" inputmode="url" placeholder="https://www.youtube.com/@channel">
            <div class="hint" data-i18n="youtubeUrlHint">אפשר להדביק ערוץ או פלייליסט.</div>
          </div>

          <div id="drive-fields" class="hidden">
            <label for="drive-url" data-i18n="driveUrlLabel">קישור לתיקיית Google Drive</label>
            <input id="drive-url" name="drive-url" inputmode="url" placeholder="https://drive.google.com/drive/folders/...">
            <div class="source-note">
              <p data-i18n="shareFolder">שתפו את התיקייה עם החשבון הזה כ-Viewer:</p>
              <span class="service-account">podcast-sync@torah-pod-podcast-sync.iam.gserviceaccount.com</span>
              <p class="hint" data-i18n="fileNameHint">קובץ מוכן לפרסום: YYYY-MM-DD - Episode Title.ext</p>
            </div>
          </div>

          <div id="feed-fields" class="hidden">
            <label for="feed-url" data-i18n="feedUrlLabel">קישור לפיד פודקאסט קיים</label>
            <input id="feed-url" name="feed-url" inputmode="url" placeholder="https://example.com/feed.xml">
            <div class="hint" data-i18n="feedUrlHint">אפשר להדביק RSS או Atom. Torah Pod ייקח מהפיד את שם הפודקאסט, הקישור, התיאור, הרב/מחבר, התמונה והפרקים.</div>
          </div>

          <div id="title-fields" class="hidden">
            <label for="title" data-i18n="titleLabel">שם הפודקאסט (לא חובה)</label>
            <input id="title" name="title" dir="auto">
            <div class="hint" data-i18n="titleHint">אם נשאר ריק, נשתמש בשם הרב.</div>
          </div>

          <div id="speaker-fields" class="hidden">
            <label for="speaker" data-i18n="speakerLabel">שם הרב / מוסר השיעור</label>
            <input id="speaker" name="speaker" dir="auto">
          </div>

          <div id="slug-fields" class="hidden">
            <label for="slug" data-i18n="slugLabel">שם קצר לקישור באנגלית</label>
            <input id="slug" name="slug" dir="ltr" inputmode="text" placeholder="rav-shalom-deitsch" pattern="[a-z0-9]+(-[a-z0-9]+)*">
            <div class="hint" data-i18n="slugHint">אותיות באנגלית, מספרים ומקפים בלבד. זה יהיה חלק מקישור הפיד.</div>
          </div>

          <div id="start-date-fields" class="hidden">
            <label for="start-date" data-i18n="startDateLabel">תאריך התחלה</label>
            <input id="start-date" name="start-date" type="date">
            <div class="hint" data-i18n="startDateHint">רק שיעורים מהתאריך הזה והלאה ייכנסו לפודקאסט.</div>
          </div>

          <div id="description-fields" class="hidden">
            <label for="description" data-i18n="descriptionLabel">תיאור (לא חובה)</label>
            <textarea id="description" name="description" dir="auto"></textarea>
            <div class="hint" data-i18n="descriptionHint">ביוטיוב אפשר להשאיר ריק, ו-Torah Pod יוכל להשתמש בתיאור הערוץ.</div>
          </div>

          <div id="artwork-fields" class="hidden">
            <label for="artwork" data-i18n="artworkLabel">קישור לתמונת הפודקאסט (לא חובה)</label>
            <input id="artwork" name="artwork" inputmode="url">
          </div>

          <div id="contact-fields" class="hidden">
            <label for="contact" data-i18n="contactLabel">כתובת אימייל שלכם (לא חובה)</label>
            <input id="contact" name="contact" type="email">
          </div>

          <div id="notes-fields" class="hidden">
            <label for="notes" data-i18n="notesLabel">הערות נוספות (לא חובה)</label>
            <textarea id="notes" name="notes" dir="auto"></textarea>
          </div>

          <label id="approval-fields" class="check hidden">
            <span data-i18n="approvalLabel">אני מבין/ה שצריך אישור של Torah Pod לפני יצירת הפודקאסט.</span>
            <input id="approval" type="checkbox">
          </label>

          <button id="submit-button" class="button primary hidden" type="submit" data-i18n="submitButton">שלחו בקשה</button>
          <p id="status" class="status" role="status"></p>
        </form>
      </div>
    </section>
"""
    _write_text(onboard_dir / "index.html", _page("Onboard", body, site_config=site_config, relative_prefix="../"))


def _build_about_page(site_config: SiteConfig, *, show_count: int, episode_count: int) -> None:
    about_dir = PUBLIC_DIR / "about"
    about_dir.mkdir(parents=True, exist_ok=True)
    donation_button = _donation_link(site_config, "../", class_name="button")
    body = f"""
    <section class="section hero page-hero">
      <div class="hero-copy">
        <p class="kicker" data-i18n="about">{HE["about"]}</p>
        <h1>{BRAND}</h1>
        <p data-i18n="about_text">{HE["about_text"]}</p>
      </div>
    </section>
    <section class="section">
      <div class="about-panel">
        <div>
          <h2 data-i18n="how_it_works">{HE["how_it_works"]}</h2>
          <p data-i18n="how_it_works_text">{HE["how_it_works_text"]}</p>
        </div>
        <div class="about-note">
          <span data-i18n="source_mix">{HE["source_mix"]}</span>
          <div class="stats">
            <div class="stat"><strong>{show_count}</strong><span data-i18n="total_shows">{HE["total_shows"]}</span></div>
            <div class="stat"><strong>{episode_count}</strong><span data-i18n="total_episodes">{HE["total_episodes"]}</span></div>
          </div>
        </div>
      </div>
      <div class="creator-panel">
        <div>
          <h2 data-i18n="onboard">{HE["onboard"]}</h2>
          <p data-i18n="hero_kicker">{HE["hero_kicker"]}</p>
        </div>
        <div class="hero-actions">
          <a class="button primary" href="../onboard/" data-app-route="/onboard/" data-i18n="onboard">{HE["onboard"]}</a>
          {donation_button}
        </div>
      </div>
    </section>
"""
    _write_text(about_dir / "index.html", _page("About", body, site_config=site_config, relative_prefix="../"))


def _write_linked_feed_redirects(shows: list[ShowConfig]) -> None:
    redirects = [
        f"/{show.slug}/feed.xml {public_feed_url(show)} 302"
        for show in shows
        if is_linked_existing_feed_show(show)
    ]
    redirects.extend(
        [
            "/lvmdym-chsydvt-19/feed.xml https://feeds.captivate.fm/lomdimchassidut/ 302",
            "/lvmdym-chsydvt-19/ /lvmdym-chsydvt/ 301",
            "/lvmdym-chsydvt-19/* /lvmdym-chsydvt/:splat 301",
            "/status/ / 302",
            "/status/* / 302",
        ]
    )
    redirects_path = PUBLIC_DIR / "_redirects"
    if redirects:
        _write_text(redirects_path, "\n".join(redirects) + "\n")
    elif redirects_path.exists():
        redirects_path.unlink()


def _episode_published_date(episode: dict[str, Any]) -> date | None:
    try:
        return datetime.strptime(str(episode.get("published") or ""), "%Y%m%d").date()
    except ValueError:
        return None


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
                "filter_value": _show_hosting_key(show),
            }
            for show in shows
            for episode in show_episodes[show.slug]
        ),
        key=lambda episode: episode.get("published") or "",
        reverse=True,
    )

    cards = "\n".join(_show_card(show, show_episodes[show.slug]) for show in shows)
    latest = "\n".join(_episode_item(episode) for episode in all_episodes[:12])
    subscription_blocks = "\n".join(_subscription_show_block(show, show_episodes[show.slug]) for show in shows)
    suggested_cards = "\n".join(_show_card(show, show_episodes[show.slug]) for show in shows[:6])
    latest_dates = [published for episode in all_episodes if (published := _episode_published_date(episode))]
    library_recent_cutoff = (max(latest_dates) - timedelta(days=2)) if latest_dates else None
    library_recent_episodes = [
        episode
        for episode in all_episodes
        if library_recent_cutoff and (published := _episode_published_date(episode)) and published >= library_recent_cutoff
    ][:24]
    library_recent = "\n".join(
        _episode_item(episode, id_suffix="-library-recent").replace(
            'class="episode"',
            'class="episode" data-library-recent-episode',
            1,
        )
        for episode in library_recent_episodes
    )
    total_episodes = sum(len(episodes) for episodes in show_episodes.values())
    index_body = f"""
    <section class="section dashboard-section" id="subscriptions" data-subscriptions-section>
      <div class="toolbar dashboard-toolbar">
        <div>
          <p class="kicker" data-i18n="subscriptions_recent">{HE["subscriptions_recent"]}</p>
          <h1 data-i18n="subscriptions">{HE["subscriptions"]}</h1>
          <p class="muted" data-i18n="subscriptions_empty_text">{HE["subscriptions_empty_text"]}</p>
        </div>
      </div>
      <div class="subscription-empty" data-subscriptions-empty>
        <div class="empty-library-card">
          <h2 data-i18n="subscriptions_empty_title">{HE["subscriptions_empty_title"]}</h2>
          <p data-i18n="subscriptions_empty_text">{HE["subscriptions_empty_text"]}</p>
        </div>
        <div>
          <h2 class="section-subtitle" data-i18n="suggested_subscriptions">{HE["suggested_subscriptions"]}</h2>
          <div class="grid subscription-suggestions">
{suggested_cards}
          </div>
        </div>
      </div>
      <div class="subscription-active" data-subscriptions-active hidden>
        <div class="library-recent-block" data-library-recent-block hidden>
          <h2 class="section-subtitle" data-i18n="recent_from_library">{HE["recent_from_library"]}</h2>
          <div class="episode-list compact-episode-list library-recent-list">
{library_recent or f'<p class="muted" data-i18n="no_subscription_episodes">{HE["no_subscription_episodes"]}</p>'}
          </div>
        </div>
        <h2 class="section-subtitle" data-i18n="all_subscriptions">{HE["all_subscriptions"]}</h2>
        <div class="subscription-show-list" data-subscription-shows>
{subscription_blocks}
        </div>
        <p class="muted" data-subscriptions-none hidden data-i18n="no_subscription_episodes">{HE["no_subscription_episodes"]}</p>
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
        <div class="toolbar-controls" data-list-controls="latest-episode-list">
          <div class="search-field">
            <label for="latest-episode-search" data-i18n="search_episodes">{HE["search_episodes"]}</label>
            <input id="latest-episode-search" class="search" type="search" data-search-target="latest-episode-list" data-i18n-placeholder="search_episodes_placeholder" placeholder="{_escape(HE['search_episodes_placeholder'])}">
          </div>
          <div class="filter-group" role="group" aria-label="{HE["filter_group"]}">
            <button class="button filter-toggle" type="button" data-filter-toggle="latest-episode-list" aria-pressed="false" data-i18n="filter_hosted_toggle">{HE["filter_hosted_toggle"]}</button>
            <button class="button filter-toggle" type="button" data-library-filter-toggle="latest-episode-list" aria-pressed="false" data-i18n="filter_library_toggle">{HE["filter_library_toggle"]}</button>
          </div>
        </div>
      </div>
      <div id="latest-episode-list" class="episode-list" data-list data-page-size="12">
{latest or f'<p class="muted" data-i18n="empty">{HE["empty"]}</p>'}
      </div>
      <div class="load-more-row">
        <button class="button" type="button" data-load-more="latest-episode-list" data-i18n="show_more">{HE["show_more"]}</button>
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
                    "filter_value": _show_hosting_key(show),
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
    _build_about_page(site_config, show_count=len(shows), episode_count=total_episodes)
    _build_donation_page(site_config)
    _build_contact_page(site_config)
    _write_linked_feed_redirects(shows)
    print(f"{PUBLIC_DIR / 'index.html'} written with {len(shows)} show(s)")
