import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from podcast_feeds.episode_notifications import load_new_episodes_report
from podcast_feeds.operational_health import build_operational_report, render_markdown


STATUS = {
    "generated_at": "2026-07-21T00:00:00Z",
    "shows": [
        {
            "slug": "hosted",
            "title": "Hosted",
            "feed_url": "https://torah-pod.pages.dev/hosted/feed.xml",
            "episode_count": 2,
            "latest_episode": {"title": "New", "published": "20260720"},
            "platforms": {"apple": "https://podcasts.apple.com/show"},
            "sources": [{"type": "youtube"}],
        },
        {
            "slug": "external",
            "title": "External",
            "feed_url": "https://feeds.example/external.xml",
            "episode_count": 5,
            "latest_episode": {"title": "Latest", "published": "20260701"},
            "platforms": {"spotify": "https://open.spotify.com/show/test"},
            "sources": [{"type": "existing_feed"}],
        },
    ],
}


class OperationalHealthTests(unittest.TestCase):
    def test_combines_show_availability_storage_and_directories(self):
        report = build_operational_report(
            STATUS,
            r2_report={
                "prefixes": [
                    {"prefix": "one", "show_slug": "hosted", "bytes": 100, "objects": 2},
                    {"prefix": "two", "show_slug": "hosted", "bytes": 50, "objects": 1},
                ],
                "unmapped": {"bytes": 5, "objects": 1, "prefixes": ["stray"]},
            },
            availability_report={
                "shows": [
                    {
                        "slug": "hosted",
                        "status": "ok",
                        "feed_status": 200,
                        "enclosure_status": 206,
                        "range_supported": True,
                    }
                ]
            },
            today=date(2026, 7, 22),
        )

        hosted, external = report["shows"]
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["hosted_show_count"], 1)
        self.assertEqual(hosted["latest_episode"]["age_days"], 2)
        self.assertEqual(hosted["storage"], {"status": "available", "bytes": 150, "objects": 3})
        self.assertTrue(hosted["feed_health"]["range_supported"])
        self.assertEqual(hosted["directories"]["spotify"]["status"], "not_recorded")
        self.assertEqual(external["feed_health"]["status"], "not_applicable")
        self.assertEqual(external["storage"]["status"], "not_applicable")
        self.assertEqual(report["unmapped_storage"]["objects"], 1)

    def test_missing_provider_data_is_explicit_not_success(self):
        report = build_operational_report(
            STATUS,
            r2_report=None,
            availability_report=None,
            today=date(2026, 7, 22),
        )

        hosted = report["shows"][0]
        self.assertEqual(hosted["status"], "unavailable")
        self.assertEqual(hosted["feed_health"]["status"], "unavailable")
        self.assertEqual(hosted["storage"]["status"], "unavailable")
        self.assertEqual(report["providers"], {"availability": "unavailable", "r2": "unavailable"})

    def test_feed_failure_makes_report_fail(self):
        report = build_operational_report(
            STATUS,
            r2_report={"prefixes": []},
            availability_report={
                "shows": [
                    {"slug": "hosted", "status": "error", "error": "network_error"}
                ]
            },
            today=date(2026, 7, 22),
        )

        self.assertEqual(report["status"], "error")
        self.assertEqual(report["counts"]["error"], 1)
        markdown = render_markdown(report)
        self.assertIn("`hosted`", markdown)
        self.assertIn("network", report["shows"][0]["feed_health"]["error"])

    def test_partial_show_data_does_not_crash_health_report(self):
        report = build_operational_report(
            {
                "generated_at": "2026-07-21T00:00:00Z",
                "shows": [
                    {
                        "slug": "broken",
                        "title": "Broken",
                        "feed_url": "https://torah-pod.pages.dev/broken/feed.xml",
                        "episode_count": 0,
                        "latest_episode": None,
                        "platforms": None,
                        "sources": None,
                    }
                ],
            },
            r2_report=None,
            availability_report=None,
            today=date(2026, 7, 22),
        )

        self.assertEqual(report["shows"][0]["status"], "unavailable")
        self.assertEqual(report["shows"][0]["source_types"], [])

    def test_empty_report_file_is_treated_as_no_new_episodes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "new-episodes.json"
            report_path.write_text("", encoding="utf-8")
            self.assertEqual(load_new_episodes_report(report_path), [])


if __name__ == "__main__":
    unittest.main()
