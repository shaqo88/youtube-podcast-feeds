"""Versioned public episode pages and last-good linked-feed snapshots."""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

PAGE_SIZE = 20
SNAPSHOT_FIELDS = {
    "id", "guid", "title", "description", "published", "duration", "url", "size",
    "mime_type", "source_url", "source_type", "delivery_mode", "source_enclosure_url",
    "source_enclosure_type",
}


def validated_episodes(items: object) -> list[dict]:
    if not isinstance(items, list):
        raise ValueError("Expected an episode array")
    result = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid episode metadata")
        identity = str(item.get("guid") or item.get("id") or "")
        url = urlparse(str(item.get("url") or ""))
        if not identity or not isinstance(item.get("title"), str) or url.scheme not in {"https", "http"} or not url.netloc or url.username or url.password:
            raise ValueError("Invalid public episode identity or enclosure")
        duration = item.get("duration") or 0
        if not isinstance(duration, (int, float)) or duration < 0:
            raise ValueError("Invalid episode duration")
        if identity in seen:
            continue
        seen.add(identity)
        result.append({key: value for key, value in item.items() if key in SNAPSHOT_FIELDS})
    return sorted(result, key=lambda item: str(item.get("published") or ""), reverse=True)


def snapshot_path(public_dir: Path, slug: str, feed_url: str) -> Path:
    key = hashlib.sha256(feed_url.encode("utf-8")).hexdigest()[:20]
    return public_dir / "metadata" / "v1" / "snapshots" / slug / f"{key}.json"


def read_snapshot(path: Path) -> list[dict] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            return None
        return validated_episodes(payload["episodes"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def write_snapshot(path: Path, items: list[dict]) -> list[dict]:
    episodes = validated_episodes(items)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "episodes": episodes}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return episodes


def legacy_snapshot(public_dir: Path, slug: str) -> list[dict]:
    """Bootstrap retention from the previously generated, validated search index."""
    try:
        payload = json.loads((public_dir / "search-index.json").read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            return []
        items = [
            {"id": item["id"].removeprefix(f"{slug}:"), "guid": item["id"].removeprefix(f"{slug}:"),
             "title": item["title"], "published": item.get("published", ""),
             "duration": item.get("duration", 0), "url": item["audio_url"], "delivery_mode": "linked"}
            for item in payload["episodes"] if item.get("show_slug") == slug
        ]
        # Keep the existing episode descriptions during the first offline upgrade.
        by_id = {item["id"]: item for item in items}
        for page in (public_dir / slug / "episodes").glob("*/index.html"):
            markup = page.read_text(encoding="utf-8")
            identity = re.search(r'data-episode-id="([^"]+)"', markup)
            description = re.search(r'data-episode-description="([^"]*)"', markup)
            if identity and description:
                item = by_id.get(html.unescape(identity[1]).removeprefix(f"{slug}:"))
                if item is not None:
                    item["description"] = html.unescape(description[1])
        return validated_episodes(items)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []


def write_episode_pages(public_dir: Path, slug: str, items: list[dict]) -> dict:
    directory = public_dir / "metadata" / "v1" / "shows" / slug
    directory.mkdir(parents=True, exist_ok=True)
    unique = {item["id"]: item for item in reversed(items)}
    episodes = sorted(unique.values(), key=lambda item: (item["published"], item["id"]), reverse=True)
    pages = max(1, (len(episodes) + PAGE_SIZE - 1) // PAGE_SIZE)
    for page in range(pages):
        payload = {"schema_version": 1, "show_slug": slug, "page": page + 1, "page_size": PAGE_SIZE,
                   "total": len(episodes), "next_page": page + 2 if page + 1 < pages else None,
                   "episodes": episodes[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]}
        (directory / f"{page + 1}.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return {"slug": slug, "total": len(episodes), "latest": episodes[:PAGE_SIZE], "pages": pages}
