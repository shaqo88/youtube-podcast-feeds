import unittest

from podcast_feeds.site import _search_excerpt


class SearchExcerptTests(unittest.TestCase):
    def test_strips_markup_and_collapses_whitespace(self):
        self.assertEqual(_search_excerpt("<p>Hello   world</p>"), "Hello world")

    def test_caps_at_word_boundary(self):
        value = "one two three four"
        self.assertEqual(_search_excerpt(value, limit=12), "one two")

    def test_keeps_short_text(self):
        self.assertEqual(_search_excerpt("short", limit=10), "short")


if __name__ == "__main__":
    unittest.main()
