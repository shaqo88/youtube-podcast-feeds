import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from podcast_feeds.config import load_enabled_shows
from podcast_feeds.episode_metadata import read_snapshot, snapshot_path, write_snapshot
from podcast_feeds.existing_feed import ExistingFeedItem
from podcast_feeds.linked_feed_refresh import refresh_source
from podcast_feeds.site import _load_show_episodes


def linked_show():
    return next(show for show in load_enabled_shows() if show.slug == "alvnymyyl-alonimail")


def episode():
    return {"guid": "stable", "title": "Episode", "published": "20990101", "url": "https://example.com/one.mp3"}


def feed_item():
    return ExistingFeedItem(
        id="stable", guid="feed:item:stable", title="Episode", description="Description",
        published="20990101", duration=60, enclosure_url="https://example.com/one.mp3",
        enclosure_type="audio/mpeg", enclosure_size=100, source_url="https://example.com/episode",
    )


class LinkedFeedRefreshTests(unittest.TestCase):
    def test_release_render_uses_exact_snapshot_without_network_or_rewriting_it(self):
        show = linked_show()
        source = show.sources[0]
        with tempfile.TemporaryDirectory() as directory:
            public_dir = Path(directory)
            path = snapshot_path(public_dir, show.slug, source.feed_url)
            write_snapshot(path, [episode()])
            original = path.read_bytes()
            with patch("podcast_feeds.site.PUBLIC_DIR", public_dir), \
                 patch("podcast_feeds.site.list_existing_feed_items", side_effect=AssertionError("network fetch")), \
                 patch("requests.sessions.Session.request", side_effect=AssertionError("network request")), \
                 patch.dict(os.environ, {"TORAH_POD_RELEASE_RENDER": "1", "TORAH_POD_OFFLINE_BUILD": "0"}):
                self.assertEqual(_load_show_episodes(show), [episode()])
            self.assertEqual(path.read_bytes(), original)

    def test_release_render_rejects_missing_or_corrupt_snapshot_without_legacy_fallback(self):
        show = linked_show()
        source = show.sources[0]
        with tempfile.TemporaryDirectory() as directory:
            public_dir = Path(directory)
            path = snapshot_path(public_dir, show.slug, source.feed_url)
            with patch("podcast_feeds.site.PUBLIC_DIR", public_dir), \
                 patch("podcast_feeds.site.legacy_snapshot", return_value=[episode()]), \
                 patch("podcast_feeds.site.list_existing_feed_items", side_effect=AssertionError("network fetch")), \
                 patch.dict(os.environ, {"TORAH_POD_RELEASE_RENDER": "1"}):
                with self.assertRaisesRegex(ValueError, "missing or invalid linked-feed snapshot"):
                    _load_show_episodes(show)
                path.parent.mkdir(parents=True)
                path.write_text('{"schema_version":1,"episodes":[{"url":"file:///private"}]}', encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "missing or invalid linked-feed snapshot"):
                    _load_show_episodes(show)

    def test_refresh_captures_validated_snapshot_and_preserves_last_good_on_failure(self):
        show = linked_show()
        source = show.sources[0]
        with tempfile.TemporaryDirectory() as directory:
            public_dir = Path(directory)
            with patch("podcast_feeds.linked_feed_refresh.list_existing_feed_items", return_value=[feed_item()]) as fetch:
                path = refresh_source(show, source, public_dir=public_dir)
            fetch.assert_called_once_with(source.feed_url, source.scan_limit_per_tab)
            original = path.read_bytes()
            self.assertEqual(read_snapshot(path)[0]["guid"], "feed:item:stable")
            with patch("podcast_feeds.linked_feed_refresh.list_existing_feed_items", side_effect=TimeoutError("upstream")):
                self.assertEqual(refresh_source(show, source, public_dir=public_dir), path)
            self.assertEqual(path.read_bytes(), original)

    def test_refresh_without_initial_valid_snapshot_fails(self):
        show = linked_show()
        source = show.sources[0]
        with tempfile.TemporaryDirectory() as directory:
            with patch("podcast_feeds.linked_feed_refresh.list_existing_feed_items", side_effect=TimeoutError("upstream")):
                with self.assertRaisesRegex(RuntimeError, "no valid initial linked-feed snapshot"):
                    refresh_source(show, source, public_dir=Path(directory))

    def test_interrupted_atomic_replace_keeps_previous_snapshot(self):
        show = linked_show()
        source = show.sources[0]
        with tempfile.TemporaryDirectory() as directory:
            public_dir = Path(directory)
            path = snapshot_path(public_dir, show.slug, source.feed_url)
            write_snapshot(path, [episode()])
            original = path.read_bytes()
            with patch("podcast_feeds.linked_feed_refresh.list_existing_feed_items", return_value=[feed_item()]), \
                 patch("podcast_feeds.linked_feed_refresh.os.replace", side_effect=OSError("interrupted")):
                with self.assertRaisesRegex(OSError, "interrupted"):
                    refresh_source(show, source, public_dir=public_dir)
            self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
