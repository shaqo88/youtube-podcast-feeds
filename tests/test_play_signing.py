import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("play_signing", Path(__file__).resolve().parents[1] / "scripts/check-play-signing.py")
signing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(signing)


class PlaySigningTests(unittest.TestCase):
    def test_selects_base_instead_of_configuration_split(self):
        self.assertEqual(signing.select_download({"generatedSplitApks": [
            {"moduleName": "base", "splitId": "config.en", "downloadId": "language"},
            {"moduleName": "feature", "downloadId": "feature"},
            {"moduleName": "base", "downloadId": "base"},
        ]}), "base")
        with self.assertRaises(ValueError):
            signing.select_download({"generatedSplitApks": [{"moduleName": "base", "splitId": "config.en", "downloadId": "language"}]})

    def test_rejects_certificate_that_differs_from_play(self):
        output = f"Signer #1 certificate SHA-1 digest: {'a' * 40}\nSigner #1 certificate SHA-256 digest: {'b' * 64}\n"
        self.assertEqual(signing.certificate_digests(output, "b" * 64)["sha1"], "A" * 40)
        with self.assertRaises(ValueError):
            signing.certificate_digests(output, "c" * 64)
        with self.assertRaises(ValueError):
            signing.certificate_digests(output + output.replace("#1", "#2"), "b" * 64)
