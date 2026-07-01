from __future__ import annotations

import argparse
import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import yaml

from .config import ShowConfig, selected_shows

APPLE_SEARCH_URL = "https://itunes.apple.com/search"
PODCAST_INDEX_API_URL = "https://api.podcastindex.org/api/1.0"


@dataclass(frozen=True)
class LinkCandidate:
    platform: str
    show_slug: str
    title: str
    url: str
    feed_url: str
    reason: str


@dataclass(frozen=True)
class DiscoveryError:
    platform: str
    show_slug: str
    message: str


def _normalize_url(value: str | None) -> str:
    return str(value or "").strip().rstrip("/")


def _platforms(config: dict[str, Any]) -> dict[str, str]:
    podcast = config.setdefault("podcast", {})
    platforms = podcast.setdefault("platforms", {})
    if not isinstance(platforms, dict):
        raise ValueError("podcast.platforms must be a mapping")
    return platforms


def _load_config(show: ShowConfig) -> dict[str, Any]:
    config_path = show.show_dir / "config.yml"
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{config_path} must contain a mapping")
    return raw


def _write_config(show: ShowConfig, config: dict[str, Any]) -> None:
    config_path = show.show_dir / "config.yml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _acceptable_feed_urls(show: ShowConfig) -> set[str]:
    urls = {_normalize_url(show.podcast.feed_url)}
    for source in show.sources:
        if source.type == "existing_feed" and source.feed_url:
            urls.add(_normalize_url(source.feed_url))
    return {url for url in urls if url}


def _apple_search(show: ShowConfig) -> list[dict[str, Any]]:
    terms = [
        show.podcast.title,
        f"{show.podcast.title} {show.podcast.author}",
    ]
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for term in terms:
        response = requests.get(
            APPLE_SEARCH_URL,
            params={"term": term, "entity": "podcast", "country": "il", "limit": 50},
            timeout=20,
        )
        response.raise_for_status()
        for result in response.json().get("results") or []:
            key = result.get("collectionViewUrl") or result.get("feedUrl")
            if not key or key in seen:
                continue
            seen.add(key)
            results.append(result)
    return results


def _discover_apple(show: ShowConfig) -> tuple[str | None, list[LinkCandidate]]:
    feed_urls = _acceptable_feed_urls(show)
    candidates: list[LinkCandidate] = []
    for result in _apple_search(show):
        feed_url = _normalize_url(result.get("feedUrl"))
        link_url = result.get("collectionViewUrl")
        if not feed_url or not link_url:
            continue
        if feed_url in feed_urls:
            return str(link_url), candidates
        candidates.append(
            LinkCandidate(
                platform="apple",
                show_slug=show.slug,
                title=str(result.get("collectionName") or ""),
                url=str(link_url),
                feed_url=feed_url,
                reason="title matched, RSS feed did not match",
            )
        )
    return None, candidates


def _podcast_index_headers() -> dict[str, str] | None:
    api_key = os.environ.get("PODCASTINDEX_API_KEY", "").strip()
    api_secret = os.environ.get("PODCASTINDEX_API_SECRET", "").strip()
    if not api_key or not api_secret:
        return None
    auth_date = str(int(time.time()))
    auth_hash = hashlib.sha1((api_key + api_secret + auth_date).encode("utf-8")).hexdigest()
    return {
        "User-Agent": "TorahPodPlatformLinkDiscovery/1.0",
        "X-Auth-Key": api_key,
        "X-Auth-Date": auth_date,
        "Authorization": auth_hash,
    }


def _discover_podcast_index(show: ShowConfig) -> str | None:
    headers = _podcast_index_headers()
    if not headers:
        return None
    for feed_url in _acceptable_feed_urls(show):
        response = requests.get(
            f"{PODCAST_INDEX_API_URL}/podcasts/byfeedurl",
            params={"url": feed_url},
            headers=headers,
            timeout=20,
        )
        if response.status_code == 404:
            continue
        response.raise_for_status()
        feed = response.json().get("feed") or {}
        feed_id = feed.get("id")
        if feed_id:
            return f"https://podcastindex.org/podcast/{feed_id}"
    return None


def _set_platform(platforms: dict[str, str], key: str, value: str | None) -> bool:
    if not value:
        return False
    if platforms.get(key) == value:
        return False
    platforms[key] = value
    return True


def discover(show: ShowConfig, *, write: bool) -> tuple[list[str], list[LinkCandidate], list[DiscoveryError]]:
    config = _load_config(show)
    platforms = _platforms(config)
    updates: list[str] = []
    candidates: list[LinkCandidate] = []
    errors: list[DiscoveryError] = []

    try:
        apple_url, apple_candidates = _discover_apple(show)
        candidates.extend(apple_candidates)
        if _set_platform(platforms, "apple", apple_url):
            updates.append(f"{show.slug}: apple")
    except requests.RequestException as exc:
        errors.append(DiscoveryError("apple", show.slug, str(exc)))

    try:
        podcast_index_url = _discover_podcast_index(show)
        if _set_platform(platforms, "podcast_index", podcast_index_url):
            updates.append(f"{show.slug}: podcast_index")
    except requests.RequestException as exc:
        errors.append(DiscoveryError("podcast_index", show.slug, str(exc)))

    if write and updates:
        _write_config(show, config)
    return updates, candidates, errors


def _report(updates: list[str], candidates: list[LinkCandidate], errors: list[DiscoveryError]) -> str:
    lines = ["# Platform Link Discovery", ""]
    if updates:
        lines.append("## Auto-updated exact RSS matches")
        lines.extend(f"- {update}" for update in updates)
        lines.append("")
    else:
        lines.extend(["## Auto-updated exact RSS matches", "- None", ""])

    lines.append("## Manual review candidates")
    if candidates:
        for candidate in candidates:
            lines.extend(
                [
                    f"- Show: `{candidate.show_slug}`",
                    f"  Platform: `{candidate.platform}`",
                    f"  Title: {candidate.title}",
                    f"  URL: {candidate.url}",
                    f"  Candidate feed: {candidate.feed_url}",
                    f"  Reason: {candidate.reason}",
                ]
            )
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Discovery errors")
    if errors:
        for error in errors:
            lines.extend(
                [
                    f"- Show: `{error.show_slug}`",
                    f"  Platform: `{error.platform}`",
                    f"  Error: {error.message}",
                ]
            )
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", help="Show slug. Omit to scan all enabled shows.")
    parser.add_argument("--write", action="store_true", help="Write exact verified platform links into show config.")
    parser.add_argument("--report", type=Path, help="Markdown report path.")
    args = parser.parse_args()

    all_updates: list[str] = []
    all_candidates: list[LinkCandidate] = []
    all_errors: list[DiscoveryError] = []
    for show in selected_shows(args.show):
        updates, candidates, errors = discover(show, write=args.write)
        all_updates.extend(updates)
        all_candidates.extend(candidates)
        all_errors.extend(errors)

    report = _report(all_updates, all_candidates, all_errors)
    print(report)
    if args.report:
        args.report.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
