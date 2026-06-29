from __future__ import annotations

import hashlib
import mimetypes
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

HTTP_TIMEOUT = 45
USER_AGENT = "torah-pod-feed-importer/1.0"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ITUNES_NS = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


@dataclass(frozen=True)
class ExistingFeedItem:
    id: str
    guid: str
    title: str
    description: str
    published: str
    duration: int
    enclosure_url: str
    enclosure_type: str
    source_url: str


@dataclass(frozen=True)
class ExistingFeedMetadata:
    title: str = ""
    description: str = ""
    author: str = ""
    thumbnail: str = ""
    website_url: str = ""


def stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _text(parent: ET.Element, tag: str) -> str:
    node = parent.find(tag)
    return (node.text or "").strip() if node is not None else ""


def _strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


def _rss_metadata(root: ET.Element, feed_url: str) -> ExistingFeedMetadata:
    channel = root.find("channel")
    if channel is None:
        return ExistingFeedMetadata()
    image = channel.find("image")
    image_url = _text(image, "url") if image is not None else ""
    itunes_image = channel.find(f"{ITUNES_NS}image")
    artwork_url = (itunes_image.get("href") if itunes_image is not None else "") or image_url
    return ExistingFeedMetadata(
        title=_text(channel, "title"),
        description=_strip_html(_text(channel, "description") or _text(channel, f"{ITUNES_NS}summary")),
        author=_text(channel, f"{ITUNES_NS}author") or _strip_html(_text(channel, "managingEditor")),
        thumbnail=urljoin(feed_url, artwork_url) if artwork_url else "",
        website_url=urljoin(feed_url, _text(channel, "link")) if _text(channel, "link") else "",
    )


def _atom_metadata(root: ET.Element, feed_url: str) -> ExistingFeedMetadata:
    website_url = ""
    for link in root.findall(f"{ATOM_NS}link"):
        rel = link.get("rel") or "alternate"
        href = link.get("href") or ""
        if rel == "alternate" and href:
            website_url = href
            break
    author = root.find(f"{ATOM_NS}author")
    author_name = _text(author, f"{ATOM_NS}name") if author is not None else ""
    artwork_url = _text(root, f"{ATOM_NS}logo") or _text(root, f"{ATOM_NS}icon")
    return ExistingFeedMetadata(
        title=_text(root, f"{ATOM_NS}title"),
        description=_strip_html(_text(root, f"{ATOM_NS}subtitle") or _text(root, f"{ATOM_NS}summary")),
        author=author_name,
        thumbnail=urljoin(feed_url, artwork_url) if artwork_url else "",
        website_url=urljoin(feed_url, website_url) if website_url else "",
    )


def _parse_date(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "20000101"
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return "20000101"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y%m%d")


def _parse_duration(value: str) -> int:
    value = (value or "").strip()
    if not value:
        return 0
    if value.isdigit():
        return int(value)
    parts = value.split(":")
    if not all(part.isdigit() for part in parts):
        return 0
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return total


def _rss_items(root: ET.Element) -> list[ExistingFeedItem]:
    channel = root.find("channel")
    if channel is None:
        return []
    items: list[ExistingFeedItem] = []
    for item in channel.findall("item"):
        enclosure = item.find("enclosure")
        enclosure_url = (enclosure.get("url") if enclosure is not None else "") or ""
        if not enclosure_url:
            continue
        upstream_guid = _text(item, "guid") or enclosure_url
        item_id = stable_id(upstream_guid)
        title = _text(item, "title") or f"Episode {item_id}"
        description = _strip_html(_text(item, "description") or _text(item, f"{ITUNES_NS}summary") or title)
        items.append(
            ExistingFeedItem(
                id=item_id,
                guid=f"feed:item:{item_id}",
                title=title,
                description=description or title,
                published=_parse_date(_text(item, "pubDate")),
                duration=_parse_duration(_text(item, f"{ITUNES_NS}duration")),
                enclosure_url=enclosure_url,
                enclosure_type=(enclosure.get("type") if enclosure is not None else "") or "",
                source_url=_text(item, "link"),
            )
        )
    return items


def _atom_items(root: ET.Element) -> list[ExistingFeedItem]:
    items: list[ExistingFeedItem] = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        enclosure_url = ""
        enclosure_type = ""
        source_url = ""
        for link in entry.findall(f"{ATOM_NS}link"):
            rel = link.get("rel") or "alternate"
            href = link.get("href") or ""
            if rel == "enclosure" and href:
                enclosure_url = href
                enclosure_type = link.get("type") or ""
            elif rel == "alternate" and href and not source_url:
                source_url = href
        if not enclosure_url:
            continue
        upstream_guid = _text(entry, f"{ATOM_NS}id") or enclosure_url
        item_id = stable_id(upstream_guid)
        title = _text(entry, f"{ATOM_NS}title") or f"Episode {item_id}"
        description = _strip_html(_text(entry, f"{ATOM_NS}summary") or _text(entry, f"{ATOM_NS}content") or title)
        items.append(
            ExistingFeedItem(
                id=item_id,
                guid=f"feed:item:{item_id}",
                title=title,
                description=description or title,
                published=_parse_date(_text(entry, f"{ATOM_NS}published") or _text(entry, f"{ATOM_NS}updated")),
                duration=0,
                enclosure_url=enclosure_url,
                enclosure_type=enclosure_type,
                source_url=source_url,
            )
        )
    return items


def list_existing_feed_items(feed_url: str, limit: int | None = None) -> list[ExistingFeedItem]:
    response = requests.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items = _rss_items(root) or _atom_items(root)
    if limit:
        return items[:limit]
    return items


def extract_existing_feed_metadata(feed_url: str) -> dict[str, str]:
    response = requests.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    metadata = _rss_metadata(root, feed_url) or _atom_metadata(root, feed_url)
    if not metadata.title:
        metadata = _atom_metadata(root, feed_url)
    return {
        "title": metadata.title,
        "description": metadata.description,
        "author": metadata.author,
        "thumbnail": metadata.thumbnail,
        "website_url": metadata.website_url,
    }


def download_existing_enclosure(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT, stream=True) as response:
        response.raise_for_status()
        with dest.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)


def enclosure_extension(url: str, content_type: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix:
        return suffix
    guessed = mimetypes.guess_extension(content_type.split(";")[0].strip()) if content_type else None
    return (guessed or ".mp3").lstrip(".")
