from __future__ import annotations

import html
import hashlib
import json
import os
import re
import shutil
from functools import lru_cache
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
from .episode_metadata import legacy_snapshot, read_snapshot, snapshot_path, validated_episodes, write_episode_pages, write_snapshot
from .existing_feed import ExistingFeedItem, list_existing_feed_items

BRAND = "Torah Pod"
BRAND_HE = "תורה־פּוֹד"
BRAND_HE_SEARCH = "תורה-פוד"
SITE_ORIGIN = "https://torah-pod.pages.dev"
SITE_BUILD_ID = (os.environ.get("GITHUB_SHA") or "local")[:7]
CATALOG_SCHEMA_VERSION = 1
SEARCH_INDEX_SCHEMA_VERSION = 1
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


def _catalog_metadata() -> dict[str, Any]:
    """Describe the stable catalog contract without changing its array shape."""
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "catalog_url": "catalog.json",
        "top_level": "array",
        "item_identity": "slug",
        "fields": {
            "slug": {"type": "string", "required": True},
            "title": {"type": "string", "required": True},
            "author": {"type": "string", "required": True},
            "description": {"type": "string", "required": True},
            "feed_url": {"type": "https-url", "required": True},
            "artwork_url": {"type": "https-url", "required": True},
            "platforms": {
                "type": "object",
                "required": True,
                "additional_properties": "https-url",
            },
            "episode_count": {
                "type": "integer",
                "required": True,
                "minimum": 0,
            },
            "latest_episode_date": {"type": "date-string", "required": True},
            "episode_dates": {"type": "array", "items": "date-string", "required": True},
        },
        "client_cache": {
            "conditional_requests": ["ETag", "Last-Modified"],
            "keep_last_valid_response_on_error": True,
        },
    }


HE = {
    "brand_name": BRAND_HE,
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
    "copy_feed": "העתקת קישור RSS",
    "feed_copied": "קישור ה-RSS הועתק.",
    "copy_feed_failed": "לא ניתן להעתיק את הקישור. אפשר לפתוח את RSS ולהעתיק משם.",
    "account": "חשבון",
    "manage_account": "ניהול פודקאסטים",
    "sign_in": "כניסה",
    "your_account": "החשבון שלך",
    "sync_listening": "סנכרון ההאזנה שלך",
    "onboard": "צירוף פודקאסט",
    "onboarding_steps": "שלבי צירוף פודקאסט",
    "status": "סטטוס",
    "contact": "יצירת קשר",
    "contact_title": "יצירת קשר",
    "contact_text": "יש שאלה, הצעה או בקשה לצירוף פודקאסט? אפשר לכתוב ישירות ל-תורה־פּוֹד.",
    "contact_name": "שם",
    "contact_email": "אימייל",
    "contact_message": "הודעה",
    "contact_submit": "פתיחת אימייל",
    "terms": "תנאים וזכויות",
    "terms_title": "תנאים, זכויות ופרטיות",
    "terms_code_title": "קוד, עיצוב והמותג",
    "terms_code_text": "הקוד, העיצוב ושם המותג של תורה־פּוֹד מוגנים בזכויות. אין הרשאה להעתיק, לשנות, להפיץ, לארח או להשתמש בהם מסחרית ללא אישור בכתב. גרסאות ישנות שפורסמו תחת MIT נשארות כפופות לרישיון MIT שלהן.",
    "terms_content_title": "הקלטות ותוכן",
    "terms_content_text": "תורה־פּוֹד אינו טוען לבעלות על הקלטות, תמונות, סימני מסחר או תוכן של צדדים שלישיים. הזכויות נשארות בידי בעלי הזכויות המתאימים, ואין כאן הענקת רישיון לשימוש חוזר בתוכן זה.",
    "terms_removal_title": "פנייה לגבי זכויות",
    "terms_removal_text": "בעל/ת זכויות שרוצה לתקן מידע או לבקש הסרה יכול/ה לפנות אלינו באימייל. נבדוק את הפנייה ונפעל לפי הצורך.",
    "terms_privacy_title": "פרטיות",
    "terms_privacy_text": "האתר שומר בדפדפן הגדרות שפה והאזנה כדי לשפר את השימוש. בקשות לצירוף פודקאסט, כולל פרטי יצירת קשר שנמסרו מרצון, נשלחות למערכת פרטית לצורך בדיקה ומענה. טופס הצירוף משתמש באימות אבטחה של Cloudflare Turnstile. האתר משתמש ב-Cloudflare Web Analytics למדידה מצרפית של צפיות וביצועי האתר. אין שימוש בפרסום מותאם אישית. חשבון Google אופציונלי מסנכרן מינויים, פרקים שמורים והתקדמות האזנה. נתוני החשבון פרטיים. אפשר למחוק את החשבון דרך תפריט החשבון, לאחר אישור. מחיקה מסירה את החשבון ונתוני ההאזנה; פודקאסטים שפורסמו נשארים זמינים ורישומי הרשאות לפרסום עשויים להישמר בנפרד.",
    "donate": "תרומה",
    "donate_title": "תמיכה ב-תורה־פּוֹד",
    "donate_text": "אם המיזם מועיל לך, אפשר להשתתף בהחזקת המערכת דרך Bit או PayBox.",
    "episodes": "פרקים",
    "source": "מקור",
    "search": "חיפוש",
    "search_placeholder": "חפשו שיעור או רב",
    "search_podcasts": "חיפוש פודקאסטים",
    "search_podcasts_placeholder": "חפשו לפי שם פודקאסט או רב",
    "filter_hosted_toggle": "תורה־פּוֹד",
    "filter_library_toggle": "הספרייה שלי",
    "filter_group": "סינון פודקאסטים",
    "search_episodes": "חיפוש פרקים",
    "search_episodes_placeholder": "חפשו לפי שם שיעור או תיאור",
    "show_more": "הצג עוד",
    "no_search_results": "לא נמצאו תוצאות. נסו חיפוש אחר.",
    "empty": "עדיין אין פרקים להצגה.",
    "intro": "שיעורי תורה להאזנה מכל מקום.",
    "hero_kicker": "בית פתוח לפודקאסטים של שיעורי תורה",
    "hero_cta_primary": "האזנה לפרקים",
    "hero_cta_secondary": "צירוף פודקאסט",
    "about": "על תורה־פּוֹד",
    "about_text": "תורה־פּוֹד מרכז שיעורי תורה ופודקאסטים במקום אחד, עם ספרייה אישית, תור האזנה ו-RSS פתוח לאפליקציות פודקאסטים.",
    "how_it_works": "מה אפשר לעשות כאן",
    "how_it_works_text": "עקבו אחרי פודקאסטים, ראו פרקים חדשים מהספרייה שלכם, הוסיפו פרקים לתור והמשיכו להאזין מכל מכשיר.",
    "source_mix": "מאזינים חופשי, בלי חשבון",
    "latest_episode": "פרק אחרון",
    "total_shows": "פודקאסטים",
    "total_episodes": "פרקים",
    "language": "English",
    "primary_navigation": "ניווט ראשי",
    "app_navigation": "ניווט אפליקציה",
    "updated_at": "עודכן",
    "hosted_by_torahpod": "מאוחסן ב-תורה־פּוֹד",
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
    "reorder_queue": "גרירה לשינוי סדר",
    "clear_queue": "ניקוי התור",
    "queue_empty": "התור שלך ריק. הוסיפו פרק כדי להתחיל.",
    "confirm_clear_queue": "לנקות את כל תור ההאזנה?",
    "now_playing": "מתנגן עכשיו",
    "remove_from_library": "הסרה מהספרייה",
    "mark_played": "סמן כנשמע",
    "mark_unplayed": "סמן כלא נשמע",
    "played": "נשמע",
    "share": "שיתוף",
    "share_copied": "הקישור לפרק הועתק.",
    "share_failed": "לא ניתן לשתף את הקישור כרגע.",
    "player_close": "סגירה",
    "player_stop": "עצירת הניגון",
    "player_minimize": "מזעור",
    "pause": "עצירה",
    "playback_speed": "מהירות",
    "previous_queue": "הקודם בתור",
    "next_queue": "הבא בתור",
    "skip_back": "חזרה 15 שניות",
    "skip_forward": "קדימה 30 שניות",
    "skip_to_content": "דילוג לתוכן הראשי",
    "player_details": "פתיחת פרטי הניגון",
    "player_progress": "מיקום בניגון",
    "volume": "עוצמת שמע",
    "audio_player": "נגן שמע",
    "network_offline": "אין חיבור. דפים שמורים עשויים לעבוד; השמע דורש חיבור לרשת.",
    "network_online": "החיבור חזר",
    "navigation_loading": "העמוד נטען",
    "navigation_failed": "לא ניתן לפתוח את העמוד. בדקו את החיבור ונסו שוב.",
    "navigation_retry": "נסו שוב",
    "playback_failed": "לא ניתן לנגן את הפרק. בדקו את החיבור ונסו שוב.",
    "playback_offline": "אין חיבור לרשת. הפרק וההתקדמות נשמרו; נסו שוב כשהחיבור יחזור.",
    "playback_stalled": "טעינת הפרק נמשכת זמן רב מהרגיל. אפשר לנסות שוב בלי לאבד את ההתקדמות.",
    "playback_retry": "ניסיון נוסף",
    "diagnostics_title": "פתרון תקלות",
    "diagnostics_text": "אם ההאזנה לא עובדת כמצופה, העתיקו פרטי אבחון בטוחים ושלחו אותם אלינו.",
    "copy_diagnostics": "העתקת פרטי אבחון",
    "diagnostics_copied": "פרטי האבחון הועתקו.",
    "diagnostics_failed": "לא ניתן להעתיק את פרטי האבחון כרגע.",
    "nav_menu": "תפריט נוסף",
    "new_from_subscriptions": "חדש מהפודקאסטים שלכם",
    "up_next": "הבא בתור",
    "your_subscriptions": "הפודקאסטים שלכם",
    "see_all": "הצגת הכל",
    "subscription_filter": "חיפוש בפודקאסטים שלכם",
    "sort_recent": "עודכנו לאחרונה",
    "sort_alpha": "לפי א-ב",
    "new_episodes": "פרקים חדשים",
    "search_catalog": "חיפוש בכל תורה־פּוֹד",
    "search_catalog_placeholder": "חפשו פודקאסט, רב או פרק",
    "search_start": "הקלידו לפחות שני תווים כדי לחפש בכל הפרקים.",
    "search_loading": "טוען את מאגר החיפוש…",
    "search_failed": "לא ניתן לטעון את החיפוש כרגע. בדקו את החיבור ונסו שוב.",
    "podcast_results": "פודקאסטים",
    "episode_results": "פרקים",
    "no_queue_preview": "התור שלכם ריק. הוסיפו פרק כדי להמשיך להאזין ברצף.",
    "open_queue": "פתיחת התור",
    "full_player": "נגן מורחב",
    "close_full_player": "סגירת הנגן המורחב",
    "update_ready": "גרסה חדשה מוכנה.",
    "update_now": "רענון עכשיו",
    "saved_progress": "נשמר",
}
EN = {
    "brand_name": BRAND,
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
    "copy_feed": "Copy RSS Link",
    "feed_copied": "RSS link copied.",
    "copy_feed_failed": "Could not copy the link. Open RSS to copy it instead.",
    "account": "Account",
    "manage_account": "Manage podcasts",
    "sign_in": "Sign in",
    "your_account": "Your account",
    "sync_listening": "Sync your listening",
    "onboard": "Add a Podcast",
    "onboarding_steps": "Podcast onboarding steps",
    "status": "Status",
    "contact": "Contact",
    "contact_title": "Contact",
    "contact_text": "Questions, suggestions, or podcast requests can be sent directly to Torah Pod.",
    "contact_name": "Name",
    "contact_email": "Email",
    "contact_message": "Message",
    "contact_submit": "Open Email",
    "terms": "Terms & Rights",
    "terms_title": "Terms, Rights & Privacy",
    "terms_code_title": "Code, design, and brand",
    "terms_code_text": "Torah Pod's code, design, and brand name are protected. No permission is granted to copy, modify, redistribute, host, or use them commercially without written permission. Earlier releases published under MIT remain subject to their MIT license.",
    "terms_content_title": "Recordings and content",
    "terms_content_text": "Torah Pod does not claim ownership of third-party recordings, artwork, trademarks, or other content. Those rights remain with their respective rights holders, and this site does not grant a license to reuse that content.",
    "terms_removal_title": "Rights requests",
    "terms_removal_text": "A rights holder can email us to correct information or request removal. We will review the request and act as appropriate.",
    "terms_privacy_title": "Privacy",
    "terms_privacy_text": "The site stores language and listening preferences in the browser to support use of the service. Podcast onboarding requests, including voluntarily supplied contact details, are sent to a private review system so they can be reviewed and answered. The onboarding form uses Cloudflare Turnstile for security verification. The site uses Cloudflare Web Analytics for aggregate page-view and performance measurement. The site does not use personalized advertising. Optional Google accounts synchronize follows, saved episodes and listening progress. Account data is private. Delete your account from the account menu after confirming. Deletion removes account access and listening data; published podcasts remain available, and private publication-rights records may be retained separately.",
    "donate": "Donate",
    "donate_title": "Support Torah Pod",
    "donate_text": "If this project is useful to you, you can help support the platform through Bit or PayBox.",
    "episodes": "Episodes",
    "source": "Source",
    "search": "Search",
    "search_placeholder": "Search lessons or speakers",
    "search_podcasts": "Search Podcasts",
    "search_podcasts_placeholder": "Search by podcast name or rabbi",
    "filter_hosted_toggle": "Torah Pod",
    "filter_library_toggle": "My Library",
    "filter_group": "Podcast filters",
    "search_episodes": "Search Episodes",
    "search_episodes_placeholder": "Search by lesson title or description",
    "show_more": "Show More",
    "no_search_results": "No results found. Try another search.",
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
    "primary_navigation": "Primary navigation",
    "app_navigation": "App navigation",
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
    "reorder_queue": "Drag to reorder",
    "clear_queue": "Clear Queue",
    "queue_empty": "Your queue is empty. Add an episode to get started.",
    "confirm_clear_queue": "Clear the entire listening queue?",
    "now_playing": "Now Playing",
    "remove_from_library": "Remove from Library",
    "mark_played": "Mark Played",
    "mark_unplayed": "Mark Unplayed",
    "played": "Played",
    "share": "Share",
    "share_copied": "Episode link copied.",
    "share_failed": "Could not share the link right now.",
    "player_close": "Close",
    "player_stop": "Stop playback",
    "player_minimize": "Minimize",
    "pause": "Pause",
    "playback_speed": "Speed",
    "previous_queue": "Previous in Queue",
    "next_queue": "Next in Queue",
    "skip_back": "Back 15 seconds",
    "skip_forward": "Forward 30 seconds",
    "skip_to_content": "Skip to main content",
    "player_details": "Open playback details",
    "player_progress": "Playback position",
    "volume": "Volume",
    "audio_player": "Audio player",
    "network_offline": "You are offline. Saved pages may still work; audio needs a connection.",
    "network_online": "Back online",
    "navigation_loading": "Loading page",
    "navigation_failed": "Could not open the page. Check your connection and try again.",
    "navigation_retry": "Try again",
    "playback_failed": "Could not play this episode. Check your connection and try again.",
    "playback_offline": "You are offline. The episode and progress are preserved; try again when your connection returns.",
    "playback_stalled": "This episode is taking longer than usual to start. You can retry without losing progress.",
    "playback_retry": "Retry playback",
    "diagnostics_title": "Troubleshooting",
    "diagnostics_text": "If playback is not working as expected, copy safe diagnostics and send them to us.",
    "copy_diagnostics": "Copy diagnostics",
    "diagnostics_copied": "Diagnostics copied.",
    "diagnostics_failed": "Could not copy diagnostics right now.",
    "nav_menu": "More menu",
    "new_from_subscriptions": "New from your subscriptions",
    "up_next": "Up Next",
    "your_subscriptions": "Your subscriptions",
    "see_all": "See all",
    "subscription_filter": "Search your subscriptions",
    "sort_recent": "Recently updated",
    "sort_alpha": "Alphabetical",
    "new_episodes": "new episodes",
    "search_catalog": "Search all Torah Pod",
    "search_catalog_placeholder": "Search podcasts, speakers, or episodes",
    "search_start": "Enter at least two characters to search every episode.",
    "search_loading": "Loading the search catalog…",
    "search_failed": "Search could not be loaded. Check your connection and try again.",
    "podcast_results": "Podcasts",
    "episode_results": "Episodes",
    "no_queue_preview": "Your queue is empty. Add an episode to keep listening continuously.",
    "open_queue": "Open queue",
    "full_player": "Full player",
    "close_full_player": "Close full player",
    "update_ready": "A new version is ready.",
    "update_now": "Refresh now",
    "saved_progress": "Saved",
}



HE.update({"library": "הספרייה שלי", "recent_catalog": "הפרקים החדשים", "home_welcome": "פודקאסטים ושיעורי תורה להאזנה", "home_subtitle": "בחרו פרק והתחילו להקשיב.", "play_latest": "הפרק האחרון", "show_details": "על הפודקאסט וקישורים", "saved": "שמורים", "history": "היסטוריה", "save_episode": "שמירת פרק", "unsave_episode": "הסרה מהשמורים", "theme": "ערכת צבעים", "theme_system": "לפי המכשיר", "theme_light": "בהירה", "theme_dark": "כהה", "loading_episodes": "טוען פרקים…", "episodes_failed": "לא ניתן לטעון עוד פרקים. נסו שוב.", "library_empty": "הפרקים שלכם יופיעו כאן אחרי שתשמרו או תאזינו.", "follow_invite": "עקבו אחרי פודקאסטים כדי לראות כאן את הפרקים החדשים שלהם."})
EN.update({"library": "Library", "recent_catalog": "Recent episodes", "home_welcome": "Torah podcasts and audio lessons", "home_subtitle": "Choose an episode and settle in.", "play_latest": "Play Latest", "show_details": "About this show & links", "saved": "Saved", "history": "History", "save_episode": "Save episode", "unsave_episode": "Remove from saved", "theme": "Appearance", "theme_system": "Device default", "theme_light": "Light", "theme_dark": "Dark", "loading_episodes": "Loading episodes…", "episodes_failed": "Could not load more episodes. Try again.", "library_empty": "Episodes appear here when you save or listen to them.", "follow_invite": "Follow shows to see their newest episodes here."})
HE.update({"mute": "השתקה", "unmute": "ביטול השתקה", "muted": "מושתק", "episode_page": "עמוד הפרק", "device_volume": "עוצמת השמע נשלטת באמצעות כפתורי המכשיר"})
EN.update({"mute": "Mute", "unmute": "Unmute", "muted": "Muted", "episode_page": "Episode page", "device_volume": "Use your device buttons to adjust volume"})
HE.update({"explore": "כל הפודקאסטים", "explore_title": "כל הפודקאסטים", "explore_subtitle": "מצאו שיעורים וקולות שתרצו לחזור אליהם.", "explore_filter": "חיפוש פודקאסט או רב", "sort": "סדר"})
EN.update({"explore": "Explore", "explore_title": "All podcasts", "explore_subtitle": "Find shows and voices worth coming back to.", "explore_filter": "Find a podcast or speaker", "sort": "Sort"})

def _escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _search_text(*values: Any) -> str:
    return _escape(" ".join(" ".join(str(value or "").split()) for value in values if value))


def _search_excerpt(value: Any, limit: int = 600) -> str:
    text = _plain_text(value)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0]


def _plain_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def _write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(re.sub(r"(?m)^[ \t]+$", "", content))


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


def _episode_page_path(show_slug: str, episode: dict[str, Any]) -> str:
    """Return the stable, public route for an episode detail page."""
    return f"{show_slug}/episodes/{_episode_dom_id({**episode, 'show_slug': show_slug})}/"


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
    linked_sources = [source for source in show.sources if is_linked_existing_feed_source(source) and source.feed_url]
    for source in linked_sources:
        cached_path = snapshot_path(PUBLIC_DIR, show.slug, source.feed_url)
        previous = read_snapshot(cached_path)
        if previous is None and len(linked_sources) == 1:
            previous = legacy_snapshot(PUBLIC_DIR, show.slug)
        try:
            if os.environ.get("TORAH_POD_OFFLINE_BUILD") == "1":
                if previous is None or not previous:
                    raise ValueError("No previous metadata available for offline build")
                items = previous
            else:
                items = [_linked_feed_episode(item) for item in list_existing_feed_items(source.feed_url, source.scan_limit_per_tab)]
                items = validated_episodes(items)
                if not items and previous:
                    raise ValueError("Refresh unexpectedly returned no playable episodes")
            filtered = [item for item in items if not item.get("published") or datetime.strptime(item["published"], "%Y%m%d").date() >= source.start_date]
            episodes.extend(write_snapshot(cached_path, filtered))
        except Exception as exc:
            print(f"{show.slug}: linked refresh failed; retaining previous validated metadata ({type(exc).__name__})")
            episodes.extend(previous or [])
    unique = {}
    for episode in episodes:
        unique.setdefault(_episode_identity({**episode, "show_slug": show.slug}), episode)
    return sorted(unique.values(), key=lambda episode: (str(episode.get("published") or ""), _episode_identity({**episode, "show_slug": show.slug})), reverse=True)


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


def _nav_icon(name: str) -> str:
    paths = {
        "home": '<path d="M3 10.5 12 3l9 7.5v9a1.5 1.5 0 0 1-1.5 1.5H15v-6H9v6H4.5A1.5 1.5 0 0 1 3 19.5Z"/>',
        "subscriptions": '<rect x="4" y="5" width="16" height="14" rx="3"/><path d="M8 2h8M8 22h8"/>',
        "search": '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 5 5"/>',
        "explore": '<circle cx="12" cy="12" r="9"/><path d="m16 8-3 5-5 3 3-5Z"/>',
        "queue": '<path d="M5 6h14M5 12h10M5 18h7"/><path d="m17 15 4 3-4 3Z"/>',
    }
    return f'<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">{paths[name]}</svg>'


def _ui_icon(name: str) -> str:
    paths = {
        "play": '<path d="m9 7 9 5-9 5Z" fill="currentColor" stroke="none"/>',
        "previous": '<path d="M7 6v12M18 7l-8 5 8 5Z"/>',
        "next": '<path d="M17 6v12M6 7l8 5-8 5Z"/>',
        "back15": '<path d="M5.4 8A8 8 0 1 1 4 14.5M5 4v4h4"/><text x="12" y="15.5">15</text>',
        "forward30": '<path d="M18.6 8A8 8 0 1 0 20 14.5M19 4v4h-4"/><text x="12" y="15.5">30</text>',
        "queue": '<path d="M5 7h10M5 12h10M5 17h7"/><path d="m16 15 4 2.5-4 2.5Z"/>',
        "stop": '<rect x="8" y="8" width="8" height="8" rx="1" fill="currentColor" stroke="none"/>',
        "more": '<circle cx="5" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1" fill="currentColor" stroke="none"/>',
        "account": '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
        "volume": '<path d="M11 4 6 8H3v8h3l5 4Z"/><path d="M15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14"/>',
        "muted": '<path d="M11 4 6 8H3v8h3l5 4Z"/><path d="m16 9 6 6m0-6-6 6"/>',
        "down": '<path d="m7 10 5 5 5-5"/>',
        "close": '<path d="m7 7 10 10M17 7 7 17"/>',
    }
    return f'<svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">{paths[name]}</svg>'


@lru_cache(maxsize=1)
def _asset_version() -> str:
    digest = hashlib.sha256(Path(__file__).read_bytes())
    for path in sorted((ROOT / "podcast_feeds" / "web").glob("*")):
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _page(title: str, body: str, *, site_config: SiteConfig, relative_prefix: str = "", is_home: bool = False) -> str:
    css = f"{relative_prefix}assets/site.css?v={_asset_version()}"
    app_js = f"{relative_prefix}assets/app.js?v={_asset_version()}"
    manifest = f"{relative_prefix}manifest.webmanifest"
    home = f"{relative_prefix}index.html"
    onboard = f"{relative_prefix}onboard/"
    about = f"{relative_prefix}about/"
    about_contact = f"{relative_prefix}about/#contact"
    terms = f"{relative_prefix}terms/"
    subscriptions = f"{relative_prefix}subscriptions/"
    search = f"{relative_prefix}search/"
    explore = f"{relative_prefix}explore/"
    queue = f"{relative_prefix}queue/"
    donation_nav = _donation_link(site_config, relative_prefix)
    account_config = _account_configuration()
    account_enabled = account_config["listenerAccounts"] or account_config["publisherAccess"]
    account_label = "sign_in" if account_enabled else "account"
    account_guest_state = ' data-signed-out="true"' if account_enabled else ""
    account_signin = f'<span data-account-signin data-i18n="sign_in">{HE["sign_in"]}</span>' if account_enabled else ""
    account_management = (
        f'<a class="account-menu-link" href="{relative_prefix}account/" data-app-route="/account/">'
        f'{_ui_icon("account")}<span data-i18n="manage_account">{HE["manage_account"]}</span></a>'
        if account_config["publisherAccess"] else ""
    )
    page_title = f'{HE["home_welcome"]} | {BRAND_HE_SEARCH} | {BRAND}' if is_home else f'{title} | {BRAND_HE_SEARCH} | {BRAND}'
    search_metadata = '<meta data-site-search-meta property="og:site_name" content="' + _escape(BRAND_HE) + '">'
    if account_config["environment"] == "preview":
        search_metadata += '\n  <meta data-site-search-meta name="robots" content="noindex">'
    if is_home:
        description = f"{BRAND_HE_SEARCH} (Torah Pod) — פודקאסטים ושיעורי תורה להאזנה במקום אחד. חפשו רב או נושא, עקבו אחרי פודקאסטים ושמרו פרקים להאזנה."
        website = json.dumps({
            "@context": "https://schema.org", "@type": "WebSite", "name": BRAND_HE,
            "alternateName": [BRAND_HE_SEARCH, BRAND, "תורה פוד"], "url": SITE_ORIGIN + "/",
            "inLanguage": ["he", "en"], "description": description,
        }, ensure_ascii=False).replace("<", "\\u003c")
        search_metadata += (
            f'\n  <meta data-site-search-meta name="description" content="{_escape(description)}">'
            f'\n  <meta data-site-search-meta property="og:title" content="{_escape(page_title)}">'
            f'\n  <meta data-site-search-meta property="og:description" content="{_escape(description)}">'
            '\n  <meta data-site-search-meta property="og:type" content="website">'
            f'\n  <link data-site-search-meta rel="canonical" href="{SITE_ORIGIN}/">'
            f'\n  <script data-site-search-meta type="application/ld+json">{website}</script>'
        )
    return f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#f7f8f5">
  <meta name="color-scheme" content="light dark">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="{BRAND_HE}">
  <title>{_escape(page_title)}</title>
  {search_metadata}
  <link rel="manifest" href="{manifest}">
  <link rel="icon" type="image/png" sizes="192x192" href="{relative_prefix}assets/icon-192.png">
  <link rel="apple-touch-icon" href="{relative_prefix}assets/icon-192.png">
  <script src="{relative_prefix}assets/theme.js?v={_asset_version()}"></script>
  <link rel="stylesheet" href="{css}">
</head>
<body>
  <a class="skip-link" href="#main-content" data-i18n="skip_to_content">{HE["skip_to_content"]}</a>
  <header class="site-header">
    <nav class="nav" data-i18n-aria="primary_navigation" aria-label="{HE["primary_navigation"]}">
      <a class="brand" href="{home}" data-app-route="/">{_brand_mark()}<span data-i18n="brand_name">{BRAND_HE}</span></a>
      <div class="nav-actions">
        <a class="nav-search-shortcut" href="{search}" data-app-route="/search/" data-i18n-aria="search" aria-label="{HE["search"]}">{_nav_icon("search")}</a>
        <div class="account-nav" data-account-nav>
          <button class="account-toggle" type="button" data-account-toggle{account_guest_state} aria-controls="account-options" aria-expanded="false" data-i18n-aria="{account_label}" aria-label="{HE[account_label]}"><span data-account-avatar>{_ui_icon("account")}</span>{account_signin}</button>
          <div class="account-menu" id="account-options" data-account-menu hidden>
            <div class="account-menu-profile">
              <span class="account-menu-avatar" data-account-menu-avatar aria-hidden="true">{_ui_icon("account")}</span>
              <div class="account-menu-identity"><strong data-account-menu-name data-i18n="your_account">{HE["your_account"]}</strong><span data-account-menu-caption data-i18n="sync_listening">{HE["sync_listening"]}</span></div>
            </div>
            {account_management}
            <div data-account-menu-content></div>
          </div>
        </div>
        <div class="nav-overflow">
          <button class="nav-menu-toggle" type="button" data-nav-menu-toggle aria-controls="app-options" aria-expanded="false" data-i18n-aria="nav_menu" aria-label="{HE["nav_menu"]}">{_ui_icon("more")}</button>
          <div class="nav-overflow-menu" id="app-options">
            <a href="{onboard}" data-app-route="/onboard/" data-i18n="onboard">{HE["onboard"]}</a>
            <a href="{about}" data-app-route="/about/" data-i18n="about">{HE["about"]}</a>{donation_nav}
            <label class="theme-setting"><span data-i18n="theme">{HE["theme"]}</span><select data-theme-select aria-label="{HE['theme']}" data-i18n-aria="theme"><option value="system" data-i18n="theme_system">{HE["theme_system"]}</option><option value="light" data-i18n="theme_light">{HE["theme_light"]}</option><option value="dark" data-i18n="theme_dark">{HE["theme_dark"]}</option></select></label>
            <button class="language-toggle" type="button" data-language-toggle data-i18n="language">{HE["language"]}</button>
          </div>
        </div>
      </div>
    </nav>
  </header>
  <main id="main-content" tabindex="-1">
{body}
  </main>
  <footer class="footer">
    <div class="section footer-inner">
      <span class="footer-brand">{_brand_mark()}<span data-i18n="brand_name">{BRAND_HE}</span></span>
      <a href="{about_contact}" data-app-route="/about/#contact" data-i18n="contact">{HE["contact"]}</a>
      <a href="{terms}" data-app-route="/terms/" data-i18n="terms">{HE["terms"]}</a>
      <span class="build-version" data-site-build="{_escape(SITE_BUILD_ID)}" data-app-version>Site {_escape(SITE_BUILD_ID)}</span>
    </div>
  </footer>
  <nav class="app-bottom-nav" data-i18n-aria="app_navigation" aria-label="{HE["app_navigation"]}">
    <a class="bottom-nav-item" href="{home}" data-app-route="/" data-nav-route="/">
      <span class="bottom-nav-icon">{_nav_icon("home")}</span>
      <span data-i18n="home">{HE["home"]}</span>
    </a>
    <a class="bottom-nav-item" href="{explore}" data-app-route="/explore/" data-nav-route="/explore/">
      <span class="bottom-nav-icon">{_nav_icon("explore")}</span><span data-i18n="explore">{HE["explore"]}</span>
    </a>
    <a class="bottom-nav-item" href="{search}" data-app-route="/search/" data-nav-route="/search/">
      <span class="bottom-nav-icon">{_nav_icon("search")}</span><span data-i18n="search">{HE["search"]}</span>
    </a>
    <a class="bottom-nav-item" href="{subscriptions}" data-app-route="/subscriptions/" data-nav-route="/subscriptions/">
      <span class="bottom-nav-icon">{_nav_icon("subscriptions")}</span><span data-i18n="library">{HE["library"]}</span>
    </a>
    <a class="bottom-nav-item" href="{queue}" data-app-route="/queue/" data-nav-route="/queue/">
      <span class="bottom-nav-icon">{_nav_icon("queue")}</span><span data-i18n="queue">{HE["queue"]}</span>
    </a>
  </nav>
  <aside class="resume-card" data-resume hidden>
    <div>
      <span class="resume-label" data-i18n="continue_listening">{HE["continue_listening"]}</span>
      <strong data-resume-title></strong>
      <span data-resume-show></span>
    </div>
    <button class="button primary" type="button" data-resume-play data-i18n="listen">{HE["listen"]}</button>
    <button class="resume-close" type="button" data-resume-close data-i18n-aria="player_close" aria-label="{HE["player_close"]}">{_ui_icon("close")}</button>
  </aside>
  <div class="app-status" data-app-status role="status" aria-live="polite" aria-atomic="true" hidden></div>
  <section class="app-player" data-player hidden data-i18n-aria="audio_player" aria-label="{HE["audio_player"]}" tabindex="-1">
    <div class="player-sheet-handle" aria-hidden="true"></div>
    <div class="player-topbar">
      <button class="player-minimize" type="button" data-player-minimize data-i18n-aria="player_minimize" aria-label="{HE["player_minimize"]}">{_ui_icon("down")}</button>
      <span class="player-kicker" data-i18n="now_playing">{HE["now_playing"]}</span>
      <span class="player-topbar-spacer" aria-hidden="true"></span>
    </div>
    <div class="player-main">
      <button class="player-expand" type="button" data-player-details aria-expanded="false" data-i18n-aria="player_details" aria-label="{HE["player_details"]}">
        <img class="player-artwork" src="" alt="" data-player-artwork hidden>
      </button>
      <button class="player-details" type="button" data-player-open aria-expanded="false" data-i18n-aria="player_details" aria-label="{HE['player_details']}">
        <strong data-player-title></strong>
        <span data-player-show></span>
      </button>
      <input class="player-seek" type="range" min="0" max="1" value="0" step="1" data-player-seek data-i18n-aria="player_progress" aria-label="{HE["player_progress"]}">
      <progress class="player-mini-progress" max="1" value="0" data-player-mini-progress aria-hidden="true"></progress>
      <p class="player-description" data-player-description hidden></p>
    </div>
    <span class="player-time" data-player-time><span data-player-elapsed>0:00</span><span data-player-remaining>-0:00</span></span>
    <div class="player-primary-controls">
      <button class="player-queue-nav" type="button" data-player-prev data-i18n-aria="previous_queue" aria-label="{HE["previous_queue"]}">{_ui_icon("previous")}</button>
      <button class="player-skip" type="button" data-player-skip="-15" data-i18n-aria="skip_back" aria-label="{HE["skip_back"]}">{_ui_icon("back15")}</button>
      <button class="player-toggle" type="button" data-player-toggle aria-label="{HE["listen"]}">{_ui_icon("play")}</button>
      <button class="player-skip" type="button" data-player-skip="30" data-i18n-aria="skip_forward" aria-label="{HE["skip_forward"]}">{_ui_icon("forward30")}</button>
      <button class="player-queue-nav" type="button" data-player-next data-i18n-aria="next_queue" aria-label="{HE["next_queue"]}">{_ui_icon("next")}</button>
      <button class="player-mute" type="button" data-player-mute aria-pressed="false" aria-label="{HE['mute']}">{_ui_icon("volume")}</button>
    </div>
    <div class="player-secondary-controls">
      <button class="player-speed" type="button" data-player-speed data-i18n-aria="playback_speed" aria-label="{HE["playback_speed"]}">1x</button>
      <a class="player-queue-link" href="{queue}" data-app-route="/queue/">{_ui_icon("queue")}<span data-i18n="open_queue">{HE["open_queue"]}</span></a>
      <a class="player-episode-page" data-player-episode-link data-i18n="episode_page">{HE['episode_page']}</a>
      <button class="player-close" type="button" data-player-close data-i18n-aria="player_stop" aria-label="{HE["player_stop"]}">{_ui_icon("stop")}<span data-i18n="player_stop">{HE["player_stop"]}</span></button>
      <p class="player-volume-hint" data-player-volume-hint hidden data-i18n="device_volume">{HE['device_volume']}</p>
    </div>
  </section>
  <script src="{relative_prefix}assets/storage.js?v={_asset_version()}" defer></script>
  <script src="{relative_prefix}assets/accounts-bootstrap.js?v={_asset_version()}" defer></script>
  <script src="{relative_prefix}assets/listen-core.js?v={_asset_version()}" defer></script>
  <script src="{app_js}" defer data-torah-pod-labels="{_escape(json.dumps({"he": HE, "en": EN}, ensure_ascii=False))}" data-torah-pod-base="{_escape(relative_prefix)}"></script>
</body>
</html>
"""


def _show_card(show: ShowConfig, episodes: list[dict[str, Any]], *, prefix: str = "") -> str:
    artwork = f"{prefix}{show.slug}/assets/podcast-cover.png"
    latest = episodes[0] if episodes else {}
    episode_dates = [str(episode.get("published") or "") for episode in episodes if episode.get("published")]
    hosting_key = _show_hosting_key(show)
    source_badge = _show_hosting_badge(show)
    latest_line = ""
    if latest:
        latest_line = (
            f'<p class="latest-line"><span class="pill" data-i18n="latest_episode">'
            f'{HE["latest_episode"]}</span><span>{_escape(latest.get("title"))}</span></p>'
        )
    return f"""
      <article class="show-card" data-list-item data-show-card data-show-slug="{_escape(show.slug)}" data-show-title="{_escape(show.podcast.title)}" data-show-author="{_escape(show.podcast.author)}" data-show-artwork="{_escape(artwork)}" data-show-url="{_escape(prefix + show.slug + '/index.html')}" data-show-latest="{_escape(latest.get('published'))}" data-show-episode-dates="{_escape(json.dumps(episode_dates, ensure_ascii=False))}" data-filter-value="{hosting_key}" data-search-item="{_search_text(show.podcast.title, show.podcast.author)}">
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


def _episode_item(
    episode: dict[str, Any],
    *,
    id_suffix: str = "",
    show_context: bool = True,
    artwork: bool = True,
) -> str:
    duration = _duration(episode.get("duration"))
    meta = " · ".join(part for part in (_date(str(episode.get("published") or "")), duration) if part)
    show_title = episode.get("show_title")
    show_url = episode.get("show_page_url") or (
        f'{_escape(episode.get("show_slug"))}/index.html' if episode.get("show_slug") else ""
    )
    show_title_line = ""
    if show_context and show_title and show_url:
        show_title_line = (
            f'<p class="muted episode-show-link"><a href="{_escape(show_url)}"'
            f' data-app-route="/{_escape(episode.get("show_slug"))}/">{_escape(show_title)}</a></p>'
        )
    elif show_context and show_title:
        show_title_line = f'<p class="muted">{_escape(show_title)}</p>'
    source_link = ""
    if episode.get("source_url"):
        source_link = (
            f'<a href="{_escape(episode.get("source_url"))}" target="_blank" '
            f'rel="noopener noreferrer" data-i18n="source">{HE["source"]}</a>'
        )
    episode_id = _episode_identity(episode)
    dom_id = f"{_episode_dom_id(episode)}{id_suffix}"
    artwork_url = episode.get("artwork_url") or ""
    artwork_markup = (
        f'        <img class="episode-artwork" src="{_escape(artwork_url)}" alt="">\n'
        if artwork and artwork_url
        else ""
    )
    episode_href = episode.get("episode_page_url") or f"#{dom_id}"
    return f"""
      <article id="{dom_id}" class="episode{' episode-with-artwork' if artwork and artwork_url else ''}" data-list-item data-episode-id="{_escape(episode_id)}" data-episode-title="{_escape(episode.get("title"))}" data-episode-show="{_escape(show_title or episode.get("show_author") or BRAND)}" data-episode-show-slug="{_escape(episode.get("show_slug"))}" data-filter-value="{_escape(episode.get("filter_value"))}" data-episode-artwork="{_escape(artwork_url)}" data-episode-duration="{_escape(episode.get("duration"))}" data-episode-src="{_escape(episode.get("url"))}" data-episode-href="{_escape(episode_href)}" data-episode-description="{_escape(_plain_text(episode.get("description")))}" data-search-item="{_search_text(episode.get("title"), _search_excerpt(episode.get("description")), show_title, episode.get("show_author"))}">
{artwork_markup}        <div class="episode-head">
          <div>
            <h3><a href="{_escape(episode_href)}">{_escape(episode.get("title"))}</a></h3>{show_title_line}
          </div>
          <p class="episode-meta">{_escape(meta)}</p>
        </div>
        <audio preload="none" data-audio-src="{_escape(episode.get("url"))}" hidden aria-hidden="true"></audio>
        <p class="episode-progress" data-episode-progress hidden></p>
        <div class="episode-actions">
          <button class="button episode-play" type="button" data-episode-play data-i18n="listen">{HE["listen"]}</button>
          <button class="button secondary episode-queue" type="button" data-queue-add data-i18n="add_to_queue">{HE["add_to_queue"]}</button>
          <details class="episode-more">
            <summary data-i18n-aria="nav_menu" aria-label="{HE["nav_menu"]}">{_ui_icon("more")}</summary>
            <div class="episode-more-menu">
              <button class="button secondary" type="button" data-save-episode data-i18n="save_episode">{HE["save_episode"]}</button>
              <button class="button secondary episode-queue-next" type="button" data-queue-next data-i18n="play_next">{HE["play_next"]}</button>
              <button class="button secondary episode-share" type="button" data-share-episode data-i18n="share">{HE["share"]}</button>
              <button class="button secondary episode-played" type="button" data-toggle-played data-i18n="mark_played">{HE["mark_played"]}</button>
              <div class="episode-links">{source_link}</div>
            </div>
          </details>
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
        "show_page_url": f"{show.slug}/index.html",
        "episode_page_url": _episode_page_path(show.slug, episode),
        "filter_value": _show_hosting_key(show),
    }


def _episode_detail_page(show: ShowConfig, episode: dict[str, Any], *, site_config: SiteConfig) -> str:
    """Render the focused listening page shared by links, search, and the player."""
    context = {
        **episode,
        "show_slug": show.slug,
        "show_title": show.podcast.title,
        "show_author": show.podcast.author,
        "artwork_url": "../../assets/podcast-cover.png",
        "show_page_url": "../../",
        "episode_page_url": "./",
        "filter_value": _show_hosting_key(show),
    }
    source_link = ""
    if episode.get("source_url"):
        source_link = (
            f'<a class="button secondary" href="{_escape(episode.get("source_url"))}" '
            f'target="_blank" rel="noopener noreferrer" data-i18n="source">{HE["source"]}</a>'
        )
    description = _plain_text(episode.get("description")).strip()
    meta = " · ".join(
        part for part in (_date(str(episode.get("published") or "")), _duration(episode.get("duration"))) if part
    )
    episode_id = _episode_identity(context)
    return f"""
    <section class="section episode-detail-shell">
      <a class="back-link" href="../../" data-app-route="/{_escape(show.slug)}/">{_escape(show.podcast.title)}</a>
      <article class="episode episode-detail" data-episode-id="{_escape(episode_id)}" data-episode-title="{_escape(episode.get("title"))}" data-episode-show="{_escape(show.podcast.title)}" data-episode-show-slug="{_escape(show.slug)}" data-filter-value="{_escape(_show_hosting_key(show))}" data-episode-artwork="../../assets/podcast-cover.png" data-episode-duration="{_escape(episode.get("duration"))}" data-episode-src="{_escape(episode.get("url"))}" data-episode-href="./" data-episode-description="{_escape(description)}" data-search-item="{_search_text(episode.get("title"), _search_excerpt(episode.get("description")), show.podcast.title, show.podcast.author)}">
        <img class="episode-artwork" src="../../assets/podcast-cover.png" alt="">
        <div class="episode-detail-content">
          <p class="episode-detail-show">{_escape(show.podcast.title)}</p>
          <h1>{_escape(episode.get("title"))}</h1>
          <p class="episode-meta">{_escape(meta)}</p>
          <audio preload="none" data-audio-src="{_escape(episode.get("url"))}" hidden aria-hidden="true"></audio>
          <p class="episode-progress" data-episode-progress hidden></p>
          <div class="episode-actions">
            <button class="button episode-play" type="button" data-episode-play data-i18n="listen">{HE["listen"]}</button>
            <button class="button secondary episode-queue" type="button" data-queue-add data-i18n="add_to_queue">{HE["add_to_queue"]}</button>
            <button class="button secondary" type="button" data-save-episode data-i18n="save_episode">{HE["save_episode"]}</button>
              <button class="button secondary episode-queue-next" type="button" data-queue-next data-i18n="play_next">{HE["play_next"]}</button>
            <button class="button secondary episode-share" type="button" data-share-episode data-i18n="share">{HE["share"]}</button>
            <button class="button secondary episode-played" type="button" data-toggle-played data-i18n="mark_played">{HE["mark_played"]}</button>
{('            ' + source_link) if source_link else ''}
          </div>
        </div>
      </article>
      {f'<section class="episode-description"><h2>על הפרק</h2><p>{_escape(description)}</p></section>' if description else ''}
    </section>
"""


def _write_app_js() -> None:
    for name in ("app.js", "listen-core.js", "theme.js", "storage.js", "accounts-bootstrap.js", "accounts.mjs", "accounts-core.mjs", "firebase-auth.bundle.js"):
        content = (ROOT / "podcast_feeds" / "web" / name).read_text(encoding="utf-8")
        if name == "app.js":
            content = content.replace("  // LISTENING_PAGES", (ROOT / "podcast_feeds" / "web" / "listening-pages.js").read_text(encoding="utf-8"))
        target_name = name.replace('.mjs', '.js')
        if name.endswith('.mjs'):
            content = content.replace("'./accounts-core.mjs'", "'./accounts-core.js'")
        _write_text(PUBLIC_DIR / "assets" / target_name, content)


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
                "name": f"{BRAND_HE} | {BRAND}",
                "short_name": BRAND_HE,
                "description": HE["home_welcome"],
                "lang": "he",
                "dir": "rtl",
                "start_url": "./",
                "scope": "./",
                "display": "standalone",
                "background_color": "#f7f8f5",
                "theme_color": "#24685d",
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
    # Include every precached resource plus this policy revision. A clean build
    # writes the service worker after pages/data so content changes migrate an
    # installed PWA to a fresh shell instead of retaining stale metadata.
    cache_revision = "3"
    shell_fingerprint_paths = (
        PUBLIC_DIR / "index.html",
        PUBLIC_DIR / "about" / "index.html",
        assets / "site.css",
        assets / "app.js",
        assets / "storage.js",
        assets / "accounts-bootstrap.js",
        PUBLIC_DIR / "accounts-config.json",
        assets / "listen-core.js",
        assets / "theme.js",
        assets / "fonts" / "NotoSansHebrew.ttf",
        PUBLIC_DIR / "metadata" / "v1" / "latest.json",
        assets / "icon-192.png",
        assets / "icon-512.png",
        PUBLIC_DIR / "manifest.webmanifest",
        PUBLIC_DIR / "catalog.json",
        PUBLIC_DIR / "catalog-meta.json",
        PUBLIC_DIR / "status.json",
    )
    fingerprint = hashlib.sha256(cache_revision.encode("utf-8"))
    for path in shell_fingerprint_paths:
        fingerprint.update(path.read_bytes())
    cache_fingerprint = fingerprint.hexdigest()[:12]
    _write_text(
        PUBLIC_DIR / "sw.js",
        ("""const CACHE_NAME = "__CACHE_NAME__";
const SHELL_ASSETS = [
  "./",
  "./index.html",
  "./about/",
  "./explore/",
  "./assets/site.css",
  "./assets/app.js",
  "./assets/storage.js",
  "./assets/accounts-bootstrap.js",
  "./assets/listen-core.js",
  "./assets/theme.js",
  "./assets/fonts/NotoSansHebrew.ttf",
  "./metadata/v1/latest.json",
  "./assets/icon-192.png",
  "./assets/icon-512.png",
  "./manifest.webmanifest",
  "./catalog.json",
  "./catalog-meta.json",
  "./status.json",
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
  if (url.pathname.startsWith("/api/") || request.headers.has("Authorization")) return;
  if (url.pathname.includes("/__/auth/") || url.pathname.includes("/auth/callback") || url.searchParams.has("code") || url.searchParams.has("state")) return;
  if (url.pathname.endsWith("/accounts-config.json")) return;
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
  const freshData = url.pathname.endsWith(".json") || url.pathname.endsWith(".xml");
  if (request.destination === "script" || request.destination === "style" || freshData) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(async () => (await caches.match(request)) || ((request.destination === "script" || request.destination === "style") ? caches.match(url.origin + url.pathname) : undefined))
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
""").replace("__CACHE_NAME__", f"torah-pod-shell-{cache_fingerprint}"),
    )


def _write_css() -> None:
    sources = ROOT / "podcast_feeds" / "web"
    _write_text(PUBLIC_DIR / "assets" / "site.css", "\n".join((sources / name).read_text(encoding="utf-8") for name in ("base.css", "listening.css", "accounts.css")))
    for font in (sources / "fonts").glob("*"):
        target = PUBLIC_DIR / "assets" / "fonts" / font.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(font, target)


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
    body = f"""
    <section class="section">
      <p class="kicker" data-i18n="brand_name">{BRAND_HE}</p>
      <h1>Contact moved</h1>
      <p class="muted">Contact is now part of the About page.</p>
      <p><a class="button primary" href="../about/#contact" data-app-route="/about/#contact">Open About</a></p>
    </section>
"""
    _write_text(contact_dir / "index.html", _page("Contact", body, site_config=site_config, relative_prefix="../"))


def _contact_section(site_config: SiteConfig) -> str:
    if not site_config.contact_email:
        return ""
    email = _escape(site_config.contact_email)
    return f"""
    <section class="section" id="contact">
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


def _build_onboarding_page(site_config: SiteConfig) -> None:
    onboard_dir = PUBLIC_DIR / "onboard"
    onboard_dir.mkdir(parents=True, exist_ok=True)
    body = f"""
    <section class="section">
      <div class="onboard-shell">
        <aside class="onboard-intro">
          <h1 data-i18n="heading">צירוף פודקאסט</h1>
          <p data-i18n="intro">מלאו פרטים בסיסיים. Torah Pod יבדוק ויאשר לפני פרסום.</p>
          <ul class="onboard-steps" data-i18n-aria="onboarding_steps" aria-label="{HE["onboarding_steps"]}">
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

        <form id="onboarding-form" class="onboard-form" data-worker-endpoint="https://youtube-podcast-onboarding.shauldr.workers.dev" data-turnstile-site-key="{_escape(site_config.turnstile_site_key)}">
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
            <span data-i18n="approvalLabel">אני מאשר/ת שאני בעל/ת הזכויות בתוכן או מוסמך/ת לאשר ל-Torah Pod לאחסן ולהפיץ אותו, ומבין/ה שנדרש אישור לפני פרסום.</span>
            <input id="approval" type="checkbox">
          </label>
          <p class="hint"><a href="../terms/" data-app-route="/terms/" data-i18n="terms">תנאים וזכויות</a></p>

          <div class="turnstile-widget" data-turnstile-container hidden></div>

          <button id="submit-button" class="button primary hidden" type="submit" data-i18n="submitButton">שלחו בקשה</button>
          <p id="status" class="status" role="status"></p>
        </form>
        <section id="onboarding-success" class="onboard-success" hidden tabindex="-1" aria-live="polite">
          <h2 data-i18n="successTitle">הבקשה נשלחה</h2>
          <p data-i18n="successDetail">קיבלנו את פרטי הפודקאסט. נבדוק אותם לפני כל פרסום, וניצור קשר אם נצטרך פרטים נוספים.</p>
          <div><button class="button secondary" type="button" data-onboarding-another data-i18n="anotherRequest">שליחת בקשה נוספת</button></div>
        </section>
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
        <h1 data-i18n="brand_name">{BRAND_HE}</h1>
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
      <div class="about-panel diagnostics-panel">
        <div>
          <h2 data-i18n="diagnostics_title">{HE["diagnostics_title"]}</h2>
          <p data-i18n="diagnostics_text">{HE["diagnostics_text"]}</p>
        </div>
        <div class="about-note diagnostics-actions">
          <button class="button secondary" type="button" data-copy-diagnostics data-i18n="copy_diagnostics">{HE["copy_diagnostics"]}</button>
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
{_contact_section(site_config)}
"""
    _write_text(about_dir / "index.html", _page("About", body, site_config=site_config, relative_prefix="../"))


def _build_terms_page(site_config: SiteConfig) -> None:
    terms_dir = PUBLIC_DIR / "terms"
    terms_dir.mkdir(parents=True, exist_ok=True)
    email = _escape(site_config.contact_email)
    body = f"""
    <section class="section hero page-hero">
      <div class="hero-copy">
        <p class="kicker" data-i18n="terms">{HE["terms"]}</p>
        <h1 data-i18n="terms_title">{HE["terms_title"]}</h1>
      </div>
    </section>
    <section class="section">
      <div class="about-panel">
        <div>
          <h2 data-i18n="terms_code_title">{HE["terms_code_title"]}</h2>
          <p data-i18n="terms_code_text">{HE["terms_code_text"]}</p>
        </div>
        <div>
          <h2 data-i18n="terms_content_title">{HE["terms_content_title"]}</h2>
          <p data-i18n="terms_content_text">{HE["terms_content_text"]}</p>
        </div>
      </div>
    </section>
    <section class="section">
      <div class="about-panel">
        <div>
          <h2 data-i18n="terms_removal_title">{HE["terms_removal_title"]}</h2>
          <p data-i18n="terms_removal_text">{HE["terms_removal_text"]}</p>
          <p><a class="button primary" href="mailto:{email}">{email}</a></p>
        </div>
        <div>
          <h2 data-i18n="terms_privacy_title">{HE["terms_privacy_title"]}</h2>
          <p data-i18n="terms_privacy_text">{HE["terms_privacy_text"]}</p>
        </div>
      </div>
    </section>
"""
    _write_text(terms_dir / "index.html", _page("Terms & Rights", body, site_config=site_config, relative_prefix="../"))


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
            "/contact/ /about/#contact 301",
            "/contact/* /about/#contact 301",
            "/status/ / 302",
            "/status/* / 302",
        ]
    )
    redirects_path = PUBLIC_DIR / "_redirects"
    if redirects:
        _write_text(redirects_path, "\n".join(redirects) + "\n")
    elif redirects_path.exists():
        redirects_path.unlink()



def _account_configuration() -> dict[str, Any]:
    from urllib.parse import urlsplit
    environment = os.environ.get("ACCOUNTS_ENVIRONMENT", "production")
    if environment not in ("production", "preview"):
        raise ValueError("Invalid account environment")
    config = json.loads((ROOT / "config" / f"accounts.{environment}.json").read_text(encoding="utf-8"))
    if config.get("environment") != environment or any(type(config.get(key)) is not bool for key in ("listenerAccounts", "publisherAccess")):
        raise ValueError("Invalid account configuration")
    if config["listenerAccounts"] or config["publisherAccess"]:
        api = urlsplit(config.get("apiOrigin", ""))
        firebase = config.get("firebase") or {}
        if api.scheme != "https" or not api.hostname or api.path not in ("", "/") or api.query or api.fragment or api.username:
            raise ValueError("Accounts require an HTTPS API origin")
        if not all(isinstance(firebase.get(key), str) and firebase[key] for key in ("apiKey", "authDomain", "projectId", "appId")):
            raise ValueError("Accounts require public Firebase configuration")
        if firebase["authDomain"] != firebase["projectId"] + ".firebaseapp.com":
            raise ValueError("Firebase auth origin must match the selected project")
        other = "preview" if environment == "production" else "production"
        other_config = json.loads((ROOT / "config" / f"accounts.{other}.json").read_text(encoding="utf-8"))
        if (other_config.get("firebase") or {}).get("projectId") == firebase["projectId"] or other_config.get("apiOrigin") == config["apiOrigin"]:
            raise ValueError("Preview and production must use separate account resources")
    return config


def _build_account_page(site_config: SiteConfig) -> None:
    (PUBLIC_DIR / "account").mkdir(parents=True, exist_ok=True)
    config = _account_configuration()
    turnstile_site_key = config.get("turnstileSiteKey", site_config.turnstile_site_key if config["environment"] == "production" else "")
    if config["publisherAccess"] and not turnstile_site_key:
        raise ValueError("Publisher access requires an environment-specific Turnstile site key")
    body = f'''    <section class="section account-shell" data-account-page data-turnstile-site-key="{_escape(turnstile_site_key)}">
      <h1 data-i18n="manage_account">{HE["manage_account"]}</h1>
      <div data-account-content aria-busy="false"><p>ניהול פודקאסטים יהיה זמין כאן בהמשך.</p></div>
      <p><a href="../terms/" data-app-route="/terms/" data-i18n="terms">{HE["terms"]}</a></p>
    </section>'''
    _write_text(PUBLIC_DIR / "account" / "index.html", _page(HE["manage_account"], body, site_config=site_config, relative_prefix="../"))

def _write_security_headers() -> None:
    config = _account_configuration()
    account_enabled = config["listenerAccounts"] or config["publisherAccess"]
    api_origin = config["apiOrigin"] if account_enabled else ""
    auth_origin = "https://" + config["firebase"]["authDomain"] if account_enabled else ""
    _write_text(
        PUBLIC_DIR / "_headers",
        f"""/*
  Content-Security-Policy: default-src 'self'; script-src 'self' https://challenges.cloudflare.com https://static.cloudflareinsights.com{' https://apis.google.com' if account_enabled else ''}; script-src-attr 'none'; style-src 'self'; style-src-attr 'none'; img-src 'self' data: https:; media-src 'self' https:; connect-src 'self' https://youtube-podcast-onboarding.shauldr.workers.dev https://cloudflareinsights.com{' ' + api_origin + ' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com ' + auth_origin if account_enabled else ''}; frame-src https://challenges.cloudflare.com{' ' + auth_origin + ' https://accounts.google.com' if account_enabled else ''}; worker-src 'self'; manifest-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'
  Strict-Transport-Security: max-age=31536000
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  X-Permitted-Cross-Domain-Policies: none
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()
  Cross-Origin-Opener-Policy: same-origin{'-allow-popups' if account_enabled else ''}
  Cross-Origin-Resource-Policy: same-site
  Origin-Agent-Cluster: ?1
""",
    )
def _episode_published_date(episode: dict[str, Any]) -> date | None:
    try:
        return datetime.strptime(str(episode.get("published") or ""), "%Y%m%d").date()
    except ValueError:
        return None


def build_site(shows: list[ShowConfig]) -> None:
    site_config = load_site_config()
    _write_css()
    _write_app_js()
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
                "show_page_url": f"{show.slug}/index.html",
                "episode_page_url": _episode_page_path(show.slug, episode),
                "filter_value": _show_hosting_key(show),
            }
            for show in shows
            for episode in show_episodes[show.slug]
        ),
        key=lambda episode: episode.get("published") or "",
        reverse=True,
    )

    subscription_blocks = "\n".join(_subscription_show_block(show, show_episodes[show.slug]) for show in shows)
    suggested_cards = "\n".join(_show_card(show, show_episodes[show.slug]) for show in shows[:3])
    total_episodes = sum(len(episodes) for episodes in show_episodes.values())
    recent_markup = "\n".join(_episode_item(episode, id_suffix="-home") for episode in all_episodes[:20])
    index_body = f"""
    <section class="section app-page-heading home-heading"><p class="kicker" data-i18n="brand_name">{BRAND_HE}</p><h1 data-i18n="home_welcome">{HE["home_welcome"]}</h1><p class="muted" data-i18n="home_subtitle">{HE["home_subtitle"]}</p></section>
    <section class="section home-resume" data-home-resume hidden>
      <img data-home-resume-artwork alt="" hidden>
      <div><span class="kicker" data-i18n="continue_listening">{HE["continue_listening"]}</span><h2 data-home-resume-title></h2><p class="muted" data-home-resume-show></p></div>
      <button class="button primary" type="button" data-home-resume-play data-i18n="listen">{HE["listen"]}</button>
    </section>
    <section class="section home-recent" data-home-recent>
      <div class="section-heading"><h2 data-home-recent-title data-i18n="recent_catalog">{HE["recent_catalog"]}</h2><a href="search/" data-app-route="/search/" data-i18n="search">{HE["search"]}</a></div>
      <p class="muted" data-home-recent-status role="status"></p>
      <div class="episode-list compact-episode-list" data-home-recent-list>{recent_markup}</div>
      <div class="load-more-row"><button class="button secondary" type="button" data-home-more data-i18n="show_more">{HE["show_more"]}</button></div>
    </section>
    <section class="section discovery-section"><div class="section-heading"><h2 data-i18n="suggested_subscriptions">{HE["suggested_subscriptions"]}</h2><a href="explore/" data-app-route="/explore/" data-i18n="see_all">{HE["see_all"]}</a></div><p class="muted follow-invitation" data-i18n="follow_invite">{HE["follow_invite"]}</p><div class="grid discovery-grid">{suggested_cards}</div></section>
"""
    _write_text(PUBLIC_DIR / "index.html", _page("Home", index_body, site_config=site_config, is_home=True))

    routed_cards = "\n".join(_show_card(show, show_episodes[show.slug], prefix="../") for show in shows)
    explore_body = f"""
    <section class="section app-page-heading"><p class="kicker" data-i18n="brand_name">{BRAND_HE}</p><h1 data-i18n="explore_title">{HE['explore_title']}</h1><p class="muted" data-i18n="explore_subtitle">{HE['explore_subtitle']}</p></section>
    <section class="section" data-explore-page>
      <div class="destination-toolbar">
        <label class="search-field"><span data-i18n="explore_filter">{HE['explore_filter']}</span><input class="search" type="search" data-explore-filter data-i18n-placeholder="explore_filter" placeholder="{HE['explore_filter']}" autocomplete="off"></label>
        <label class="explore-sort"><span data-i18n="sort">{HE['sort']}</span><select data-explore-sort data-i18n-aria="sort" aria-label="{HE['sort']}"><option value="recent" data-i18n="sort_recent">{HE['sort_recent']}</option><option value="alpha" data-i18n="sort_alpha">{HE['sort_alpha']}</option></select></label>
      </div>
      <p class="muted" data-explore-status role="status">{len(shows)} {HE['podcast_results']}</p>
      <div class="grid explore-grid" data-explore-grid>{routed_cards}</div>
      <p class="muted" data-explore-empty hidden data-i18n="no_search_results">{HE['no_search_results']}</p>
    </section>
"""
    explore_dir = PUBLIC_DIR / "explore"
    explore_dir.mkdir(parents=True, exist_ok=True)
    _write_text(explore_dir / "index.html", _page("Explore", explore_body, site_config=site_config, relative_prefix="../"))
    subscriptions_body = f"""
    <section class="section app-page-heading"><p class="kicker" data-i18n="brand_name">{BRAND_HE}</p><h1 data-i18n="library">{HE["library"]}</h1></section>
    <nav class="section library-tabs" aria-label="{HE['library']}" data-i18n-aria="library"><button class="button" type="button" data-library-tab="followed" aria-pressed="true" data-i18n="subscriptions">{HE['subscriptions']}</button><button class="button" type="button" data-library-tab="saved" aria-pressed="false" data-i18n="saved">{HE['saved']}</button><button class="button" type="button" data-library-tab="history" aria-pressed="false" data-i18n="history">{HE['history']}</button><a class="button" href="../queue/" data-app-route="/queue/" data-i18n="queue">{HE['queue']}</a></nav>
    <section class="section library-episode-section" data-library-episodes hidden><div class="episode-list compact-episode-list" data-library-episode-list></div><p class="muted" data-library-episodes-empty data-i18n="library_empty">{HE['library_empty']}</p></section>
    <section class="section subscriptions-page" data-subscriptions-page>
      <div class="destination-toolbar">
        <label class="search-field"><span data-i18n="subscription_filter">{HE["subscription_filter"]}</span><input class="search" type="search" data-subscription-filter data-i18n-placeholder="subscription_filter" placeholder="{HE['subscription_filter']}"></label>
        <div class="segmented-control" aria-label="Sort"><button class="button" type="button" data-subscription-sort="recent" aria-pressed="true" data-i18n="sort_recent">{HE["sort_recent"]}</button><button class="button" type="button" data-subscription-sort="alpha" aria-pressed="false" data-i18n="sort_alpha">{HE["sort_alpha"]}</button></div>
      </div>
      <div class="empty-library-card" data-subscriptions-page-empty hidden><h2 data-i18n="subscriptions_empty_title">{HE["subscriptions_empty_title"]}</h2><p data-i18n="subscriptions_empty_text">{HE["subscriptions_empty_text"]}</p><a class="button primary" href="../explore/" data-app-route="/explore/" data-i18n="browse_podcasts">{HE["browse_podcasts"]}</a></div>
      <div class="grid subscriptions-grid" data-subscriptions-grid>{routed_cards}</div>
      <p class="muted" data-subscriptions-page-none hidden data-i18n="no_search_results">{HE["no_search_results"]}</p>
    </section>
"""
    subscriptions_dir = PUBLIC_DIR / "subscriptions"
    subscriptions_dir.mkdir(parents=True, exist_ok=True)
    _write_text(subscriptions_dir / "index.html", _page("Subscriptions", subscriptions_body, site_config=site_config, relative_prefix="../"))

    search_recent = "\n".join(_episode_item({**episode, "artwork_url": f"../{episode['artwork_url']}", "show_page_url": f"../{episode['show_page_url']}", "episode_page_url": f"../{episode['episode_page_url']}"}, id_suffix="-search") for episode in all_episodes[:20])
    search_body = f"""
    <section class="section app-page-heading"><p class="kicker" data-i18n="brand_name">{BRAND_HE}</p><h1 data-i18n="search_catalog">{HE["search_catalog"]}</h1></section>
    <section class="section search-page" data-search-page>
      <label class="search-field catalog-search"><span data-i18n="search_catalog">{HE["search_catalog"]}</span><input class="search" type="search" data-catalog-search data-i18n-placeholder="search_catalog_placeholder" placeholder="{HE['search_catalog_placeholder']}" autocomplete="off"></label>
      <p class="search-status" data-search-status role="status" aria-live="polite"></p>
      <section><div class="section-heading"><h2 data-search-episode-heading data-i18n="recent_catalog">{HE["recent_catalog"]}</h2></div><div class="episode-list compact-episode-list search-episode-list" data-search-episode-results>{search_recent}</div><div class="load-more-row"><button class="button" type="button" data-search-more hidden data-i18n="show_more">{HE["show_more"]}</button></div></section>
      <section><div class="section-heading"><h2 data-i18n="podcast_results">{HE["podcast_results"]}</h2></div><div class="grid search-podcast-grid" data-search-podcast-catalog>{routed_cards}</div></section>
    </section>
"""
    search_dir = PUBLIC_DIR / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    _write_text(search_dir / "index.html", _page("Search", search_body, site_config=site_config, relative_prefix="../"))

    queue_body = f"""
    <section class="section app-page-heading destination-heading"><div><p class="kicker" data-i18n="brand_name">{BRAND_HE}</p><h1 data-i18n="queue">{HE["queue"]}</h1></div><button class="button" type="button" data-queue-clear data-i18n="clear_queue">{HE["clear_queue"]}</button></section>
    <section class="section queue-page"><div class="queue-page-list" data-queue-list></div><p class="muted destination-empty" data-queue-empty data-i18n="queue_empty">{HE["queue_empty"]}</p></section>
"""
    queue_dir = PUBLIC_DIR / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    _write_text(queue_dir / "index.html", _page("Queue", queue_body, site_config=site_config, relative_prefix="../"))

    catalog = []
    search_index = []
    latest_shows = []
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
                "latest_episode_date": episodes[0].get("published", "") if episodes else "",
                "episode_dates": [episode.get("published", "") for episode in episodes],
            }
        )
        search_index.extend(
            {
                "id": _episode_identity({**episode, "show_slug": show.slug}),
                "title": str(episode.get("title") or ""),
                "show_slug": show.slug,
                "published": str(episode.get("published") or ""),
                "duration": int(episode.get("duration") or 0),
                "audio_url": str(episode.get("url") or ""),
                "page_url": _episode_page_path(show.slug, episode),
            }
            for episode in episodes
        )
        show_items = [item for item in search_index if item["show_slug"] == show.slug]
        latest_shows.append({**write_episode_pages(PUBLIC_DIR, show.slug, show_items), "title": show.podcast.title, "author": show.podcast.author})
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
                    "show_page_url": "index.html",
                    "episode_page_url": f"episodes/{_episode_dom_id({**episode, 'show_slug': show.slug})}/",
                    "filter_value": _show_hosting_key(show),
                },
                show_context=False,
                artwork=False,
            )
            for episode in episodes[:20]
        )
        latest_episode = _episode_identity({**episodes[0], "show_slug": show.slug}) if episodes else ""
        body = f"""
    <section class="section">
      <article class="show-hero" data-show-page data-show-card data-show-slug="{_escape(show.slug)}" data-show-title="{_escape(show.podcast.title)}" data-show-author="{_escape(show.podcast.author)}" data-show-artwork="assets/podcast-cover.png" data-show-url="index.html">
        <img src="assets/podcast-cover.png" alt="">
        <div>
          <div class="show-page-meta">{source_badge}</div>
          <h1>{_escape(show.podcast.title)}</h1>
          <p>{_escape(show.podcast.author)}</p>
          <div class="show-actions">
            <button class="button follow-button" type="button" data-follow-show data-i18n="follow">{HE["follow"]}</button>
            {f'<button class="button primary" type="button" data-play-latest="{_escape(latest_episode)}" data-i18n="play_latest">{HE["play_latest"]}</button>' if latest_episode else ''}
          </div>
          <details class="show-secondary"><summary data-i18n="show_details">{HE["show_details"]}</summary><p class="muted">{_escape(show.podcast.description)}</p><div class="show-links"><a class="button secondary" href="{_escape(_show_feed_href(show))}"{_show_feed_attrs(show)} data-i18n="feed">{HE["feed"]}</a><a class="button secondary" href="{_escape(show.podcast.website_url)}" target="_blank" rel="noopener noreferrer" data-i18n="source">{HE["source"]}</a>{platform_buttons}</div></details>
        </div>
      </article>
    </section>
    <section class="section">
      <div class="toolbar">
        <h2 data-i18n="episodes">{HE["episodes"]}</h2>
        <div class="search-field" data-list-controls="episode-list">
          <label for="episode-search" data-i18n="search_episodes">{HE["search_episodes"]}</label>
          <input id="episode-search" class="search" type="search" data-show-search data-i18n-placeholder="search_episodes_placeholder" placeholder="{_escape(HE['search_episodes_placeholder'])}">
        </div>
      </div>
      <div id="episode-list" class="episode-list" data-paginated-show="{_escape(show.slug)}" data-next-page="{2 if len(episodes) > 20 else 0}">
{episode_items or f'<p class="muted" data-i18n="empty">{HE["empty"]}</p>'}
      </div>
      <div class="load-more-row">
        <p class="muted" data-show-load-status role="status"></p><button class="button" type="button" data-show-more {"hidden" if len(episodes) <= 20 else ""} data-i18n="show_more">{HE["show_more"]}</button>
      </div>
    </section>
"""
        _write_text(
            show.public_dir / "index.html",
            _page(show.podcast.title, body, site_config=site_config, relative_prefix="../"),
        )
        for episode in episodes:
            episode_dir = show.public_dir / "episodes" / _episode_dom_id({**episode, "show_slug": show.slug})
            episode_dir.mkdir(parents=True, exist_ok=True)
            _write_text(
                episode_dir / "index.html",
                _page(
                    str(episode.get("title") or show.podcast.title),
                    _episode_detail_page(show, episode, site_config=site_config),
                    site_config=site_config,
                    relative_prefix="../../../",
                ),
            )

    _write_text(
        PUBLIC_DIR / "catalog.json",
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
    )
    _write_text(
        PUBLIC_DIR / "catalog-meta.json",
        json.dumps(_catalog_metadata(), ensure_ascii=False, indent=2) + "\n",
    )
    _write_text(
        PUBLIC_DIR / "search-index.json",
        json.dumps({"schema_version": SEARCH_INDEX_SCHEMA_VERSION, "episodes": search_index}, ensure_ascii=False, separators=(",", ":")) + "\n",
    )
    _write_text(PUBLIC_DIR / "metadata" / "v1" / "latest.json", json.dumps({"schema_version": 1, "shows": latest_shows}, ensure_ascii=False, separators=(",", ":")) + "\n")
    _build_status(shows, show_episodes, site_config)
    _build_account_page(site_config)
    _write_text(PUBLIC_DIR / "accounts-config.json", json.dumps(_account_configuration(), indent=2) + "\n")
    _build_onboarding_page(site_config)
    _build_about_page(site_config, show_count=len(shows), episode_count=total_episodes)
    _build_terms_page(site_config)
    _build_donation_page(site_config)
    _build_contact_page(site_config)
    _write_linked_feed_redirects(shows)
    _write_security_headers()
    _write_pwa_assets()
    print(f"{PUBLIC_DIR / 'index.html'} written with {len(shows)} show(s)")
