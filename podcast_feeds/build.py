from __future__ import annotations

import argparse
import shutil
import sys
import xml.etree.ElementTree as ET
from email.utils import format_datetime
from datetime import datetime, timezone

from feedgen.feed import FeedGenerator

from .config import ShowConfig, selected_shows
from .episodes import available_episodes, load_episodes

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_date(yyyymmdd: str) -> datetime:
    try:
        return datetime.strptime(yyyymmdd, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime(2000, 1, 1, tzinfo=timezone.utc)


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

    for episode in episodes:
        entry = feed.add_entry()
        entry.id(f"yt:video:{episode['id']}")
        entry.title(episode["title"])
        entry.description(episode.get("description") or episode["title"])
        entry.link(href=episode.get("source_url") or f"https://www.youtube.com/watch?v={episode['id']}")
        published = parse_date(episode["published"])
        entry.published(published)
        entry.updated(published)
        entry.enclosure(episode["url"], str(episode["size"]), "audio/mpeg")
        entry.podcast.itunes_duration(episode.get("duration") or 0)
        entry.podcast.itunes_explicit("no")
    return feed


def add_channel_metadata(xml_bytes: bytes, show: ShowConfig, episodes: list[dict]) -> bytes:
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

    newest_date = parse_date(episodes[0]["published"]) if episodes else datetime.combine(show.source.start_date, datetime.min.time(), tzinfo=timezone.utc)
    set_or_update("lastBuildDate", format_datetime(newest_date))
    set_or_update(f"{{{ITUNES_NS}}}type", "episodic")
    set_or_update(f"{{{ITUNES_NS}}}summary", show.podcast.description)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_show(show: ShowConfig) -> None:
    if not show.podcast.artwork_path.exists():
        raise FileNotFoundError(f"Missing artwork: {show.podcast.artwork_path}")

    episodes = sorted(
        available_episodes(load_episodes(show.episodes_path)),
        key=lambda episode: episode["published"],
        reverse=True,
    )
    show.public_dir.mkdir(parents=True, exist_ok=True)
    artwork_dest = show.public_dir / "assets" / "podcast-cover.png"
    artwork_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(show.podcast.artwork_path, artwork_dest)

    xml = add_channel_metadata(build_feed(show, episodes).rss_str(pretty=True), show, episodes)
    feed_path = show.public_dir / "feed.xml"
    feed_path.write_bytes(xml)
    print(f"{feed_path} written with {len(episodes)} episode(s)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", help="Show slug. Omit to build all enabled shows.")
    args = parser.parse_args()
    for show in selected_shows(args.show):
        build_show(show)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
