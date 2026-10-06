import json
import html
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from podcast_feeds.config import load_enabled_shows
from podcast_feeds.episode_metadata import legacy_snapshot, read_snapshot, snapshot_path, write_snapshot, write_episode_pages
from podcast_feeds.site import _load_show_episodes


class EpisodeMetadataTests(unittest.TestCase):
    def test_explore_lists_every_enabled_show_without_episode_results(self):
        markup = Path("public/explore/index.html").read_text(encoding="utf-8")
        slugs = re.findall(r'data-show-slug="([^"]+)"', markup)
        self.assertEqual(set(slugs), {show.slug for show in load_enabled_shows()})
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertNotIn("data-episode-id", markup)
        self.assertIn("data-explore-filter", markup)

    def test_search_opens_with_playable_real_episodes_without_javascript(self):
        markup = Path("public/search/index.html").read_text(encoding="utf-8")
        identities = [html.unescape(value) for value in re.findall(r'data-episode-id="([^"]+)"', markup)]
        index = json.loads(Path("public/search-index.json").read_text(encoding="utf-8"))
        by_id = {item["id"]: item for item in index["episodes"]}
        self.assertEqual(len(identities), 20)
        for identity in identities:
            self.assertIn(html.escape(by_id[identity]["audio_url"], quote=True), markup)
            self.assertIn(f'../{by_id[identity]["page_url"]}', markup)

    def test_offline_upgrade_retains_published_episode_descriptions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "search-index.json").write_text(json.dumps({"schema_version": 1, "episodes": [
                {"id": "show:stable", "show_slug": "show", "title": "Episode", "audio_url": "https://example.com/audio.mp3"}
            ]}))
            page = root / "show/episodes/episode-one/index.html"
            page.parent.mkdir(parents=True)
            page.write_text('<article data-episode-id="show:stable" data-episode-description="A &amp; B"></article>')
            self.assertEqual(legacy_snapshot(root, "show")[0]["description"], "A & B")

    def test_initial_html_matches_the_first_metadata_page(self):
        index = json.loads(Path("public/metadata/v1/latest.json").read_text(encoding="utf-8"))
        for show in index["shows"]:
            page = Path("public", show["slug"], "index.html").read_text(encoding="utf-8")
            identities = [html.unescape(value) for value in re.findall(r'data-episode-id="([^"]+)"', page)]
            first = json.loads(Path("public/metadata/v1/shows", show["slug"], "1.json").read_text(encoding="utf-8"))
            self.assertEqual(identities, [item["id"] for item in first["episodes"]], show["slug"])

    def test_snapshot_rejects_invalid_enclosures_and_retains_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feed.json"
            item = {"id": "stable", "title": "Episode", "url": "https://example.com/one.mp3", "duration": 60}
            write_snapshot(path, [item])
            with self.assertRaises(ValueError):
                write_snapshot(path, [{**item, "url": "javascript:alert(1)"}])
            self.assertEqual(read_snapshot(path), [item])

    def test_snapshot_deduplicates_guid_and_strips_unrecognized_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            item = {"guid": "one", "title": "Episode", "url": "https://example.com/one.mp3", "private_note": "discard"}
            result = write_snapshot(Path(directory) / "feed.json", [item, item])
            self.assertEqual(len(result), 1)
            self.assertNotIn("private_note", result[0])

    def test_failed_linked_refresh_retains_valid_previous_episodes(self):
        show = next(show for show in load_enabled_shows() if show.slug == "alvnymyyl-alonimail")
        item = {"guid": "last-good", "title": "Episode", "published": "20261001", "url": "https://example.com/one.mp3"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_snapshot(snapshot_path(root, show.slug, show.sources[0].feed_url), [item])
            with patch("podcast_feeds.site.PUBLIC_DIR", root), patch("podcast_feeds.site.list_existing_feed_items", side_effect=OSError("upstream failed")), patch.dict("os.environ", {"TORAH_POD_OFFLINE_BUILD": "0"}):
                self.assertEqual(_load_show_episodes(show), [item])

    def test_corrupt_previous_metadata_is_not_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feed.json"
            path.write_text('{"schema_version":1,"episodes":[{"url":"file:///private"}]}')
            self.assertIsNone(read_snapshot(path))

    def test_empty_and_complete_episode_pagination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            items = [{"id": f"show:{i}", "published": "20261001"} for i in range(41)]
            result = write_episode_pages(root, "show", items + items[:1])
            self.assertEqual(result["total"], 41)
            self.assertEqual(result["pages"], 3)
            final = json.loads((root / "metadata/v1/shows/show/3.json").read_text())
            self.assertIsNone(final["next_page"])
            self.assertEqual(len(final["episodes"]), 1)
            self.assertEqual(write_episode_pages(root, "empty", [])["pages"], 1)
