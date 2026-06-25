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
from .youtube import extract_channel_metadata

OWNER_NAME = "Torah Pod"
OWNER_EMAIL = "torahyoupod@gmail.com"
PUBLIC_BASE_URL = "https://shaqo88.github.io/youtube-podcast-feeds"
DEFAULT_CATEGORY = "Religion & Spirituality"
DEFAULT_SUBCATEGORY = "Judaism"
DEFAULT_DESCRIPTION = "Use source description if available."
FOLDER_ID_RE = re.compile(r"/folders/([^/?#]+)")
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


def _preferred_slug(fields: dict[str, str], podcast_name: str, issue_number: int) -> str:
    requested = _field(fields, "feed slug", "short english url name")
    slug = _optional(requested).lower()
    if not slug:
        raise ValueError("Feed slug is required.")
    if not SLUG_RE.match(slug):
        raise ValueError("Feed slug must use lowercase English letters, numbers, and hyphens.")
    return slug


def _folder_id_from_input(value: str) -> str:
    match = FOLDER_ID_RE.search(value.strip())
    if match:
        return match.group(1)
    return value.strip()


def _write_env(path: Path, values: dict[str, str]) -> None:
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")


def _source_kind(labels: set[str]) -> str:
    if "drive-onboarding" in labels:
        return "drive"
    if "youtube-onboarding" in labels:
        return "youtube"
    raise OnboardingNotReady("Issue is not a supported onboarding request.")


def _drive_source_config(source_url: str) -> dict[str, str]:
    return {
        "type": "drive",
        "folder_id": _folder_id_from_input(source_url),
        "filename_pattern": "date_dash_title",
    }


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
            "tabs": ["videos", "streams", "shorts"],
            "scan_limit_per_tab": 300,
        },
        metadata,
    )


def _config_for_issue(issue: dict[str, Any], repo: str) -> tuple[str, str, dict[str, Any]]:
    body = issue.get("body") or ""
    number = int(issue["number"])
    fields = _field_map(body)

    labels = _issue_labels(issue)
    if "needs-approval" not in labels:
        raise OnboardingNotReady("Issue is not awaiting approval.")
    if "approved" not in labels:
        raise OnboardingNotReady("Issue does not have the approved label.")

    source_kind = _source_kind(labels)

    source_url = _require(
        _field(fields, "source url", "youtube channel url", "google drive folder url"),
        "Source URL",
    )
    author = _require(_field(fields, "speaker / rabbi", "speaker / rabbi name"), "Speaker / rabbi")
    podcast_name = _optional(_field(fields, "podcast name", "podcast title")) or author
    start_date = _require(_field(fields, "start date"), "Start date")
    date.fromisoformat(start_date)
    slug = _preferred_slug(fields, podcast_name, number)

    channel_metadata: dict[str, str] = {}
    if source_kind == "drive":
        source_config = _drive_source_config(source_url)
    else:
        source_config, channel_metadata = _youtube_source_config(source_url)

    source_config["start_date"] = start_date
    artwork_url = _optional(_field(fields, "artwork url")) or channel_metadata.get("thumbnail") or ""
    if not artwork_url:
        raise ValueError("Artwork URL is required when source artwork cannot be discovered.")

    description = _section(body, "Description")
    if not description or description == DEFAULT_DESCRIPTION:
        description = channel_metadata.get("description") or podcast_name

    show_dir = SHOWS_DIR / slug
    if show_dir.exists():
        existing = show_dir / "config.yml"
        if existing.exists():
            raw = yaml.safe_load(existing.read_text(encoding="utf-8")) or {}
            if raw.get("onboarding", {}).get("issue") == number:
                raise OnboardingNotReady(f"Show already exists for issue #{number}: {slug}")
        raise ValueError(f"Show slug already exists and is not owned by this issue: {slug}")

    feed_url = f"{PUBLIC_BASE_URL}/{slug}/feed.xml"
    artwork_path = f"shows/{slug}/assets/podcast-cover.png"
    config = {
        "slug": slug,
        "enabled": True,
        "source": source_config,
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
            "website_url": source_url,
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
    return slug, artwork_url, config


def onboard(issue_path: Path, repo: str, output_env: Path) -> int:
    issue = json.loads(issue_path.read_text(encoding="utf-8"))
    try:
        slug, artwork_url, config = _config_for_issue(issue, repo)
    except OnboardingNotReady as exc:
        print(f"Onboarding not ready: {exc}")
        _write_env(output_env, {"ONBOARDING_READY": "false"})
        return 0

    show_dir = SHOWS_DIR / slug
    show_dir.mkdir(parents=True, exist_ok=False)
    (show_dir / "config.yml").write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (show_dir / "episodes.json").write_text("{}\n", encoding="utf-8")

    print(f"Created show config for {slug}")
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
