import json
import gzip
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
                "latest_episode_date",
                "episode_dates",
            },
        )

    def test_committed_metadata_matches_generator(self):
        committed = json.loads(
            Path("public/catalog-meta.json").read_text(encoding="utf-8")
        )
        self.assertEqual(committed, _catalog_metadata())


class RedesignedSiteContractTests(unittest.TestCase):
    def test_destination_routes_are_generated(self):
        for route, marker in (
            ("subscriptions", "data-subscriptions-page"),
            ("search", "data-search-page"),
            ("queue", "data-queue-list"),
        ):
            page = Path("public", route, "index.html")
            self.assertTrue(page.is_file(), route)
            self.assertIn(marker, page.read_text(encoding="utf-8"))

    def test_search_index_is_compact_private_and_versioned(self):
        path = Path("public/search-index.json")
        raw = path.read_bytes()
        payload = json.loads(raw)
        self.assertEqual(payload["schema_version"], 1)
        self.assertLessEqual(len(gzip.compress(raw)), 1_500_000)
        allowed = {"id", "title", "show_slug", "published", "duration", "audio_url", "page_url"}
        self.assertTrue(payload["episodes"])
        for episode in payload["episodes"]:
            self.assertEqual(set(episode), allowed)
            self.assertNotIn("description", episode)
            self.assertNotIn("email", episode)
            self.assertTrue(episode["page_url"].startswith(f'{episode["show_slug"]}/index.html#episode-'))

    def test_search_index_is_not_install_precached(self):
        worker = Path("public/sw.js").read_text(encoding="utf-8")
        shell = worker[worker.index("const SHELL_ASSETS"):worker.index("];", worker.index("const SHELL_ASSETS"))]
        self.assertNotIn("search-index.json", shell)


if __name__ == "__main__":
    unittest.main()
