from __future__ import annotations

import argparse
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from email.utils import format_datetime, parsedate_to_datetime
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote

from feedgen.feed import FeedGenerator
from PIL import Image

from .config import ShowConfig, is_linked_existing_feed_show, load_enabled_shows, selected_shows
from .episodes import available_episodes, load_episodes
from .site import build_site

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_date(yyyymmdd: str) -> datetime:
    try:
        return datetime.strptime(yyyymmdd, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime(2000, 1, 1, tzinfo=timezone.utc)


def clean_text(value: str) -> str:
    return "\n".join(line.rstrip() for line in str(value).strip().splitlines())


def build_feed(show: ShowConfig, episodes: list[dict]) -> FeedGenerator:
    podcast = show.podcast
    feed = FeedGenerator()
    feed.load_extension("podcast")
    feed.id(podcast.feed_url)
    feed.title(podcast.title)
    feed.description(podcast.description)
    feed.author({"name": podcast.author})
    feed.link(href=podcast.feed_url, rel="self")
    feed.link(href=podcast.website_url, rel="alternate")
    feed.language(podcast.language)
    feed.copyright(podcast.copyright)
    feed.image(podcast.artwork_url)
    if podcast.subcategory:
        feed.podcast.itunes_category(podcast.category, podcast.subcategory)
    else:
        feed.podcast.itunes_category(podcast.category)
    feed.podcast.itunes_explicit(podcast.explicit)
    feed.podcast.itunes_author(podcast.author)
    feed.podcast.itunes_image(podcast.artwork_url)
    if podcast.owner_email:
        feed.podcast.itunes_owner(name=podcast.owner_name, email=podcast.owner_email)

    # feedgen serializes entries in reverse insertion order.
    for episode in reversed(episodes):
        title = clean_text(episode["title"])
        description = clean_text(episode.get("description") or title)
        entry = feed.add_entry()
        entry.id(episode.get("guid") or f"yt:video:{episode['id']}")
        entry.title(title)
        entry.description(description)
        entry.link(href=episode.get("source_url") or show.podcast.website_url)
        published = parse_date(episode["published"])
        entry.published(published)
        entry.updated(published)
        entry.enclosure(episode["url"], str(episode["size"]), episode.get("mime_type") or "audio/mpeg")
        entry.podcast.itunes_duration(episode.get("duration") or 0)
        entry.podcast.itunes_explicit("no")
    return feed


def add_channel_metadata(
    xml_bytes: bytes,
    show: ShowConfig,
    episodes: list[dict],
    *,
    previous_xml: bytes | None = None,
) -> bytes:
    ET.register_namespace("itunes", ITUNES_NS)
    ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
    ET.register_namespace("content", "http://purl.org/rss/1.0/modules/content/")
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    if channel is None:
        raise ValueError("Generated RSS has no channel element")

    def set_or_update(tag: str, value: str) -> None:
        element = channel.find(tag)
        if element is None:
            element = ET.SubElement(channel, tag)
        element.text = value

    # Reuse the prior publication date only when every emitted byte is unchanged.
    # A backdated title or enclosure correction then gets a new date, while an
    # empty CI run does not rewrite every feed merely because time passed.
    previous_date = None
    previous_instant = None
    if previous_xml:
        try:
            previous_date = ET.fromstring(previous_xml).findtext("channel/lastBuildDate")
            if previous_date:
                previous_instant = parsedate_to_datetime(previous_date)
                if previous_instant.tzinfo is None:
                    raise ValueError("RSS lastBuildDate must include a timezone")
        except (ET.ParseError, TypeError, ValueError):
            previous_date = None
    first_date = max(
        (parse_date(str(episode.get("published") or "")) for episode in episodes),
        default=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )
    last_build_date = previous_date or format_datetime(first_date)
    set_or_update("lastBuildDate", last_build_date)
    set_or_update(f"{{{ITUNES_NS}}}type", "episodic")
    set_or_update(f"{{{ITUNES_NS}}}summary", show.podcast.description)
    set_or_update(f"{{{ITUNES_NS}}}new-feed-url", show.podcast.feed_url)
    if show.podcast.owner_email:
        # Keep standard RSS contact fields alongside the iTunes owner block.
        # Some directory validators only inspect these channel-level fields.
        set_or_update("managingEditor", show.podcast.owner_email)
        set_or_update("webMaster", show.podcast.owner_email)
    ET.indent(root, space="  ")
    rendered = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    if previous_xml and rendered != previous_xml:
        build_instant = os.environ.get("TORAH_POD_BUILD_INSTANT")
        if os.environ.get("TORAH_POD_RELEASE_RENDER") == "1" and not build_instant:
            raise ValueError("Release render requires TORAH_POD_BUILD_INSTANT for changed feed bytes")
        changed_at = datetime.fromisoformat(build_instant.replace("Z", "+00:00")) if build_instant else datetime.now(timezone.utc)
        if changed_at.tzinfo is None:
            raise ValueError("TORAH_POD_BUILD_INSTANT must include a timezone")
        changed_at = changed_at.astimezone(timezone.utc)
        if previous_instant is not None:
            changed_at = max(changed_at, previous_instant + timedelta(seconds=1))
        set_or_update("lastBuildDate", format_datetime(changed_at))
        rendered = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return rendered


def build_show(show: ShowConfig) -> None:
    if not show.podcast.artwork_path.exists():
        raise FileNotFoundError(f"Missing artwork: {show.podcast.artwork_path}")

    show.public_dir.mkdir(parents=True, exist_ok=True)
    artwork_dest = show.public_dir / "assets" / "podcast-cover.png"
    artwork_url_name = unquote(Path(urlparse(show.podcast.artwork_url).path).name)
    if artwork_url_name:
        artwork_dest = show.public_dir / "assets" / artwork_url_name
    artwork_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(show.podcast.artwork_path, artwork_dest)
    with Image.open(show.podcast.artwork_path) as image:
        image.thumbnail((384, 384), Image.Resampling.LANCZOS)
        image.save(show.public_dir / "assets" / "podcast-cover.webp", "WEBP", quality=85, method=6)

    if is_linked_existing_feed_show(show):
        feed_path = show.public_dir / "feed.xml"
        if feed_path.exists():
            feed_path.unlink()
        print(f"{feed_path} skipped for linked existing feed")
        return

    episodes = sorted(
        available_episodes(load_episodes(show.episodes_path)),
        key=lambda episode: episode["published"],
        reverse=True,
    )

    feed_path = show.public_dir / "feed.xml"
    previous_xml = feed_path.read_bytes() if feed_path.exists() else None
    xml = add_channel_metadata(
        build_feed(show, episodes).rss_str(pretty=True),
        show,
        episodes,
        previous_xml=previous_xml,
    )
    feed_path.write_bytes(xml)
    # Keep a stable alternate path for directories that cache a failed parse
    # of the canonical feed URL. It is regenerated with the same XML each run.
    (show.public_dir / "spotify.xml").write_bytes(xml)
    print(f"{feed_path} written with {len(episodes)} episode(s)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", help="Show slug. Omit to build all enabled shows.")
    args = parser.parse_args()
    for show in selected_shows(args.show):
        build_show(show)
    build_site(load_enabled_shows())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
