from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .config import ROOT, SHOWS_DIR
from .existing_feed import extract_existing_feed_metadata
from .youtube import extract_channel_metadata, extract_playlist_metadata

OWNER_NAME = "Torah Pod"
OWNER_EMAIL = "torahyoupod@gmail.com"
PUBLIC_BASE_URL = "https://shaqo88.github.io/youtube-podcast-feeds"
DEFAULT_CATEGORY = "Religion & Spirituality"
DEFAULT_SUBCATEGORY = "Judaism"
DEFAULT_DESCRIPTION = "Use source description if available."
DEFAULT_EXISTING_FEED_START_DATE = "1900-01-01"
FOLDER_ID_RE = re.compile(r"/folders/([^/?#]+)")
PLAYLIST_ID_RE = re.compile(r"[?&]list=([^&#]+)")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEBREW_WORD_SLUGS = {
    "הרב": "rav",
    "רב": "rav",
    "רבי": "rebbe",
    "ר'": "r",
    "שלום": "shalom",
    "חיים": "chaim",
    "יוסף": "yosef",
    "יצחק": "yitzchak",
    "מנחם": "menachem",
    "מענדל": "mendel",
    "שניאור": "shneur",
    "זלמן": "zalman",
    "דייטש": "deitsch",
    "וועכטר": "wechter",
}
HEBREW_CHAR_SLUGS = {
    "א": "a",
    "ב": "b",
    "ג": "g",
    "ד": "d",
    "ה": "h",
    "ו": "v",
    "ז": "z",
    "ח": "ch",
    "ט": "t",
    "י": "y",
    "כ": "ch",
    "ך": "ch",
    "ל": "l",
    "מ": "m",
    "ם": "m",
    "נ": "n",
    "ן": "n",
    "ס": "s",
    "ע": "a",
    "פ": "f",
    "ף": "f",
    "צ": "tz",
    "ץ": "tz",
    "ק": "k",
    "ר": "r",
    "ש": "sh",
    "ת": "t",
}


class OnboardingNotReady(Exception):
    pass


def _issue_labels(issue: dict[str, Any]) -> set[str]:
    return {label["name"] for label in issue.get("labels") or [] if isinstance(label, dict) and label.get("name")}


def _field_map(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    lines = body.splitlines()
    for line in lines:
        match = re.match(r"^- ([^:]+):\s*(.*)$", line.strip())
        if match:
            fields[match.group(1).strip().lower()] = match.group(2).strip()
    for index, line in enumerate(lines):
        heading = re.match(r"^###\s+(.+?)\s*$", line.strip())
        if not heading:
            continue
        values = []
        for value_line in lines[index + 1 :]:
            if value_line.startswith("### "):
                break
            if value_line.strip() and value_line.strip() != "_No response_":
                values.append(value_line.strip())
        if values:
            fields[heading.group(1).strip().lower()] = "\n".join(values).strip()
    return fields


def _field(fields: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = fields.get(name.lower())
        if value is not None:
            return value
    return None


def _section(body: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)"
    match = re.search(pattern, body, re.MULTILINE)
    if not match:
        return ""
    return match.group(1).strip()


def _checked(body: str, text: str) -> bool:
    pattern = rf"^- \[[xX]\]\s+{re.escape(text)}"
    return re.search(pattern, body, re.MULTILINE) is not None


def _require(value: str | None, label: str) -> str:
    if not value or value == "Not provided":
        raise ValueError(f"Missing required onboarding field: {label}")
    return value


def _optional(value: str | None) -> str:
    if not value or value == "Not provided":
        return ""
    return value


def _slugify(value: str, fallback: str) -> str:
    value = _transliterate_hebrew(value)
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return slug or fallback


def _transliterate_hebrew(value: str) -> str:
    words: list[str] = []
    for word in value.split():
        normalized_word = word.strip(".,:;!?()[]{}\"'")
        if normalized_word in HEBREW_WORD_SLUGS:
            words.append(HEBREW_WORD_SLUGS[normalized_word])
            continue
        words.append("".join(HEBREW_CHAR_SLUGS.get(char, char) for char in word))
    return " ".join(words)


def _preferred_slug(fields: dict[str, str], podcast_name: str, issue_number: int, *, required: bool = True) -> str:
    requested = _field(fields, "feed slug", "short english url name")
    slug = _optional(requested).lower()
    if not slug:
        if required:
            raise ValueError("Feed slug is required.")
        slug = _slugify(podcast_name, f"podcast-{issue_number}")
    if not SLUG_RE.match(slug):
        raise ValueError("Feed slug must use lowercase English letters, numbers, and hyphens.")
    return slug


def _available_auto_slug(slug: str, issue_number: int) -> str:
    if not (SHOWS_DIR / slug).exists():
        return slug
    return f"{slug}-{issue_number}"


def _folder_id_from_input(value: str) -> str:
    match = FOLDER_ID_RE.search(value.strip())
    if match:
        return match.group(1)
    return value.strip()


def _playlist_id_from_input(value: str) -> str:
    value = value.strip()
    match = PLAYLIST_ID_RE.search(value)
    if match:
        return match.group(1)
    return value


def _write_env(path: Path, values: dict[str, str]) -> None:
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")


def _has_supported_onboarding_label(labels: set[str]) -> bool:
    return bool({"drive-onboarding", "youtube-onboarding", "feed-onboarding"} & labels)


def _drive_source_config(source_url: str) -> dict[str, str]:
    return {
        "type": "drive",
        "folder_id": _folder_id_from_input(source_url),
        "filename_pattern": "date_dash_title",
    }


def _existing_feed_source_config(source_url: str) -> dict[str, Any]:
    return {
        "type": "existing_feed",
        "feed_url": source_url.strip(),
        "delivery_mode": "remote",
    }


def _existing_feed_auto_source_config(source_url: str) -> tuple[dict[str, Any], dict[str, str]]:
    return _existing_feed_source_config(source_url), extract_existing_feed_metadata(source_url)


def _youtube_source_config(source_url: str) -> tuple[dict[str, Any], dict[str, str]]:
    metadata = extract_channel_metadata(source_url)
    channel_id = metadata.get("id") or ""
    if not channel_id:
        raise ValueError(f"Could not resolve YouTube channel ID for {source_url}")
    return (
        {
            "type": "youtube",
            "channel_url": source_url.rstrip("/"),
            "channel_id": channel_id,
            "tabs": ["videos", "streams"],
            "scan_limit_per_tab": 300,
        },
        metadata,
    )


def _youtube_playlist_source_config(source_url: str) -> tuple[dict[str, Any], dict[str, str]]:
    playlist_id = _playlist_id_from_input(source_url)
    metadata = extract_playlist_metadata(playlist_id)
    return (
        {
            "type": "youtube_playlist",
            "playlist_id": playlist_id,
            "scan_limit_per_tab": 300,
        },
        metadata,
    )


def _looks_like_playlist(value: str) -> bool:
    return bool(PLAYLIST_ID_RE.search(value))


def _youtube_auto_source_config(source_url: str) -> tuple[dict[str, Any], dict[str, str]]:
    if _looks_like_playlist(source_url):
        return _youtube_playlist_source_config(source_url)
    return _youtube_source_config(source_url)


SOURCE_REQUESTS = (
    {
        "name": "youtube",
        "label": "youtube-onboarding",
        "token": "youtube",
        "fields": ("youtube url", "youtube channel url", "youtube playlist url"),
        "required": "YouTube URL",
        "builder": _youtube_auto_source_config,
    },
    {
        "name": "drive",
        "label": "drive-onboarding",
        "token": "drive",
        "fields": ("drive url", "google drive folder url"),
        "required": "Google Drive folder URL",
        "builder": lambda value: (_drive_source_config(value), {}),
    },
    {
        "name": "feed",
        "label": "feed-onboarding",
        "token": "feed",
        "fields": ("existing feed url", "existing podcast feed url", "podcast feed url"),
        "required": "Existing feed URL",
        "builder": _existing_feed_auto_source_config,
    },
)


def _first_metadata_value(source_metadata: list[dict[str, str]], key: str) -> str:
    return next((metadata.get(key, "") for metadata in source_metadata if metadata.get(key)), "")


def _requested_source_names(labels: set[str], source_type: str) -> set[str]:
    return {
        request["name"] for request in SOURCE_REQUESTS
        if request["label"] in labels or request["token"] in source_type
    }


def _requested_sources(
    *,
    labels: set[str],
    source_type: str,
    fields: dict[str, str],
    fallback_source_url: str | None,
    start_date: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    requested = [
        request for request in SOURCE_REQUESTS
        if request["label"] in labels or request["token"] in source_type
    ]
    source_configs: list[dict[str, Any]] = []
    source_metadata: list[dict[str, str]] = []
    for request in requested:
        source_url = _field(fields, *request["fields"])
        if not source_url and len(requested) == 1:
            source_url = fallback_source_url
        source_url = _require(source_url, request["required"])
        builder = request["builder"]
        source_config, metadata = builder(source_url)
        source_config["start_date"] = start_date
        source_configs.append(source_config)
        source_metadata.append(metadata)
    return source_configs, source_metadata


def _source_signature(source: dict[str, Any]) -> tuple[str, str]:
    source_type = str(source.get("type") or "youtube").lower()
    if source_type == "youtube":
        return source_type, str(source.get("channel_id") or source.get("channel_url") or "").rstrip("/")
    if source_type == "youtube_playlist":
        return source_type, str(source.get("playlist_id") or "")
    if source_type == "drive":
        return source_type, str(source.get("folder_id") or "")
    if source_type == "existing_feed":
        return source_type, str(source.get("feed_url") or "").rstrip("/")
    return source_type, repr(source)


def _source_list(raw: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(raw.get("sources"), list):
        return list(raw["sources"])
    source = raw.get("source")
    if isinstance(source, dict):
        return [source]
    return []


def _config_for_issue(issue: dict[str, Any], repo: str) -> tuple[str, str, dict[str, Any], bool]:
    body = issue.get("body") or ""
    number = int(issue["number"])
    fields = _field_map(body)

    labels = _issue_labels(issue)
    if "needs-approval" not in labels:
        raise OnboardingNotReady("Issue is not awaiting approval.")
    if "approved" not in labels:
        raise OnboardingNotReady("Issue does not have the approved label.")
    if not _has_supported_onboarding_label(labels):
        raise OnboardingNotReady("Issue is not a supported onboarding request.")

    source_type = _optional(_field(fields, "source type")).lower()
    fallback_source_url = _field(
        fields,
        "source url",
        "youtube channel url",
        "youtube playlist url",
        "google drive folder url",
        "existing feed url",
        "existing podcast feed url",
        "podcast feed url",
    )
    requested_sources = _requested_source_names(labels, source_type)
    feed_only_request = requested_sources == {"feed"}
    requested_author = _optional(_field(fields, "speaker / rabbi", "speaker / rabbi name"))
    requested_podcast_name = _optional(_field(fields, "podcast name", "podcast title"))
    requested_start_date = _optional(_field(fields, "start date"))
    start_date = requested_start_date or (DEFAULT_EXISTING_FEED_START_DATE if feed_only_request else "")
    start_date = _require(start_date, "Start date")
    date.fromisoformat(start_date)

    source_configs, source_metadata = _requested_sources(
        labels=labels,
        source_type=source_type,
        fields=fields,
        fallback_source_url=fallback_source_url,
        start_date=start_date,
    )

    if not source_configs:
        raise ValueError("No supported source was requested.")

    source_title = _first_metadata_value(source_metadata, "title")
    source_author = _first_metadata_value(source_metadata, "author")
    author = requested_author or source_author or requested_podcast_name or source_title
    if not author:
        raise ValueError("Speaker / rabbi is required when source author cannot be discovered.")
    podcast_name = requested_podcast_name or source_title or author
    requested_slug = _optional(_field(fields, "feed slug", "short english url name")).lower()
    slug = _preferred_slug(
        fields,
        podcast_name,
        number,
        required=not feed_only_request,
    )
    if not requested_slug:
        slug = _available_auto_slug(slug, number)

    description = _section(body, "Description")
    if not description or description == DEFAULT_DESCRIPTION:
        description = _first_metadata_value(source_metadata, "description") or podcast_name

    show_dir = SHOWS_DIR / slug
    if show_dir.exists():
        existing_path = show_dir / "config.yml"
        if not existing_path.exists():
            raise ValueError(f"Show slug directory exists without config.yml: {slug}")
        existing_config = yaml.safe_load(existing_path.read_text(encoding="utf-8")) or {}
        existing_sources = _source_list(existing_config)
        existing_signatures = {_source_signature(source) for source in existing_sources}
        added_sources = [
            source for source in source_configs
            if _source_signature(source) not in existing_signatures
        ]
        if not added_sources:
            raise OnboardingNotReady(f"All requested sources already exist for {slug}")
        existing_config.pop("source", None)
        existing_config["sources"] = existing_sources + added_sources
        onboarding = existing_config.setdefault("onboarding", {})
        source_issues = onboarding.setdefault("source_issues", [])
        source_issues.append(number)
        existing_path.write_text(
            yaml.safe_dump(existing_config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        if not (show_dir / "episodes.json").exists():
            (show_dir / "episodes.json").write_text("{}\n", encoding="utf-8")
        return slug, "", existing_config, False

    feed_url = f"{PUBLIC_BASE_URL}/{slug}/feed.xml"
    artwork_path = f"shows/{slug}/assets/podcast-cover.png"
    artwork_url = _optional(_field(fields, "artwork url")) or _first_metadata_value(source_metadata, "thumbnail")
    if not artwork_url:
        raise ValueError("Artwork URL is required when source artwork cannot be discovered.")
    website_url = (
        _optional(_field(fields, "youtube url", "youtube channel url", "youtube playlist url"))
        or _optional(_field(fields, "drive url", "google drive folder url"))
        or _first_metadata_value(source_metadata, "website_url")
        or _optional(_field(fields, "existing feed url", "existing podcast feed url", "podcast feed url"))
        or _optional(fallback_source_url)
        or feed_url
    )
    config = {
        "slug": slug,
        "enabled": True,
        "sources": source_configs,
        "podcast": {
            "title": podcast_name,
            "owner_name": OWNER_NAME,
            "owner_email": OWNER_EMAIL,
            "author": author,
            "description": description,
            "language": "he",
            "category": DEFAULT_CATEGORY,
            "subcategory": DEFAULT_SUBCATEGORY,
            "explicit": "no",
            "copyright": f"Copyright {date.today().year} {OWNER_NAME}. All rights reserved.",
            "website_url": website_url,
            "feed_url": feed_url,
            "artwork_path": artwork_path,
            "artwork_url": f"{PUBLIC_BASE_URL}/{slug}/assets/podcast-cover.png",
        },
        "r2": {"prefix": slug},
        "onboarding": {
            "issue": number,
            "issue_url": issue.get("url") or f"https://github.com/{repo}/issues/{number}",
        },
    }
    return slug, artwork_url, config, True


def onboard(issue_path: Path, repo: str, output_env: Path) -> int:
    issue = json.loads(issue_path.read_text(encoding="utf-8"))
    try:
        slug, artwork_url, config, created = _config_for_issue(issue, repo)
    except OnboardingNotReady as exc:
        print(f"Onboarding not ready: {exc}")
        _write_env(output_env, {"ONBOARDING_READY": "false"})
        return 0

    show_dir = SHOWS_DIR / slug
    show_dir.mkdir(parents=True, exist_ok=not created)
    if created:
        (show_dir / "config.yml").write_text(
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        (show_dir / "episodes.json").write_text("{}\n", encoding="utf-8")

    print(f"{'Created' if created else 'Updated'} show config for {slug}")
    _write_env(
        output_env,
        {
            "ONBOARDING_READY": "true",
            "SHOW_SLUG": slug,
            "ARTWORK_SOURCE_URL": artwork_url,
            "FEED_URL": config["podcast"]["feed_url"],
        },
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue-json", required=True, type=Path)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output-env", required=True, type=Path)
    args = parser.parse_args()

    if not str(ROOT):
        raise AssertionError("ROOT not resolved")
    return onboard(args.issue_json, args.repo, args.output_env)


if __name__ == "__main__":
    raise SystemExit(main())
