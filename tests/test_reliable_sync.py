from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

from podcast_feeds.config import load_show
from podcast_feeds.episodes import load_episodes, save_episodes
from podcast_feeds.sync_state import (
    PENDING_RECONCILE_KEY,
    SCHEMA_VERSION,
    apply_candidates,
    bootstrap,
    capture,
    cookie_allowed,
    due_retries,
    fingerprint,
    health,
    notification_report,
    pending_key,
    receipt,
    receipt_complete,
    record_skips,
    reconcile_pending,
    retry_at,
    update_receipts,
)
from podcast_feeds.sync import _record_unavailable_observation
from podcast_feeds.youtube import (
    _auth_strategies,
    common_opts,
    extract_info_with_auth,
    extract_video_metadata,
    recording_is_ready,
)


class MemoryStore:
    def __init__(self, values=None):
        self.values = values or {}
        self.listed_prefixes = []

    def get_json(self, key):
        return self.values.get(key)

    def put_json(self, key, value):
        self.values[key] = json.loads(json.dumps(value))

    def delete_json(self, key):
        self.values.pop(key, None)

    def list_json(self, prefix):
        self.listed_prefixes.append(prefix)
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

    def test_explicit_cookie_warning_is_preserved_in_final_error(self):
        class Downloader:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, *_args, **_kwargs):
                self.options["logger"].warning(
                    "The provided YouTube account cookies are no longer valid"
                )
                raise RuntimeError("The page needs to be reloaded")

        with (
            patch("podcast_feeds.youtube._auth_strategies", return_value=["cookie"]),
            patch("podcast_feeds.youtube.yt_dlp.YoutubeDL", Downloader),
        ):
            with self.assertRaisesRegex(RuntimeError, "cookies are no longer valid"):
                extract_video_metadata("abc", download=False)

    def test_partial_metadata_retries_cookie_and_accepts_completed_recording(self):
        attempted = []

        class Downloader:
            def __init__(self, options):
                self.options = options
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def extract_info(self, *_args, **_kwargs):
                strategy = self.options["strategy"]
                attempted.append(strategy)
                if strategy == "pot":
                    self.options["logger"].warning("Sign in to confirm you're not a bot")
                    return {"id": "abc", "title": "Partial", "live_status": "was_live"}
                return {"id": "abc", "title": "Complete", "duration": 998,
                        "live_status": "was_live", "formats": [{"url": "https://media.example/abc"}]}

        with (
            patch("podcast_feeds.youtube._auth_strategies", return_value=["pot", "cookie"]),
            patch("podcast_feeds.youtube.common_opts", side_effect=lambda strategy, **_: {"strategy": strategy}),
            patch("podcast_feeds.youtube.yt_dlp.YoutubeDL", Downloader),
        ):
            result = extract_video_metadata("abc")
        self.assertEqual(attempted, ["pot", "cookie"])
        self.assertEqual(result["duration"], 998)

    def test_exhausted_partial_metadata_is_an_access_failure(self):
        attempted = []

        class Downloader:
            def __init__(self, options):
                self.options = options
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def extract_info(self, *_args, **_kwargs):
                attempted.append(self.options["strategy"])
                return {"id": "abc", "live_status": "was_live"}

        with (
            patch("podcast_feeds.youtube._auth_strategies", return_value=["pot", "cookie"]),
            patch("podcast_feeds.youtube.common_opts", side_effect=lambda strategy, **_: {"strategy": strategy}),
            patch("podcast_feeds.youtube.yt_dlp.YoutubeDL", Downloader),
        ):
            with self.assertRaisesRegex(RuntimeError, "incomplete YouTube metadata"):
                extract_video_metadata("abc")
        self.assertEqual(attempted, ["pot", "cookie"])

    def test_processing_recording_does_not_consume_auth_fallback(self):
        attempted = []

        class Downloader:
            def __init__(self, options):
                self.options = options
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def extract_info(self, *_args, **_kwargs):
                attempted.append(self.options["strategy"])
                return {"id": "abc", "live_status": "post_live", "duration": None}

        with (
            patch("podcast_feeds.youtube._auth_strategies", return_value=["pot", "cookie"]),
            patch("podcast_feeds.youtube.common_opts", side_effect=lambda strategy, **_: {"strategy": strategy}),
            patch("podcast_feeds.youtube.yt_dlp.YoutubeDL", Downloader),
        ):
            result = extract_video_metadata("abc")
        self.assertEqual(attempted, ["pot"])
        self.assertFalse(recording_is_ready(result))

    def test_access_failure_is_visible_in_source_health_and_clears_after_success(self):
        store = MemoryStore()
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            report_path = Path(temporary) / "skips.json"
            report_path.write_text(json.dumps([{
                "show_slug": "wechter", "video_id": "abc", "phase": "metadata",
                "reason": "YouTube auth/bot-check or access block", "retryable": True,
            }]), encoding="utf-8")
            record_skips(store, report_path, "youtube")
        report = health(store)
        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["source_access_failures"][0]["episode_id"], "abc")
        store.values["v1/work/youtube/wechter/abc.json"]["state"] = "published"
        self.assertEqual(health(store)["source_access_failures"], [])

    def test_isp_proxy_pool_rotates_without_sending_cookies(self):
        captured = []

        class Downloader:
            def __init__(self, options):
                self.options = options
                captured.append(options)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, *_args, **_kwargs):
                if len(captured) == 1:
                    raise RuntimeError("HTTP Error 403: Forbidden")
                return {"id": "abc", "duration": 300}

        with (
            patch("podcast_feeds.youtube._auth_strategies", return_value=["pot", "cookie"]),
            patch("podcast_feeds.youtube.yt_dlp.YoutubeDL", Downloader),
            patch.dict(
                "os.environ",
                {
                    "YOUTUBE_PROXY_URLS": "http://user:secret@one.example:8000\nhttp://user:secret@two.example:8000"
                },
                clear=False,
            ),
        ):
            result = extract_info_with_auth("https://www.youtube.com/watch?v=abc")

        self.assertEqual(result["id"], "abc")
        self.assertEqual(len(captured), 2)
        self.assertTrue(all("proxy" in options for options in captured))
        self.assertTrue(all("cookiefile" not in options for options in captured))

    def test_rejected_cookie_is_disabled_until_fingerprint_changes(self):
        store = MemoryStore()
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            report = Path(temporary) / "skips.json"
            report.write_text(
                json.dumps(
                    [{"show_slug": "show", "video_id": "item", "reason": "cookie refresh required"}]
                ),
                encoding="utf-8",
            )
            record_skips(store, report, "youtube", "old-secret")
        self.assertFalse(cookie_allowed(store, "old-secret"))
        self.assertTrue(cookie_allowed(store, "new-secret"))

    def test_retry_backoff_is_bounded_and_deterministic(self):
        now = datetime(2026, 9, 8, tzinfo=timezone.utc)
        first = retry_at("show:item", 9, now)
        second = retry_at("show:item", 9, now)
        delay = datetime.fromisoformat(first.replace("Z", "+00:00")) - now
        self.assertEqual(first, second)
        self.assertGreaterEqual(delay.total_seconds(), 5.4 * 3600)
        self.assertLessEqual(delay.total_seconds(), 6.6 * 3600)

    def test_due_retries_returns_only_expired_retryable_items_oldest_first(self):
        now = datetime(2026, 10, 20, 10, tzinfo=timezone.utc)
        store = MemoryStore({
            "v1/work/youtube/wechter/older.json": {
                "schema_version": SCHEMA_VERSION,
                "lane": "youtube", "show_slug": "wechter", "episode_id": "older",
                "state": "waiting_for_recording", "next_attempt_at": (now - timedelta(hours=2)).isoformat(),
                "first_discovered_at": (now - timedelta(days=3)).isoformat(),
            },
            "v1/work/youtube/wechter/due.json": {
                "schema_version": SCHEMA_VERSION,
                "lane": "youtube", "show_slug": "wechter", "episode_id": "due",
                "state": "retry_wait", "next_attempt_at": (now - timedelta(hours=1)).isoformat(),
                "first_discovered_at": (now - timedelta(days=1)).isoformat(),
            },
            "v1/work/youtube/wechter/future.json": {
                "schema_version": SCHEMA_VERSION,
                "lane": "youtube", "show_slug": "wechter", "episode_id": "future",
                "state": "waiting_for_recording", "next_attempt_at": (now + timedelta(minutes=5)).isoformat(),
            },
            "v1/work/youtube/wechter/published.json": {
                "schema_version": SCHEMA_VERSION,
                "lane": "youtube", "show_slug": "wechter", "episode_id": "published",
                "state": "published", "next_attempt_at": (now - timedelta(days=2)).isoformat(),
            },
            "v1/work/youtube/other/other-show.json": {
                "schema_version": SCHEMA_VERSION,
                "lane": "youtube", "show_slug": "other", "episode_id": "other-show",
                "state": "retry_wait", "next_attempt_at": (now - timedelta(days=2)).isoformat(),
            },
        })

        self.assertEqual(due_retries(store, "youtube", "wechter", limit=1, now=now), ["older"])
        self.assertEqual(due_retries(store, "youtube", "wechter", limit=5, now=now), ["older", "due"])

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

    def test_quarantine_does_not_pollute_pending_index_and_can_be_reconciled_after_release(self):
        candidate = {"schema_version": SCHEMA_VERSION, "candidate_id": "item", "show_slug": "wechter", "episode_id": "item", "lane": "youtube"}
        store = MemoryStore({
            "v1/candidates/item.json": candidate,
            pending_key("item"): {"schema_version": SCHEMA_VERSION, "candidate_id": "item"},
            "v1/quarantine/item.json": {"schema_version": SCHEMA_VERSION, "candidate_id": "item", "reason": "stale"},
        })
        reconcile_pending(store)
        self.assertNotIn(pending_key("item"), store.values)
        store.delete_json("v1/quarantine/item.json")
        self.assertEqual(reconcile_pending(store)["markers_restored"], 1)
        self.assertIn(pending_key("item"), store.values)

    def test_duplicate_capture_does_not_requeue_quarantined_candidate(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            show = replace(load_show("wechter"), episodes_path=root / "episodes.json")
            show.episodes_path.write_text(json.dumps({"item": {"id": "item", "title": "B"}}), encoding="utf-8")
            baseline = root / "baseline" / show.slug
            baseline.mkdir(parents=True)
            (baseline / "episodes.json").write_text(json.dumps({"item": {"id": "item", "title": "A"}}), encoding="utf-8")
            store = MemoryStore()
            with patch("podcast_feeds.sync_state.load_show", return_value=show), patch("podcast_feeds.sync_state.source_fingerprint", return_value="config"):
                capture(store, root / "baseline", "youtube", show_filter=show.slug)
                candidate_id = store.get_json("v1/work/youtube/wechter/item.json")["candidate_id"]
                store.put_json(f"v1/quarantine/{candidate_id}.json", {"schema_version": SCHEMA_VERSION, "candidate_id": candidate_id})
                store.delete_json(pending_key(candidate_id))
                self.assertEqual(capture(store, root / "baseline", "youtube", show_filter=show.slug), 0)
            self.assertNotIn(pending_key(candidate_id), store.values)

    def test_quarantined_candidate_stays_visible_after_newer_work_is_published(self):
        now = datetime(2026, 9, 10, 8, tzinfo=timezone.utc)
        store = MemoryStore({
            "v1/work/youtube/wechter/item.json": {"schema_version": SCHEMA_VERSION, "candidate_id": "new", "state": "published"},
            "v1/quarantine/old.json": {
                "schema_version": SCHEMA_VERSION, "candidate_id": "old",
                "quarantined_at": "2026-09-10T00:00:00Z", "reason": "published record changed",
            },
        })
        with patch("podcast_feeds.sync_state.utc_now", return_value=now):
            report = health(store)
        self.assertEqual(report["quarantine"]["count"], 1)
        self.assertEqual(report["quarantine"]["over_6h"], 1)
        self.assertTrue(report["alert"])

    def test_interrupted_marker_write_and_lost_marker_reconcile(self):
        candidate = {"schema_version": SCHEMA_VERSION, "candidate_id": "item", "show_slug": "wechter", "episode_id": "item", "lane": "youtube"}
        receipt_value = {"schema_version": SCHEMA_VERSION, "candidate_id": "item", "revision": "abc", "published_at": "2026-09-10T00:00:00Z", "deployments": {}, "notification": {"state": "pending"}}
        store = MemoryStore({
            "v1/candidates/item.json": candidate,
            "v1/receipts/item.json": receipt_value,
            "v1/work/youtube/wechter/item.json": {"state": "published"},
        })
        # Candidate was durable, but the process stopped before writing its marker.
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            manifest = Path(temporary) / "manifest.json"
            self.assertEqual(apply_candidates(store, manifest), 1)
            self.assertIn(pending_key("item"), store.values)
            # A later lost marker is restored by the bounded recovery sweep.
            store.delete_json(pending_key("item"))
            store.values[PENDING_RECONCILE_KEY]["reconciled_at"] = "2020-01-01T00:00:00Z"
            self.assertEqual(apply_candidates(store, manifest), 1)
        self.assertIn(pending_key("item"), store.values)

    def test_interrupted_first_backfill_retries_without_publishing_completion_sentinel(self):
        class InterruptingStore(MemoryStore):
            def __init__(self, values):
                super().__init__(values)
                self.interrupt = True

            def put_json(self, key, value):
                if key == pending_key("second") and self.interrupt:
                    self.interrupt = False
                    raise RuntimeError("interrupted backfill")
                super().put_json(key, value)

        store = InterruptingStore({
            f"v1/candidates/{candidate_id}.json": {"schema_version": SCHEMA_VERSION, "candidate_id": candidate_id}
            for candidate_id in ("first", "second")
        })
        with self.assertRaisesRegex(RuntimeError, "interrupted backfill"):
            reconcile_pending(store)
        self.assertNotIn(PENDING_RECONCILE_KEY, store.values)
        self.assertEqual(reconcile_pending(store)["markers_restored"], 1)
        self.assertIn(pending_key("first"), store.values)
        self.assertIn(pending_key("second"), store.values)

    def test_empty_poll_reads_only_pending_index_after_backfill(self):
        values = {}
        for number in range(1000):
            candidate_id = f"completed-{number}"
            values[f"v1/candidates/{candidate_id}.json"] = {"schema_version": SCHEMA_VERSION, "candidate_id": candidate_id}
            values[f"v1/receipts/{candidate_id}.json"] = {
                "schema_version": SCHEMA_VERSION,
                "revision": "abc",
                "deployments": {"cloudflare-pages": {"status": "verified"}, "github-pages": {"status": "verified"}},
                "notification": {"state": "not_required"},
            }
        store = MemoryStore(values)
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            manifest = Path(temporary) / "manifest.json"
            self.assertEqual(apply_candidates(store, manifest), 0)
            store.listed_prefixes.clear()
            self.assertEqual(apply_candidates(store, manifest), 0)
        self.assertEqual(store.listed_prefixes, ["v1/pending/"])

    def test_duplicate_capture_preserves_candidate_identity(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            show = load_show("wechter")
            show = replace(show, episodes_path=root / "episodes.json")
            show.episodes_path.write_text(json.dumps({"item": {"id": "item", "title": "Episode"}}), encoding="utf-8")
            baseline = root / "baseline" / show.slug
            baseline.mkdir(parents=True)
            (baseline / "episodes.json").write_text("{}", encoding="utf-8")
            store = MemoryStore()
            with patch("podcast_feeds.sync_state.load_show", return_value=show), patch("podcast_feeds.sync_state.source_fingerprint", return_value="config"), patch.dict(os.environ, {"SYNC_REQUIRE_ALLOWLIST": "0"}):
                self.assertEqual(capture(store, root / "baseline", "youtube", show_filter=show.slug), 1)
                self.assertEqual(capture(store, root / "baseline", "youtube", show_filter=show.slug), 0)
            candidates = [key for key in store.values if key.startswith("v1/candidates/")]
            self.assertEqual(len(candidates), 1)
            self.assertIn(pending_key(store.values[candidates[0]]["candidate_id"]), store.values)

    def test_repeated_metadata_transition_creates_new_candidate_after_intervening_change(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            show = replace(load_show("wechter"), episodes_path=root / "episodes.json")
            baseline = root / "baseline" / show.slug / "episodes.json"
            baseline.parent.mkdir(parents=True)
            store = MemoryStore()

            def transition(old_title, new_title):
                baseline.write_text(json.dumps({"item": {"id": "item", "title": old_title}}), encoding="utf-8")
                show.episodes_path.write_text(json.dumps({"item": {"id": "item", "title": new_title}}), encoding="utf-8")
                self.assertEqual(capture(store, root / "baseline", "youtube", show_filter=show.slug), 1)
                candidate_id = store.get_json("v1/work/youtube/wechter/item.json")["candidate_id"]
                store.put_json(f"v1/receipts/{candidate_id}.json", {
                    "schema_version": SCHEMA_VERSION,
                    "candidate_id": candidate_id,
                    "release_revision": "verified-revision",
                    "deployments": {
                        target: {"status": "verified", "revision": "verified-revision"}
                        for target in ("cloudflare-pages", "github-pages")
                    },
                    "notification": {"state": "not_required"},
                })
                return candidate_id

            with patch("podcast_feeds.sync_state.load_show", return_value=show), patch("podcast_feeds.sync_state.source_fingerprint", return_value="config"):
                first = transition("A", "B")
                second = transition("B", "A")
                third = transition("A", "B")
                self.assertEqual(len({first, second, third}), 3)

    def test_newest_uncommitted_candidate_wins_when_two_captures_share_baseline(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            show = replace(load_show("wechter"), episodes_path=root / "episodes.json")
            original = {"id": "item", "title": "A"}
            show.episodes_path.write_text(json.dumps({"item": original}), encoding="utf-8")
            values = {}
            for candidate_id, title, created_at in (
                ("a-old", "B", "2026-09-10T00:00:00Z"),
                ("z-new", "C", "2026-09-10T00:01:00Z"),
            ):
                values[f"v1/candidates/{candidate_id}.json"] = {
                    "schema_version": SCHEMA_VERSION,
                    "candidate_id": candidate_id,
                    "show_slug": show.slug,
                    "episode_id": "item",
                    "lane": "youtube",
                    "source_config_fingerprint": "config",
                    "previous_record_fingerprint": fingerprint(original),
                    "episode": {"id": "item", "title": title},
                    "created_at": created_at,
                }
                values[pending_key(candidate_id)] = {"schema_version": SCHEMA_VERSION, "candidate_id": candidate_id}
            values["v1/work/youtube/wechter/item.json"] = {
                "schema_version": SCHEMA_VERSION, "candidate_id": "z-new", "state": "ready_to_publish"
            }
            store = MemoryStore(values)
            with patch("podcast_feeds.sync_state.load_show", return_value=show), patch("podcast_feeds.sync_state.source_fingerprint", return_value="config"):
                manifest = root / "manifest.json"
                self.assertEqual(apply_candidates(store, manifest), 1)
            self.assertEqual(load_episodes(show.episodes_path)["item"]["title"], "C")
            self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))[0]["candidate_id"], "z-new")
            self.assertIn("v1/quarantine/a-old.json", store.values)

    def test_interrupted_work_pointer_update_does_not_quarantine_new_candidate(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            show = replace(load_show("wechter"), episodes_path=root / "episodes.json")
            original = {"id": "item", "title": "A"}
            show.episodes_path.write_text(json.dumps({"item": original}), encoding="utf-8")
            candidate = {
                "schema_version": SCHEMA_VERSION, "candidate_id": "new", "show_slug": show.slug,
                "episode_id": "item", "lane": "youtube", "source_config_fingerprint": "config",
                "previous_record_fingerprint": fingerprint(original),
                "episode": {"id": "item", "title": "B"},
                "created_at": "2026-09-10T00:01:00Z",
            }
            store = MemoryStore({
                PENDING_RECONCILE_KEY: {"schema_version": SCHEMA_VERSION, "reconciled_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
                "v1/candidates/old.json": {**candidate, "candidate_id": "old", "created_at": "2026-09-10T00:00:00Z"},
                "v1/candidates/new.json": candidate,
                pending_key("new"): {"schema_version": SCHEMA_VERSION, "candidate_id": "new"},
                "v1/work/youtube/wechter/item.json": {"schema_version": SCHEMA_VERSION, "candidate_id": "old", "state": "ready_to_publish"},
            })
            with patch("podcast_feeds.sync_state.load_show", return_value=show), patch("podcast_feeds.sync_state.source_fingerprint", return_value="config"):
                self.assertEqual(apply_candidates(store, root / "manifest.json"), 1)
            self.assertEqual(load_episodes(show.episodes_path)["item"]["title"], "B")
            self.assertNotIn("v1/quarantine/new.json", store.values)

    def test_new_capture_replaces_predecessor_applied_after_its_baseline(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            show = replace(load_show("wechter"), episodes_path=root / "episodes.json")
            original = {"id": "item", "title": "A"}
            previous = {"id": "item", "title": "B"}
            latest = {"id": "item", "title": "C"}
            # The publisher applied B while the source worker captured C
            # against the still-checked-out A baseline.
            show.episodes_path.write_text(json.dumps({"item": previous}), encoding="utf-8")
            old_candidate = {
                "schema_version": SCHEMA_VERSION, "candidate_id": "old", "show_slug": show.slug,
                "episode_id": "item", "lane": "youtube", "source_config_fingerprint": "config",
                "previous_record_fingerprint": fingerprint(original), "episode": previous,
                "created_at": "2026-09-10T00:00:00Z",
            }
            new_candidate = {
                **old_candidate, "candidate_id": "new", "episode": latest,
                "predecessor_candidate_id": "old", "created_at": "2026-09-10T00:01:00Z",
            }
            store = MemoryStore({
                PENDING_RECONCILE_KEY: {"schema_version": SCHEMA_VERSION, "reconciled_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
                "v1/candidates/old.json": old_candidate,
                "v1/candidates/new.json": new_candidate,
                pending_key("new"): {"schema_version": SCHEMA_VERSION, "candidate_id": "new"},
                "v1/work/youtube/wechter/item.json": {"schema_version": SCHEMA_VERSION, "candidate_id": "new", "state": "ready_to_publish"},
            })
            with patch("podcast_feeds.sync_state.load_show", return_value=show), patch("podcast_feeds.sync_state.source_fingerprint", return_value="config"):
                self.assertEqual(apply_candidates(store, root / "manifest.json"), 1)
            self.assertEqual(load_episodes(show.episodes_path)["item"], latest)
            self.assertNotIn("v1/quarantine/new.json", store.values)

            # A similarly shaped but unrelated predecessor cannot authorize
            # overwriting a changed public record.
            show.episodes_path.write_text(json.dumps({"item": previous}), encoding="utf-8")
            old_candidate["previous_record_fingerprint"] = fingerprint({"id": "item", "title": "unrelated"})
            store.values.pop("v1/quarantine/new.json", None)
            store.values[pending_key("new")] = {"schema_version": SCHEMA_VERSION, "candidate_id": "new"}
            with patch("podcast_feeds.sync_state.load_show", return_value=show), patch("podcast_feeds.sync_state.source_fingerprint", return_value="config"):
                self.assertEqual(apply_candidates(store, root / "manifest.json"), 0)
            self.assertEqual(load_episodes(show.episodes_path)["item"], previous)
            self.assertIn("v1/quarantine/new.json", store.values)

    def test_failed_notification_is_retried_but_sent_notification_is_not(self):
        item = {"candidate_id": "item", "show_slug": "wechter", "episode_id": "item", "lane": "youtube"}
        candidate = {
            "schema_version": SCHEMA_VERSION, **item,
            "previous_record_fingerprint": fingerprint(None),
            "episode": {"id": "item", "title": "New episode"},
        }
        receipt_value = {"schema_version": SCHEMA_VERSION, **item, "notification": {"state": "failed"}}
        store = MemoryStore({"v1/candidates/item.json": candidate, "v1/receipts/item.json": receipt_value})
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            manifest = Path(temporary) / "manifest.json"
            output = Path(temporary) / "notification.json"
            manifest.write_text(json.dumps([item]), encoding="utf-8")
            self.assertEqual(notification_report(store, manifest, output), 1)
            receipt_value["notification"]["state"] = "sent"
            self.assertEqual(notification_report(store, manifest, output), 0)

    def test_no_notification_retry_preserves_previous_sent_outcome(self):
        item = {"candidate_id": "item", "show_slug": "wechter", "episode_id": "item", "lane": "youtube"}
        store = MemoryStore({"v1/receipts/item.json": {
            "schema_version": SCHEMA_VERSION, **item,
            "revision": "original", "release_revision": "retry",
            "deployments": {}, "notification": {"state": "sent", "updated_at": "2026-09-10T00:00:00Z"},
        }})
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            manifest = Path(temporary) / "manifest.json"
            manifest.write_text(json.dumps([item]), encoding="utf-8")
            update_receipts(store, manifest, notification="not_required")
        self.assertEqual(store.get_json("v1/receipts/item.json")["notification"], {
            "state": "sent", "updated_at": "2026-09-10T00:00:00Z"
        })

    def test_completion_repairs_work_state_overwritten_by_concurrent_capture(self):
        item = {"candidate_id": "item", "show_slug": "wechter", "episode_id": "item", "lane": "youtube"}
        work_key = "v1/work/youtube/wechter/item.json"
        store = MemoryStore({
            work_key: {"schema_version": SCHEMA_VERSION, **item, "state": "ready_to_publish"},
            "v1/receipts/item.json": {
                "schema_version": SCHEMA_VERSION, **item,
                "release_revision": "current",
                "deployments": {"cloudflare-pages": {"status": "verified", "revision": "current"}},
                "notification": {"state": "not_required"},
            },
        })
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            manifest = Path(temporary) / "manifest.json"
            manifest.write_text(json.dumps([item]), encoding="utf-8")
            update_receipts(store, manifest, deployment="github-pages", status="verified")
        self.assertEqual(store.get_json(work_key)["state"], "published")

    def test_capture_recovers_when_receipt_completes_during_work_write(self):
        class CompletionDuringCapture(MemoryStore):
            def __init__(self):
                super().__init__()
                self.completed = False

            def put_json(self, key, value):
                super().put_json(key, value)
                if key.startswith("v1/work/") and value.get("state") == "ready_to_publish" and not self.completed:
                    self.completed = True
                    candidate_id = value["candidate_id"]
                    self.values[f"v1/receipts/{candidate_id}.json"] = {
                        "schema_version": SCHEMA_VERSION,
                        "candidate_id": candidate_id,
                        "release_revision": "current",
                        "deployments": {
                            target: {"status": "verified", "revision": "current"}
                            for target in ("cloudflare-pages", "github-pages")
                        },
                        "notification": {"state": "not_required"},
                    }
                    self.delete_json(pending_key(candidate_id))

        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            show = replace(load_show("wechter"), episodes_path=root / "episodes.json")
            show.episodes_path.write_text(json.dumps({"item": {"id": "item", "title": "B"}}), encoding="utf-8")
            baseline = root / "baseline" / show.slug
            baseline.mkdir(parents=True)
            (baseline / "episodes.json").write_text(json.dumps({"item": {"id": "item", "title": "A"}}), encoding="utf-8")
            store = CompletionDuringCapture()
            with patch("podcast_feeds.sync_state.load_show", return_value=show), patch("podcast_feeds.sync_state.source_fingerprint", return_value="config"):
                capture(store, root / "baseline", "youtube", show_filter=show.slug)
        self.assertEqual(store.get_json("v1/work/youtube/wechter/item.json")["state"], "published")

    def test_older_candidate_receipt_cannot_publish_newer_work(self):
        old = {"candidate_id": "old", "show_slug": "wechter", "episode_id": "item", "lane": "youtube"}
        work_key = "v1/work/youtube/wechter/item.json"
        store = MemoryStore({work_key: {"schema_version": SCHEMA_VERSION, **old, "candidate_id": "new", "state": "ready_to_publish"}})
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            manifest = Path(temporary) / "manifest.json"
            manifest.write_text(json.dumps([old]), encoding="utf-8")
            receipt(store, manifest, "old-revision")
        self.assertEqual(store.get_json(work_key)["state"], "ready_to_publish")

    def test_capture_interrupted_before_marker_recovers_legacy_candidate(self):
        class InterruptedStore(MemoryStore):
            def __init__(self):
                super().__init__()
                self.interrupt = True

            def put_json(self, key, value):
                if key.startswith("v1/pending/") and self.interrupt:
                    self.interrupt = False
                    raise RuntimeError("interrupted marker write")
                super().put_json(key, value)

        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            show = replace(load_show("wechter"), episodes_path=root / "episodes.json")
            show.episodes_path.write_text(json.dumps({"item": {"id": "item", "title": "Episode"}}), encoding="utf-8")
            baseline = root / "baseline" / show.slug
            baseline.mkdir(parents=True)
            (baseline / "episodes.json").write_text("{}", encoding="utf-8")
            store = InterruptedStore()
            with patch("podcast_feeds.sync_state.load_show", return_value=show), patch("podcast_feeds.sync_state.source_fingerprint", return_value="config"), patch.dict(os.environ, {"SYNC_REQUIRE_ALLOWLIST": "0"}):
                with self.assertRaisesRegex(RuntimeError, "interrupted marker write"):
                    capture(store, root / "baseline", "youtube", show_filter=show.slug)
                self.assertEqual(reconcile_pending(store)["markers_restored"], 1)
                candidate_key = next(key for key in store.values if key.startswith("v1/candidates/"))
                candidate = store.values.pop(candidate_key)
                store.delete_json(pending_key(candidate["candidate_id"]))
                candidate["candidate_id"] = "legacy-timestamped-id"
                store.put_json("v1/candidates/legacy-timestamped-id.json", candidate)
                store.put_json("v1/work/youtube/wechter/item.json", {"candidate_id": "legacy-timestamped-id"})
                self.assertEqual(capture(store, root / "baseline", "youtube", show_filter=show.slug), 0)
            self.assertEqual([key for key in store.values if key.startswith("v1/candidates/")], ["v1/candidates/legacy-timestamped-id.json"])
            self.assertIn(pending_key("legacy-timestamped-id"), store.values)

    def test_retry_updates_release_revision_without_erasing_content_commit(self):
        item = {"candidate_id": "item", "show_slug": "wechter", "episode_id": "item", "lane": "youtube"}
        store = MemoryStore({
            pending_key("item"): {"schema_version": SCHEMA_VERSION, "candidate_id": "item"},
            "v1/receipts/item.json": {
                "schema_version": SCHEMA_VERSION, **item,
                "revision": "original", "release_revision": "original", "published_at": "2026-09-10T00:00:00Z",
                "deployments": {"cloudflare-pages": {"status": "verified", "revision": "original"}, "github-pages": {"status": "failed", "revision": "original"}},
                "notification": {"state": "pending"},
            },
        })
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            manifest = Path(temporary) / "manifest.json"
            manifest.write_text(json.dumps([item]), encoding="utf-8")
            receipt(store, manifest, "retry")
            value = store.get_json("v1/receipts/item.json")
            self.assertEqual(value["revision"], "original")
            self.assertEqual(value["release_revision"], "retry")
            self.assertEqual(value["deployments"], {})
            update_receipts(store, manifest, deployment="cloudflare-pages", status="verified")
            update_receipts(store, manifest, deployment="github-pages", status="verified")
            self.assertIn(pending_key("item"), store.values)
            update_receipts(store, manifest, notification="sent")
        self.assertNotIn(pending_key("item"), store.values)

    def test_artifact_receipt_keeps_each_target_and_notification_gated(self):
        item = {"candidate_id": "artifact", "show_slug": "wechter", "episode_id": "episode", "lane": "youtube"}
        store = MemoryStore({
            pending_key("artifact"): {"schema_version": SCHEMA_VERSION, "candidate_id": "artifact"},
            "v1/receipts/artifact.json": {
                "schema_version": SCHEMA_VERSION, **item,
                "revision": "original", "release_revision": "attempt",
                "deployments": {}, "notification": {"state": "pending"},
            },
        })
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            manifest = Path(temporary) / "applied.json"
            manifest.write_text(json.dumps([item]), encoding="utf-8")
            update_receipts(store, manifest, deployment="cloudflare-pages", status="verified",
                            release_id="a" * 64, payload_digest="b" * 64)
            update_receipts(store, manifest, deployment="github-pages", status="verified")
            update_receipts(store, manifest, notification="sent")
            self.assertIn(pending_key("artifact"), store.values)
            with self.assertRaisesRegex(RuntimeError, "another payload digest"):
                update_receipts(store, manifest, deployment="github-pages", status="verified",
                                release_id="a" * 64, payload_digest="c" * 64)
            self.assertIn(pending_key("artifact"), store.values)
            update_receipts(store, manifest, deployment="github-pages", status="verified",
                            release_id="a" * 64, payload_digest="b" * 64)
        self.assertNotIn(pending_key("artifact"), store.values)
        value = store.get_json("v1/receipts/artifact.json")
        self.assertEqual(value["revision"], "original")
        self.assertEqual(value["release_revision"], "attempt")
        self.assertEqual(value["release_id"], "a" * 64)
        value["deployments"]["github-pages"]["payload_digest"] = "c" * 64
        self.assertFalse(receipt_complete(value))
        value["deployments"]["github-pages"]["payload_digest"] = "b" * 64
        value.pop("release_id")
        self.assertFalse(receipt_complete(value))

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
        report = health(store)
        self.assertEqual(report["status"], "warning")
        self.assertTrue(report["alert"])

    def test_published_work_with_old_incomplete_receipt_is_alerted(self):
        now = datetime(2026, 9, 10, 8, tzinfo=timezone.utc)
        store = MemoryStore({
            "v1/work/youtube/show/item.json": {"state": "published"},
            "v1/receipts/item.json": {
                "schema_version": SCHEMA_VERSION,
                "candidate_id": "item",
                "revision": "abc123",
                "published_at": "2026-09-10T00:00:00Z",
                "deployments": {
                    "cloudflare-pages": {"status": "verified"},
                    "github-pages": {"status": "failed"},
                },
                "notification": {"state": "pending"},
            },
        })
        with patch("podcast_feeds.sync_state.utc_now", return_value=now):
            report = health(store, persist=True)
        self.assertEqual(report["queue_size"], 0)
        self.assertEqual(report["publication"]["content_committed"], 1)
        self.assertEqual(report["publication"]["production_verified"], 0)
        self.assertEqual(report["publication"]["primary"]["verified"], 1)
        self.assertEqual(report["publication"]["mirror"]["failed"], 1)
        self.assertEqual(report["publication"]["notification"]["pending"], 1)
        self.assertEqual(report["publication"]["incomplete_over_6h"], 1)
        self.assertTrue(report["alert"])
        self.assertEqual(report["notification_transition"], "opened")

        store.values["v1/receipts/item.json"]["deployments"]["github-pages"]["status"] = "verified"
        store.values["v1/receipts/item.json"]["notification"]["state"] = "not_required"
        with patch("podcast_feeds.sync_state.utc_now", return_value=now):
            recovered = health(store, persist=True)
        self.assertEqual(recovered["publication"]["production_verified"], 1)
        self.assertEqual(recovered["publication"]["complete"], 1)
        self.assertFalse(recovered["alert"])
        self.assertEqual(recovered["notification_transition"], "recovered")

    def test_recent_committed_receipt_warns_without_incident(self):
        now = datetime(2026, 9, 10, 8, tzinfo=timezone.utc)
        store = MemoryStore({"v1/receipts/item.json": {
            "schema_version": SCHEMA_VERSION,
            "published_at": "2026-09-10T07:00:00Z",
            "deployments": {},
            "notification": {"state": "pending"},
        }})
        with patch("podcast_feeds.sync_state.utc_now", return_value=now):
            report = health(store, persist=True)
        self.assertEqual(report["status"], "warning")
        self.assertFalse(report["alert"])
        self.assertIsNone(report["notification_transition"])
        self.assertEqual(report["publication"]["awaiting_completion"], 1)

    def test_incomplete_legacy_receipt_without_timestamp_cannot_look_healthy(self):
        store = MemoryStore({"v1/receipts/legacy.json": {
            "schema_version": SCHEMA_VERSION,
            "deployments": {},
            "notification": {"state": "pending"},
        }})
        report = health(store)
        self.assertEqual(report["publication"]["incomplete_without_timestamp"], 1)
        self.assertTrue(report["alert"])

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
