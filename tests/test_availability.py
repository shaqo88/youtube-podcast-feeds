import unittest

from podcast_feeds.availability import (
    AvailabilityError,
    check_catalog,
    check_show,
    notification_transition,
    parse_latest_enclosure,
)


FEED = b"""<?xml version="1.0"?>
<rss><channel><title>Test</title>
  <item><title>Newest</title><guid>episode-2</guid><pubDate>Wed, 22 Jul 2026 10:00:00 GMT</pubDate>
    <enclosure url="https://media.example/new.mp3" type="audio/mpeg" length="123" />
  </item>
  <item><title>Older</title><guid>episode-1</guid>
    <enclosure url="https://media.example/old.mp3" type="audio/mpeg" length="100" />
  </item>
</channel></rss>"""


class AvailabilityTests(unittest.TestCase):
    def test_notifications_are_emitted_only_for_state_transitions(self):
        self.assertEqual(notification_transition("failure", "success"), "failure")
        self.assertEqual(notification_transition("failure", "unknown"), "failure")
        self.assertEqual(notification_transition("failure", "failure"), "none")
        self.assertEqual(notification_transition("success", "failure"), "recovery")
        self.assertEqual(notification_transition("success", "success"), "none")

    def test_parses_newest_feed_enclosure(self):
        latest = parse_latest_enclosure(FEED)

        self.assertEqual(latest["item_count"], 2)
        self.assertEqual(latest["guid"], "episode-2")
        self.assertEqual(latest["enclosure_url"], "https://media.example/new.mp3")

    def test_rejects_empty_or_unsafe_feeds(self):
        with self.assertRaisesRegex(AvailabilityError, "empty_feed"):
            parse_latest_enclosure(b"<rss><channel /></rss>")
        with self.assertRaisesRegex(AvailabilityError, "invalid_enclosure_url"):
            parse_latest_enclosure(
                b'<rss><channel><item><enclosure url="http://internal/file" type="audio/mpeg" /></item></channel></rss>'
            )

    def test_checks_feed_and_one_byte_enclosure_range(self):
        calls = []

        def response_reader(url, *, headers=None):
            calls.append((url, headers))
            if headers:
                return 206, {"content-range": "bytes 0-0/123", "content-type": "audio/mpeg"}, b"x"
            return 200, {"content-type": "application/rss+xml"}, FEED

        result = check_show(
            {"slug": "alpha", "feed_url": "https://torah-pod.pages.dev/alpha/feed.xml"},
            response_reader=response_reader,
        )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["range_supported"])
        self.assertEqual(calls[1][1], {"Range": "bytes=0-0"})

    def test_reports_bounded_failure_category(self):
        def response_reader(url, *, headers=None):
            if headers:
                return 200, {"content-type": "audio/mpeg"}, b"whole-file"
            return 200, {"content-type": "application/rss+xml"}, FEED

        result = check_show(
            {"slug": "alpha", "feed_url": "https://torah-pod.pages.dev/alpha/feed.xml"},
            response_reader=response_reader,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "enclosure_range_http_error")

    def test_catalog_filters_hosts_and_sorts_results(self):
        def response_reader(url, *, headers=None):
            if headers:
                return 206, {"content-range": "bytes 0-0/123", "content-type": "audio/mpeg"}, b"x"
            return 200, {"content-type": "application/rss+xml"}, FEED

        report = check_catalog(
            [
                {"slug": "zeta", "feed_url": "https://torah-pod.pages.dev/zeta/feed.xml"},
                {"slug": "external", "feed_url": "https://feeds.example/external.xml"},
                {"slug": "alpha", "feed_url": "https://torah-pod.pages.dev/alpha/feed.xml"},
            ],
            host_prefix="https://torah-pod.pages.dev/",
            response_reader=response_reader,
        )

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["checked_shows"], 2)
        self.assertEqual([item["slug"] for item in report["shows"]], ["alpha", "zeta"])


if __name__ == "__main__":
    unittest.main()
