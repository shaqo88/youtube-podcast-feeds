from __future__ import annotations

import argparse
import io
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from PIL import Image

from .config import ShowConfig, selected_shows
from .episodes import available_episodes, load_episodes

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM_NS = "http://www.w3.org/2005/Atom"
MIN_ARTWORK_SIZE = 1400
MAX_ARTWORK_SIZE = 3000
HTTP_TIMEOUT = 30
NETWORK_WORKERS = 8
USER_AGENT = "torah-pod-feed-validator/1.0"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def text(parent: ET.Element, path: str) -> str:
    node = parent.find(path)
    return (node.text or "").strip() if node is not None else ""


def validate_artwork_image(image: Image.Image, source: str) -> None:
    width, height = image.size
    require(width == height, f"{source}: artwork must be square, got {width}x{height}")
    require(
        MIN_ARTWORK_SIZE <= width <= MAX_ARTWORK_SIZE,
        f"{source}: artwork must be {MIN_ARTWORK_SIZE}-{MAX_ARTWORK_SIZE}px, got {width}px",
    )


def parse_feed(path) -> ET.Element:
    require(path.exists(), f"Missing feed: {path}")
    root = ET.parse(path).getroot()
    channel = root.find("channel")
    require(channel is not None, f"{path}: missing channel")
    return channel


def validate_local_show(show: ShowConfig) -> dict[str, dict[str, str]]:
    with Image.open(show.podcast.artwork_path) as image:
        image.verify()
    with Image.open(show.podcast.artwork_path) as image:
        validate_artwork_image(image, str(show.podcast.artwork_path))

    episodes_by_id = {
        episode["id"]: episode
        for episode in available_episodes(load_episodes(show.episodes_path))
    }
    episodes_by_guid = {
        episode.get("guid") or f"yt:video:{episode['id']}": episode
        for episode in episodes_by_id.values()
    }
    feed_path = show.public_dir / "feed.xml"
    channel = parse_feed(feed_path)
    require(text(channel, "title") == show.podcast.title, f"{feed_path}: incorrect title")
    require(text(channel, "description") == show.podcast.description, f"{feed_path}: incorrect description")
    require(text(channel, "language") == show.podcast.language, f"{feed_path}: incorrect language")
    require(text(channel, f"{{{ITUNES_NS}}}summary") == show.podcast.description, f"{feed_path}: incorrect summary")
    require(text(channel, f"{{{ITUNES_NS}}}type") == "episodic", f"{feed_path}: itunes:type must be episodic")
    require(
        text(channel, f"{{{ITUNES_NS}}}explicit").lower() in {"false", "no"},
        f"{feed_path}: itunes:explicit must be false/no",
    )

    self_urls = {
        link.get("href")
        for link in channel.findall(f"{{{ATOM_NS}}}link")
        if link.get("rel") == "self"
    }
    require(show.podcast.feed_url in self_urls, f"{feed_path}: missing atom self link")

    itunes_image = channel.find(f"{{{ITUNES_NS}}}image")
    require(itunes_image is not None, f"{feed_path}: missing itunes:image")
    require(itunes_image.get("href") == show.podcast.artwork_url, f"{feed_path}: incorrect artwork URL")

    items = channel.findall("item")
    require(len(items) == len(episodes_by_id), f"{feed_path}: expected {len(episodes_by_id)} items, found {len(items)}")

    enclosures: dict[str, dict[str, str]] = {}
    guids: list[str] = []
    for item in items:
        guid = text(item, "guid")
        require(
            guid.startswith("yt:video:") or guid.startswith("drive:file:") or guid.startswith("feed:item:"),
            f"{feed_path}: unexpected GUID {guid}",
        )
        episode = episodes_by_guid.get(guid)
        require(episode is not None, f"{feed_path}: unknown episode GUID {guid}")
        expected_guid = episode.get("guid") or f"yt:video:{episode['id']}"
        require(guid == expected_guid, f"{feed_path}: {guid} GUID mismatch")
        enclosure = item.find("enclosure")
        expected_type = episode.get("mime_type") or "audio/mpeg"
        require(enclosure is not None, f"{feed_path}: {guid} missing enclosure")
        require(enclosure.get("url") == episode["url"], f"{feed_path}: {guid} enclosure URL mismatch")
        require(enclosure.get("length") == str(episode["size"]), f"{feed_path}: {guid} enclosure length mismatch")
        require(enclosure.get("type") == expected_type, f"{feed_path}: {guid} enclosure type mismatch")
        guids.append(guid)
        enclosures[guid] = {
            "url": enclosure.get("url") or "",
            "mime_type": expected_type,
            "source_type": str(episode.get("source_type") or ""),
            "delivery_mode": str(episode.get("delivery_mode") or ""),
        }

    require(len(guids) == len(set(guids)), f"{feed_path}: duplicate GUIDs")
    enclosure_urls = [enclosure["url"] for enclosure in enclosures.values()]
    require(len(enclosure_urls) == len(set(enclosure_urls)), f"{feed_path}: duplicate enclosure URLs")
    print(f"{show.slug}: local feed validation passed")
    return enclosures


def validate_public_feed(show: ShowConfig, expected_guids: set[str]) -> None:
    response = requests.get(show.podcast.feed_url, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    channel = ET.fromstring(response.content).find("channel")
    require(channel is not None, f"{show.slug}: public feed has no channel")
    public_guids = {text(item, "guid") for item in channel.findall("item")}
    require(public_guids == expected_guids, f"{show.slug}: public feed GUIDs do not match local feed")


def validate_public_artwork(show: ShowConfig) -> None:
    response = requests.get(show.podcast.artwork_url, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    with Image.open(io.BytesIO(response.content)) as image:
        image.verify()
    with Image.open(io.BytesIO(response.content)) as image:
        validate_artwork_image(image, show.podcast.artwork_url)


def _validate_content_type(url: str, expected_type: str, response: requests.Response) -> None:
    content_type = response.headers.get("Content-Type", "").lower()
    require(content_type.startswith(expected_type.lower()), f"{url}: invalid Content-Type")


def validate_enclosure(url: str, expected_type: str, *, require_range: bool) -> str:
    if not require_range:
        response = requests.head(url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT, allow_redirects=True)
        if response.status_code >= 400:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT, stream=True)
        try:
            require(response.status_code < 400, f"{url}: request returned {response.status_code}")
            _validate_content_type(url, expected_type, response)
            if response.request.method != "HEAD":
                next(response.iter_content(chunk_size=1), b"")
        finally:
            response.close()
        return url

    headers = {"Range": "bytes=0-0", "User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT, stream=True)
    try:
        require(response.status_code == 206, f"{url}: range request returned {response.status_code}")
        require(response.headers.get("Content-Range", "").startswith("bytes 0-0/"), f"{url}: invalid Content-Range")
        _validate_content_type(url, expected_type, response)
        next(response.iter_content(chunk_size=1), b"")
    finally:
        response.close()
    return url


def validate_network_show(show: ShowConfig, enclosures: dict[str, dict[str, str]]) -> None:
    validate_public_feed(show, set(enclosures))
    validate_public_artwork(show)
    failures = []
    with ThreadPoolExecutor(max_workers=NETWORK_WORKERS) as executor:
        future_urls = {
            executor.submit(
                validate_enclosure,
                enclosure["url"],
                enclosure["mime_type"],
                require_range=not (
                    enclosure["source_type"] == "existing_feed"
                    and enclosure["delivery_mode"] == "remote"
                ),
            ): enclosure["url"]
            for enclosure in enclosures.values()
        }
        for future in as_completed(future_urls):
            try:
                future.result()
            except Exception as exc:
                failures.append(str(exc))
    require(not failures, f"{show.slug}: enclosure validation failed:\n" + "\n".join(failures))
    print(f"{show.slug}: public validation passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", help="Show slug. Omit to validate all enabled shows.")
    parser.add_argument("--network", action="store_true", help="Validate published feed, artwork, and R2 media.")
    args = parser.parse_args()
    try:
        for show in selected_shows(args.show):
            enclosures = validate_local_show(show)
            if args.network:
                validate_network_show(show, enclosures)
    except (OSError, ValueError, requests.RequestException, ET.ParseError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
