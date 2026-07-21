import json
import unittest
from pathlib import Path

from podcast_feeds.site import CATALOG_SCHEMA_VERSION, _catalog_metadata, _search_excerpt


class SearchExcerptTests(unittest.TestCase):
    def test_strips_markup_and_collapses_whitespace(self):
        self.assertEqual(_search_excerpt("<p>Hello   world</p>"), "Hello world")

    def test_caps_at_word_boundary(self):
        value = "one two three four"
        self.assertEqual(_search_excerpt(value, limit=12), "one two")

    def test_keeps_short_text(self):
        self.assertEqual(_search_excerpt("short", limit=10), "short")


class CatalogMetadataTests(unittest.TestCase):
    def test_preserves_array_contract_and_stable_identity(self):
        metadata = _catalog_metadata()

        self.assertEqual(metadata["schema_version"], CATALOG_SCHEMA_VERSION)
        self.assertEqual(metadata["catalog_url"], "catalog.json")
        self.assertEqual(metadata["top_level"], "array")
        self.assertEqual(metadata["item_identity"], "slug")

    def test_documents_every_current_catalog_field(self):
        self.assertEqual(
            set(_catalog_metadata()["fields"]),
            {
                "slug",
                "title",
                "author",
                "description",
                "feed_url",
                "artwork_url",
                "platforms",
                "episode_count",
            },
        )

    def test_committed_metadata_matches_generator(self):
        committed = json.loads(
            Path("public/catalog-meta.json").read_text(encoding="utf-8")
        )
        self.assertEqual(committed, _catalog_metadata())


if __name__ == "__main__":
    unittest.main()
