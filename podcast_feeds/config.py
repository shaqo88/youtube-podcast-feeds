from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SHOWS_DIR = ROOT / "shows"
PUBLIC_DIR = ROOT / "public"


@dataclass(frozen=True)
class SourceConfig:
    type: str
    feed_url: str | None
    delivery_mode: str
    channel_url: str
    channel_id: str | None
    playlist_id: str | None
    tabs: tuple[str, ...]
    start_date: date
    scan_limit_per_tab: int | None
    folder_id: str | None
    filename_pattern: str | None


@dataclass(frozen=True)
class PodcastConfig:
    title: str
    owner_name: str
    owner_email: str | None
    author: str
    description: str
    language: str
    category: str
    subcategory: str | None
    explicit: str
    copyright: str
    website_url: str
    feed_url: str
    artwork_path: Path
    artwork_url: str


@dataclass(frozen=True)
class R2Config:
    prefix: str


@dataclass(frozen=True)
class ShowConfig:
    slug: str
    enabled: bool
    source: SourceConfig
    sources: tuple[SourceConfig, ...]
    podcast: PodcastConfig
    r2: R2Config
    show_dir: Path
    episodes_path: Path
    public_dir: Path


def _required(mapping: dict[str, Any], key: str) -> Any:
    value = mapping.get(key)
    if value in (None, ""):
        raise ValueError(f"Missing required config key: {key}")
    return value


def load_show(slug: str) -> ShowConfig:
    show_dir = SHOWS_DIR / slug
    config_path = show_dir / "config.yml"
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{config_path} must contain a mapping")

    source_values = raw.get("sources")
    if source_values is None:
        source_values = [_required(raw, "source")]
    if not isinstance(source_values, list) or not source_values:
        raise ValueError(f"{config_path}: sources must be a non-empty list")
    podcast_raw = _required(raw, "podcast")
    r2_raw = _required(raw, "r2")

    config_slug = _required(raw, "slug")
    if config_slug != slug:
        raise ValueError(f"{config_path}: slug {config_slug!r} must match directory {slug!r}")

    podcast = PodcastConfig(
        title=_required(podcast_raw, "title"),
        owner_name=_required(podcast_raw, "owner_name"),
        owner_email=podcast_raw.get("owner_email"),
        author=_required(podcast_raw, "author"),
        description=_required(podcast_raw, "description"),
        language=_required(podcast_raw, "language"),
        category=_required(podcast_raw, "category"),
        subcategory=podcast_raw.get("subcategory"),
        explicit=str(_required(podcast_raw, "explicit")).lower(),
        copyright=_required(podcast_raw, "copyright"),
        website_url=_required(podcast_raw, "website_url"),
        feed_url=_required(podcast_raw, "feed_url"),
        artwork_path=ROOT / _required(podcast_raw, "artwork_path"),
        artwork_url=_required(podcast_raw, "artwork_url"),
    )
    sources: list[SourceConfig] = []
    for source_raw in source_values:
        if not isinstance(source_raw, dict):
            raise ValueError(f"{config_path}: each source must be a mapping")
        start_date = date.fromisoformat(str(_required(source_raw, "start_date")))
        source_type = str(source_raw.get("type") or "youtube").lower()
        source = SourceConfig(
            type=source_type,
            feed_url=source_raw.get("feed_url"),
            delivery_mode=str(source_raw.get("delivery_mode") or "mirror").lower(),
            channel_url=str(source_raw.get("channel_url") or "").rstrip("/"),
            channel_id=source_raw.get("channel_id"),
            playlist_id=source_raw.get("playlist_id"),
            tabs=tuple(source_raw.get("tabs") or ("videos", "streams", "shorts")),
            start_date=start_date,
            scan_limit_per_tab=source_raw.get("scan_limit_per_tab"),
            folder_id=source_raw.get("folder_id"),
            filename_pattern=source_raw.get("filename_pattern"),
        )
        if source.type == "youtube":
            _required(source_raw, "channel_url")
            _required(source_raw, "channel_id")
        elif source.type == "youtube_playlist":
            _required(source_raw, "playlist_id")
        elif source.type == "drive":
            _required(source_raw, "folder_id")
            if source.filename_pattern not in (None, "date_dash_title"):
                raise ValueError(f"{config_path}: unsupported Drive filename_pattern {source.filename_pattern!r}")
        elif source.type == "existing_feed":
            _required(source_raw, "feed_url")
            if source.delivery_mode not in ("mirror", "remote"):
                raise ValueError(f"{config_path}: unsupported existing_feed delivery_mode {source.delivery_mode!r}")
        else:
            raise ValueError(f"{config_path}: unsupported source type {source.type!r}")
        sources.append(source)
    return ShowConfig(
        slug=slug,
        enabled=bool(raw.get("enabled", True)),
        source=sources[0],
        sources=tuple(sources),
        podcast=podcast,
        r2=R2Config(prefix=_required(r2_raw, "prefix").strip("/")),
        show_dir=show_dir,
        episodes_path=show_dir / "episodes.json",
        public_dir=PUBLIC_DIR / slug,
    )


def load_enabled_shows() -> list[ShowConfig]:
    shows = []
    for config_path in sorted(SHOWS_DIR.glob("*/config.yml")):
        show = load_show(config_path.parent.name)
        if show.enabled:
            shows.append(show)
    return shows


def selected_shows(slug: str | None) -> list[ShowConfig]:
    if slug:
        return [load_show(slug)]
    return load_enabled_shows()
