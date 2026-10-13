import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from podcast_feeds import build, site
from podcast_feeds.config import load_show, load_site_config


def fixed_datetime(value: str):
    instant = datetime.fromisoformat(value)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz or timezone.utc)

    return Clock


class StableFeedTests(unittest.TestCase):
    def test_release_correction_uses_explicit_build_instant(self):
        show = load_show("wechter")
        episode = {"id": "recording-1", "title": "Original", "published": "20260102",
                   "url": "https://audio.example/one.mp3", "size": 100}
        first = build.add_channel_metadata(build.build_feed(show, [episode]).rss_str(pretty=True), show, [episode])
        episode["title"] = "Corrected"
        generated = build.build_feed(show, [episode]).rss_str(pretty=True)
        with patch.dict(os.environ, {"TORAH_POD_RELEASE_RENDER": "1"}, clear=False):
            os.environ.pop("TORAH_POD_BUILD_INSTANT", None)
            with self.assertRaisesRegex(ValueError, "BUILD_INSTANT"):
                build.add_channel_metadata(generated, show, [episode], previous_xml=first)
        with patch.dict(os.environ, {"TORAH_POD_RELEASE_RENDER": "1", "TORAH_POD_BUILD_INSTANT": "2026-10-12T18:00:00Z"}):
            corrected = build.add_channel_metadata(generated, show, [episode], previous_xml=first)
        self.assertEqual(ET.fromstring(corrected).findtext("channel/lastBuildDate"), "Mon, 12 Oct 2026 18:00:00 +0000")

    def test_first_build_date_comes_from_episodes(self):
        show = load_show("wechter")
        episode = {
            "id": "recording-1", "title": "Example", "published": "20260102",
            "url": "https://audio.example/recording-1.mp3", "size": 100,
        }
        with patch.object(build, "datetime", fixed_datetime("2026-10-11T10:00:00+00:00")):
            first = build.add_channel_metadata(build.build_feed(show, [episode]).rss_str(pretty=True), show, [episode])
        with patch.object(build, "datetime", fixed_datetime("2026-10-12T10:00:00+00:00")):
            second = build.add_channel_metadata(build.build_feed(show, [episode]).rss_str(pretty=True), show, [episode])
        self.assertEqual(first, second)
        self.assertEqual(ET.fromstring(first).findtext("channel/lastBuildDate"), "Fri, 02 Jan 2026 00:00:00 +0000")

    def test_noop_build_and_old_episode_correction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            show = load_show("wechter")
            show = replace(show, episodes_path=root / "episodes.json", public_dir=root / "public")
            episode = {
                "id": "recording-1",
                "guid": "stable-guid-1",
                "title": "Original title",
                "description": "Original description",
                "published": "20260102",
                "url": "https://audio.example/recording-1.mp3",
                "size": 123456,
                "duration": 600,
                "source_url": "https://source.example/recording-1",
            }
            show.episodes_path.write_text(json.dumps({episode["id"]: episode}), encoding="utf-8")

            with patch.dict(os.environ, {"GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "101"}), patch.object(build, "datetime", fixed_datetime("2026-10-11T10:00:00+00:00")):
                build.build_show(show)
            first = (show.public_dir / "feed.xml").read_bytes()
            self.assertEqual((show.public_dir / "spotify.xml").read_bytes(), first)
            first_date = ET.fromstring(first).findtext("channel/lastBuildDate")

            with patch.dict(os.environ, {"GITHUB_SHA": "b" * 40, "GITHUB_RUN_ID": "202"}), patch.object(build, "datetime", fixed_datetime("2026-10-12T10:00:00+00:00")):
                build.build_show(show)
            self.assertEqual((show.public_dir / "feed.xml").read_bytes(), first)

            episode["title"] = "Corrected title"
            show.episodes_path.write_text(json.dumps({episode["id"]: episode}), encoding="utf-8")
            with patch.object(build, "datetime", fixed_datetime("2026-10-13T10:00:00+00:00")):
                build.build_show(show)
            corrected = (show.public_dir / "feed.xml").read_bytes()
            corrected_root = ET.fromstring(corrected)
            self.assertNotEqual(corrected, first)
            self.assertNotEqual(corrected_root.findtext("channel/lastBuildDate"), first_date)
            item = corrected_root.find("channel/item")
            self.assertEqual(item.findtext("guid"), "stable-guid-1")
            self.assertEqual(item.find("enclosure").attrib["url"], episode["url"])
            self.assertEqual(item.findtext("title"), "Corrected title")

            with patch.object(build, "datetime", fixed_datetime("2026-10-14T10:00:00+00:00")):
                build.build_show(show)
            self.assertEqual((show.public_dir / "feed.xml").read_bytes(), corrected)
            self.assertEqual((show.public_dir / "spotify.xml").read_bytes(), corrected)


class StablePageTests(unittest.TestCase):
    def test_identical_icon_pixels_keep_prior_png_bytes(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "icon.png"
            icon = Image.new("RGB", (16, 16), "#12284d")
            icon.save(path, compress_level=0)
            prior = path.read_bytes()
            site._save_icon_if_pixels_changed(icon, path)
            self.assertEqual(path.read_bytes(), prior)
            changed = Image.new("RGB", (16, 16), "#ffffff")
            site._save_icon_if_pixels_changed(changed, path)
            self.assertNotEqual(path.read_bytes(), prior)

    def test_separate_process_builds_preserve_bytes_and_publish_old_correction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "public"
            episodes = root / "episodes.json"
            episode = {
                "id": "recording-1", "guid": "stable-guid-1",
                "title": "Original title", "description": "Original description",
                "published": "20260102", "url": "https://audio.example/recording-1.mp3",
                "size": 123456, "duration": 600,
            }
            script = """
from dataclasses import replace
from pathlib import Path
import sys
from podcast_feeds import build, site
from podcast_feeds.config import load_show
root = Path(sys.argv[1])
show = load_show('wechter')
show = replace(show, episodes_path=root / 'episodes.json', public_dir=root / 'public' / show.slug)
site.PUBLIC_DIR = root / 'public'
(site.PUBLIC_DIR / 'assets').mkdir(parents=True, exist_ok=True)
build.build_show(show)
site.build_site([show])
"""

            def run_build(sha: str, run_id: str) -> dict[Path, bytes]:
                env = os.environ.copy()
                env.update({"GITHUB_SHA": sha, "GITHUB_RUN_ID": run_id})
                result = subprocess.run(
                    [sys.executable, "-c", script, str(root)],
                    cwd=Path(__file__).resolve().parents[1], env=env,
                    check=False, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return {path.relative_to(output): path.read_bytes()
                        for path in output.rglob("*") if path.is_file()}

            episodes.write_text(json.dumps({episode["id"]: episode}), encoding="utf-8")
            first = run_build("a" * 40, "101")
            second = run_build("b" * 40, "202")
            self.assertEqual(first, second)

            feed_path = Path("wechter/feed.xml")
            first_root = ET.fromstring(first[feed_path])
            episode["title"] = "Corrected historical title"
            episodes.write_text(json.dumps({episode["id"]: episode}), encoding="utf-8")
            corrected = run_build("c" * 40, "303")
            corrected_root = ET.fromstring(corrected[feed_path])
            self.assertNotEqual(corrected[feed_path], first[feed_path])
            self.assertNotEqual(
                corrected_root.findtext("channel/lastBuildDate"),
                first_root.findtext("channel/lastBuildDate"),
            )
            item = corrected_root.find("channel/item")
            self.assertEqual(item.findtext("title"), "Corrected historical title")
            self.assertEqual(item.findtext("guid"), "stable-guid-1")
            self.assertEqual(item.find("enclosure").attrib["url"], episode["url"])
            self.assertEqual(run_build("d" * 40, "404"), corrected)

    def test_site_files_and_episode_route_stay_stable_across_ci_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "public"
            (output / "assets").mkdir(parents=True)
            show = load_show("wechter")
            show = replace(show, episodes_path=root / "episodes.json", public_dir=output / show.slug)
            show.episodes_path.write_text(json.dumps({
                "recording-1": {
                    "id": "recording-1", "guid": "stable-guid-1", "title": "Example",
                    "published": "20260102", "url": "https://audio.example/recording-1.mp3",
                    "size": 100, "duration": 600,
                }
            }), encoding="utf-8")

            with patch.object(site, "PUBLIC_DIR", output):
                with patch.dict(os.environ, {"GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "101"}):
                    site.build_site([show])
                first = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
                with patch.dict(os.environ, {"GITHUB_SHA": "b" * 40, "GITHUB_RUN_ID": "202"}):
                    site.build_site([show])
                second = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}

            self.assertEqual(first, second)
            episode_route = Path(site._episode_page_path(show.slug, {"guid": "stable-guid-1", "id": "recording-1"})) / "index.html"
            self.assertIn(episode_route, first)
            self.assertIn("https://audio.example/recording-1.mp3", first[episode_route].decode("utf-8"))

    def test_ci_revision_and_run_do_not_rewrite_page_badge(self):
        config = load_site_config()
        with patch.dict(os.environ, {"GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "101"}):
            importlib.reload(site)
            first = site._page("Example", "<p>Content</p>", site_config=config)
        with patch.dict(os.environ, {"GITHUB_SHA": "b" * 40, "GITHUB_RUN_ID": "202"}):
            importlib.reload(site)
            second = site._page("Example", "<p>Content</p>", site_config=config)
        self.assertEqual(first, second)
        self.assertIn(f'data-site-build="{site.SITE_BUILD_ID}"', first)
        self.assertNotEqual(site.SITE_BUILD_ID, "aaaaaaa")
        self.assertNotEqual(site.SITE_BUILD_ID, "bbbbbbb")


if __name__ == "__main__":
    unittest.main()
