from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from podcast_feeds.episodes import load_episodes, save_episodes
from podcast_feeds.sync_state import (
    SCHEMA_VERSION,
    apply_candidates,
    bootstrap,
    fingerprint,
    health,
    retry_at,
)
from podcast_feeds.sync import _record_unavailable_observation
from podcast_feeds.youtube import (
    _auth_strategies,
    common_opts,
    extract_video_metadata,
    recording_is_ready,
)


class MemoryStore:
    def __init__(self, values=None):
        self.values = values or {}

    def get_json(self, key):
        return self.values.get(key)

    def put_json(self, key, value):
        self.values[key] = json.loads(json.dumps(value))

    def list_json(self, prefix):
        for key in sorted(self.values):
            if key.startswith(prefix):
                yield key, self.values[key]


class ReliableSyncTests(unittest.TestCase):
    def test_youtube_enables_pinned_node_runtime(self):
        self.assertIn("node", common_opts("pot")["js_runtimes"])
        self.assertIn("node", common_opts("cookie")["js_runtimes"])

    def test_bootstrap_dry_run_does_not_write_state(self):
        store = MemoryStore()
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            output = Path(temporary) / "bootstrap.json"
            result = bootstrap(store, "wechter", output, dry_run=True)
        self.assertGreater(result["episode_count"], 0)
        self.assertEqual(result["episode_count"], result["planned"]["published"] + result["planned"]["unavailable"] + result["planned"]["pending"])
        self.assertEqual(result["public_changes"], 0)
        self.assertEqual(store.values, {})

    def test_bootstrap_is_idempotent(self):
        store = MemoryStore()
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            output = Path(temporary) / "bootstrap.json"
            first = bootstrap(store, "wechter", output)
            second = bootstrap(store, "wechter", output)
        self.assertEqual(first["episode_count"], len(store.values))
        self.assertEqual(second["existing_state"], first["episode_count"])

    def test_episode_save_is_atomic_and_loadable(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            path = Path(temporary) / "episodes.json"
            save_episodes(path, {"x": {"id": "x", "title": "שלום"}})
            self.assertEqual(load_episodes(path)["x"]["title"], "שלום")
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_recording_requires_finite_completed_metadata(self):
        self.assertFalse(recording_is_ready({"duration": 500, "live_status": "post_live"}))
        self.assertFalse(recording_is_ready({"live_status": "not_live"}))
        self.assertTrue(recording_is_ready({"duration": 500, "live_status": "was_live"}))
        self.assertTrue(recording_is_ready({"duration": 500}))

    def test_download_rechecks_final_metadata_before_fetching_media(self):
        captured = {}

        class Downloader:
            def __init__(self, options):
                captured.update(options)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, *_args, **_kwargs):
                reason = captured["match_filter"](
                    {"duration": 500, "live_status": "post_live"}, incomplete=False
                )
                raise RuntimeError(reason)

        with patch("podcast_feeds.youtube.yt_dlp.YoutubeDL", Downloader):
            with self.assertRaisesRegex(RuntimeError, "recording is not ready"):
                extract_video_metadata("abc", download=True, output_template="x.%(ext)s")

    def test_malformed_cookie_file_disables_cookie_strategy(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            cookie = Path(temporary) / "cookies.txt"
            cookie.write_text("not netscape", encoding="utf-8")
            with (
                patch("podcast_feeds.youtube.COOKIES_FILE", cookie),
                patch.dict("os.environ", {"YOUTUBE_AUTH_MODE": "pot_then_cookie"}),
            ):
                self.assertEqual(_auth_strategies(), ["pot"])

    def test_retry_backoff_is_bounded_and_deterministic(self):
        now = datetime(2026, 9, 8, tzinfo=timezone.utc)
        first = retry_at("show:item", 9, now)
        second = retry_at("show:item", 9, now)
        delay = datetime.fromisoformat(first.replace("Z", "+00:00")) - now
        self.assertEqual(first, second)
        self.assertGreaterEqual(delay.total_seconds(), 5.4 * 3600)
        self.assertLessEqual(delay.total_seconds(), 6.6 * 3600)

    def test_stale_candidate_is_quarantined_without_changing_metadata(self):
        candidate = {
            "schema_version": SCHEMA_VERSION,
            "candidate_id": "candidate",
            "show_slug": "wechter",
            "episode_id": "new-id",
            "lane": "youtube",
            "source_config_fingerprint": "stale",
            "previous_record_fingerprint": fingerprint(None),
            "episode": {"id": "new-id"},
        }
        store = MemoryStore({"v1/candidates/candidate.json": candidate})
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            manifest = Path(temporary) / "manifest.json"
            self.assertEqual(apply_candidates(store, manifest), 0)
        self.assertIn("v1/quarantine/candidate.json", store.values)

    def test_health_reports_six_hour_ready_candidate(self):
        store = MemoryStore(
            {
                "v1/work/youtube/show/item.json": {
                    "schema_version": SCHEMA_VERSION,
                    "state": "ready_to_publish",
                    "first_discovered_at": "2020-01-01T00:00:00Z",
                    "first_ready_at": "2020-01-01T00:00:00Z",
                }
            }
        )
        self.assertEqual(health(store)["status"], "error")

    def test_three_hour_discovery_warning_does_not_open_incident(self):
        now = datetime(2026, 9, 10, 8, tzinfo=timezone.utc)
        store = MemoryStore(
            {
                "v1/sources/youtube/show.json": {
                    "show_slug": "show",
                    "lane": "youtube",
                    "last_successful_discovery_at": "2026-09-10T04:30:00Z",
                }
            }
        )
        with patch("podcast_feeds.sync_state.utc_now", return_value=now):
            report = health(store, persist=True)
        self.assertEqual(report["status"], "warning")
        self.assertIsNone(report["notification_transition"])
        self.assertEqual(store.values["v1/health/sync-incident.json"]["status"], "ok")

    def test_six_hour_discovery_alert_opens_and_recovers_incident(self):
        now = datetime(2026, 9, 10, 8, tzinfo=timezone.utc)
        source_key = "v1/sources/youtube/show.json"
        store = MemoryStore(
            {
                source_key: {
                    "show_slug": "show",
                    "lane": "youtube",
                    "last_successful_discovery_at": "2026-09-10T01:00:00Z",
                }
            }
        )
        with patch("podcast_feeds.sync_state.utc_now", return_value=now):
            opened = health(store, persist=True)
        self.assertEqual(opened["notification_transition"], "opened")
        store.values[source_key]["last_successful_discovery_at"] = "2026-09-10T07:30:00Z"
        with patch("podcast_feeds.sync_state.utc_now", return_value=now):
            recovered = health(store, persist=True)
        self.assertEqual(recovered["notification_transition"], "recovered")

    def test_unavailability_requires_confirmation_after_six_hours(self):
        known = {}
        self.assertFalse(_record_unavailable_observation(known, "gone"))
        self.assertNotIn("unavailable", known["gone"])
        known["gone"]["unavailable_pending_at"] = "2020-01-01T00:00:00Z"
        self.assertTrue(_record_unavailable_observation(known, "gone"))
        self.assertTrue(known["gone"]["unavailable"])


if __name__ == "__main__":
    unittest.main()
