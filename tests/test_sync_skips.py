from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from podcast_feeds.config import PodcastConfig, R2Config, ShowConfig, SourceConfig
from podcast_feeds.episode_notifications import write_skipped_youtube_outputs
from podcast_feeds.sync import sync_youtube_source
from podcast_feeds.youtube import common_opts


def _source() -> SourceConfig:
    return SourceConfig(
        type="youtube",
        feed_url=None,
        delivery_mode="mirror",
        channel_url="https://www.youtube.com/@example",
        channel_id="UCexample",
        playlist_id=None,
        tabs=("videos",),
        start_date=date(2026, 1, 1),
        scan_limit_per_tab=10,
        max_episodes_per_run=None,
        folder_id=None,
        filename_pattern=None,
    )


def _show(root: Path) -> ShowConfig:
    show_dir = root / "shows" / "nachmanson"
    source = _source()
    return ShowConfig(
        slug="nachmanson",
        enabled=True,
        source=source,
        sources=(source,),
        podcast=PodcastConfig(
            title="Nachmanson",
            owner_name="Owner",
            owner_email=None,
            author="Author",
            description="Description",
            language="he",
            category="Religion & Spirituality",
            subcategory=None,
            explicit="false",
            copyright="Copyright",
            website_url="https://example.test/nachmanson",
            feed_url="https://example.test/nachmanson/feed.xml",
            artwork_path=show_dir / "assets" / "podcast-cover.png",
            artwork_url="https://example.test/cover.png",
            platforms={},
        ),
        r2=R2Config(prefix="nachmanson"),
        show_dir=show_dir,
        episodes_path=show_dir / "episodes.json",
        public_dir=root / "public" / "nachmanson",
    )


def _meta(**overrides):
    values = {
        "title": "A useful shiur",
        "upload_date": "20260714",
        "duration": 1800,
        "description": "Description",
    }
    values.update(overrides)
    return values


class YouTubeSkipReportTests(unittest.TestCase):
    def test_pot_strategy_tries_mweb_with_po_tokens(self) -> None:
        youtube_args = common_opts("pot")["extractor_args"]["youtube"]
        self.assertEqual(youtube_args["player_client"][:2], ["mweb", "android_vr"])
        self.assertEqual(youtube_args["fetch_pot"], ["always"])

    def test_wpc_browser_path_is_passed_to_extractor_args(self) -> None:
        with patch.dict("os.environ", {"YOUTUBE_WPC_BROWSER_PATH": "/usr/bin/google-chrome"}):
            extractor_args = common_opts("pot")["extractor_args"]

        self.assertEqual(
            extractor_args["youtubepot-wpc"]["browser_path"],
            ["/usr/bin/google-chrome"],
        )

    def test_youtube_requests_prefer_hebrew_metadata(self) -> None:
        opts = common_opts("pot")

        self.assertEqual(opts["http_headers"]["Accept-Language"], "he-IL,he;q=0.9,en-US;q=0.5,en;q=0.3")

    def test_auth_required_metadata_failure_is_reported_and_nonfatal(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            skipped: list[dict] = []
            show = _show(Path(temp))

            with (
                patch("podcast_feeds.sync.discover_video_ids_by_tab", return_value=[("videos", ["abc123"])]),
                patch(
                    "podcast_feeds.sync.extract_video_metadata",
                    side_effect=Exception("Sign in to confirm you're not a bot"),
                ),
            ):
                ok = sync_youtube_source(show, _source(), skipped_youtube=skipped)

            self.assertTrue(ok)
            self.assertEqual(len(skipped), 1)
            self.assertEqual(skipped[0]["show_slug"], "nachmanson")
            self.assertEqual(skipped[0]["video_id"], "abc123")
            self.assertEqual(skipped[0]["phase"], "metadata")
            self.assertTrue(skipped[0]["retryable"])
            self.assertIn("auth/bot-check", skipped[0]["reason"])

    def test_403_download_failure_is_reported_and_nonfatal(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            skipped: list[dict] = []
            show = _show(Path(temp))

            def extract(video_id, download=False, output_template=None):
                if download:
                    raise Exception("HTTP Error 403: Forbidden")
                return _meta(title="Blocked episode")

            with (
                patch("podcast_feeds.sync.discover_video_ids_by_tab", return_value=[("videos", ["def456"])]),
                patch("podcast_feeds.sync.extract_video_metadata", side_effect=extract),
            ):
                ok = sync_youtube_source(show, _source(), skipped_youtube=skipped)

            self.assertTrue(ok)
            self.assertEqual(len(skipped), 1)
            self.assertEqual(skipped[0]["video_id"], "def456")
            self.assertEqual(skipped[0]["title"], "Blocked episode")
            self.assertEqual(skipped[0]["phase"], "download")
            self.assertIn("HTTP Error 403: Forbidden", skipped[0]["reason"])

    def test_format_unavailable_download_failure_is_reported_and_nonfatal(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            skipped: list[dict] = []
            show = _show(Path(temp))

            def extract(video_id, download=False, output_template=None):
                if download:
                    raise Exception("Requested format is not available")
                return _meta(title="PO token blocked episode")

            with (
                patch("podcast_feeds.sync.discover_video_ids_by_tab", return_value=[("videos", ["fmt789"])]),
                patch("podcast_feeds.sync.extract_video_metadata", side_effect=extract),
            ):
                ok = sync_youtube_source(show, _source(), skipped_youtube=skipped)

            self.assertTrue(ok)
            self.assertEqual(len(skipped), 1)
            self.assertEqual(skipped[0]["video_id"], "fmt789")
            self.assertEqual(skipped[0]["title"], "PO token blocked episode")
            self.assertEqual(skipped[0]["phase"], "download")
            self.assertIn("auth/bot-check or access block", skipped[0]["reason"])

    def test_short_video_skip_is_not_reported(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            skipped: list[dict] = []
            show = _show(Path(temp))

            with (
                patch("podcast_feeds.sync.discover_video_ids_by_tab", return_value=[("videos", ["short1"])]),
                patch("podcast_feeds.sync.extract_video_metadata", return_value=_meta(duration=60)),
            ):
                ok = sync_youtube_source(show, _source(), skipped_youtube=skipped)

            self.assertTrue(ok)
            self.assertEqual(skipped, [])

    def test_normal_post_live_delay_under_one_hour_is_not_reported(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            skipped: list[dict] = []
            show = _show(Path(temp))
            timestamp = int((datetime.now(timezone.utc) - timedelta(minutes=30)).timestamp())

            with (
                patch("podcast_feeds.sync.discover_video_ids_by_tab", return_value=[("videos", ["live1"])]),
                patch(
                    "podcast_feeds.sync.extract_video_metadata",
                    return_value=_meta(upload_date=None, timestamp=timestamp, live_status="post_live"),
                ),
            ):
                ok = sync_youtube_source(show, _source(), skipped_youtube=skipped)

            self.assertTrue(ok)
            self.assertEqual(skipped, [])

    def test_skipped_youtube_notification_includes_actionable_details(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            root = Path(temp)
            output = root / "github-output.txt"
            summary = root / "summary.md"

            write_skipped_youtube_outputs(
                skips=[
                    {
                        "show_slug": "nachmanson",
                        "video_id": "def456",
                        "youtube_url": "https://www.youtube.com/watch?v=def456",
                        "title": "Blocked episode",
                        "phase": "download",
                        "reason": "HTTP Error 403: Forbidden",
                        "retryable": True,
                    }
                ],
                repo="owner/repo",
                run_url="https://github.com/owner/repo/actions/runs/1",
                output_path=output,
                summary_path=summary,
            )

            output_text = output.read_text(encoding="utf-8")
            summary_text = summary.read_text(encoding="utf-8")
            self.assertIn("has_actionable_skips=true", output_text)
            self.assertIn("Blocked episode", summary_text)
            self.assertIn("def456", summary_text)
            self.assertIn("HTTP Error 403: Forbidden", summary_text)
            self.assertIn("runner=oracle-youtube", summary_text)


if __name__ == "__main__":
    unittest.main()
