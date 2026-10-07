import unittest
from scripts.publisher_publication_receipt import verified


class PublicationReceiptTest(unittest.TestCase):
    def test_requires_real_cloudflare_revision_and_catalog_show(self):
        revision = 'a' * 40
        manifest = {'target': 'cloudflare-pages', 'revision': revision}
        self.assertTrue(verified(manifest, [{'slug': 'example'}], 'example', revision))
        self.assertFalse(verified(manifest, [], 'example', revision))
        self.assertFalse(verified(manifest, [{'slug': 'example'}], 'example', 'b' * 40))
        self.assertFalse(verified({'target': 'github-pages', 'revision': revision}, [{'slug': 'example'}], 'example', revision))
