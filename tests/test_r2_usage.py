import unittest

from podcast_feeds.r2_usage import render_markdown, summarize_usage


class R2UsageTests(unittest.TestCase):
    def test_maps_configured_prefixes_and_aggregates_objects(self):
        report = summarize_usage(
            "media",
            [
                {"Key": "show-a/one.mp3", "Size": 100},
                {"Key": "show-a/two.mp3", "Size": 200},
                {"Key": "show-b/one.mp3", "Size": 50},
            ],
            {"show-a": "alpha", "show-b": "beta"},
        )

        self.assertEqual(report["total_bytes"], 350)
        self.assertEqual(report["total_objects"], 3)
        self.assertEqual(report["prefixes"][0]["show_slug"], "alpha")
        self.assertEqual(report["prefixes"][0]["objects"], 2)
        self.assertEqual(report["unmapped"]["objects"], 0)

    def test_reports_unknown_and_root_objects_separately(self):
        report = summarize_usage(
            "media",
            [
                {"Key": "known/one.mp3", "Size": 100},
                {"Key": "stray/file.mp3", "Size": 25},
                {"Key": "orphan.mp3", "Size": 10},
            ],
            {"known": "alpha"},
        )

        self.assertEqual(report["unmapped"]["bytes"], 35)
        self.assertEqual(report["unmapped"]["objects"], 2)
        self.assertEqual(set(report["unmapped"]["prefixes"]), {"stray", "(root)"})

        markdown = render_markdown(report, warning_gb=7, critical_gb=9)
        self.assertIn("Warning: 2 unmapped object(s)", markdown)
        self.assertIn("`stray`", markdown)
        self.assertIn("`(root)`", markdown)

    def test_empty_bucket_has_explicit_zero_unmapped_summary(self):
        report = summarize_usage("media", [], {"known": "alpha"})

        self.assertEqual(report["prefixes"], [])
        self.assertEqual(
            report["unmapped"],
            {"bytes": 0, "objects": 0, "prefixes": []},
        )


if __name__ == "__main__":
    unittest.main()
