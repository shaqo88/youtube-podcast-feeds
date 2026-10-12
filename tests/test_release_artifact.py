from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from podcast_feeds.release_artifact import canonical, create_release, digest, verify_release
from podcast_feeds.release_pipeline import fetch, recover_index
from podcast_feeds.release_store import ReleaseStore
from tests.test_release_store import FakeS3


class ReleaseArtifactTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        self.run_git("init", "-b", "main")
        self.run_git("config", "user.name", "Fixture")
        self.run_git("config", "user.email", "fixture@example.test")
        self.run_git("config", "core.autocrlf", "false")
        (self.root / "public").mkdir()
        (self.root / "public" / "index.html").write_text("<html>public route</html>\n", encoding="utf-8")
        (self.root / "public" / "feed.xml").write_text("<rss/>\n", encoding="utf-8")
        (self.root / "requirements.txt").write_text("feedgen==1.0.0\n", encoding="utf-8")
        self.run_git("add", ".")
        self.run_git("commit", "-m", "fixture")
        self.revision = self.run_git("rev-parse", "HEAD")
        self.run_git("update-ref", "refs/remotes/origin/main", self.revision)
        self.bundle = Path(self.temporary.name) / "bundle"
        self.validations = 0

    def run_git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True).stdout.strip()

    def validator(self, _root: Path, extracted: Path) -> None:
        self.validations += 1
        self.assertEqual((extracted / "index.html").read_text(encoding="utf-8"), "<html>public route</html>\n")

    def create(self) -> tuple[bytes, Path]:
        release_id, manifest = create_release(self.root, self.revision, self.bundle, validate=self.validator)
        raw = (self.bundle / "manifest.json").read_bytes()
        self.assertEqual(release_id, digest(raw))
        self.assertEqual(manifest["source_revision"], self.revision)
        self.assertEqual(self.validations, 1)
        return raw, self.bundle / "payload.zip"

    def test_exact_package_is_reused_for_two_targets_without_rendering(self) -> None:
        manifest, archive = self.create()
        first = Path(self.temporary.name) / "primary"
        second = Path(self.temporary.name) / "mirror"
        self.assertEqual(verify_release(self.root, self.revision, manifest, archive, first), digest(manifest))
        self.assertEqual(verify_release(self.root, self.revision, manifest, archive, second), digest(manifest))
        self.assertEqual((first / "index.html").read_bytes(), (second / "index.html").read_bytes())
        self.assertEqual(self.validations, 1)

    def test_corrupt_archive_and_incomplete_inventory_fail(self) -> None:
        manifest, archive = self.create()
        with archive.open("ab") as stream:
            stream.write(b"corruption")
        with self.assertRaisesRegex(ValueError, "digest/size mismatch"):
            verify_release(self.root, self.revision, manifest, archive, Path(self.temporary.name) / "bad")
        archive.unlink()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("index.html", b"<html>public route</html>\n")
        altered = json.loads(manifest)
        altered["payload_digest"] = digest(archive.read_bytes())
        altered["payload_size"] = archive.stat().st_size
        with self.assertRaisesRegex(ValueError, "incomplete"):
            verify_release(self.root, self.revision, canonical(altered), archive, Path(self.temporary.name) / "missing")

    def test_rejects_archive_member_marked_as_symlink(self) -> None:
        manifest, archive = self.create()
        original = json.loads(manifest)
        with zipfile.ZipFile(archive, "w") as output:
            for name in sorted(original["files"]):
                member = zipfile.ZipInfo(name)
                member.external_attr = 0o120777 << 16
                output.writestr(member, (self.root / "public" / name).read_bytes())
        original["payload_digest"] = digest(archive.read_bytes())
        original["payload_size"] = archive.stat().st_size
        with self.assertRaisesRegex(ValueError, "Unsafe or mismatched release member"):
            verify_release(self.root, self.revision, canonical(original), archive,
                           Path(self.temporary.name) / "symlink")

    def test_untrusted_manifest_and_non_main_revision_fail(self) -> None:
        manifest, archive = self.create()
        altered = json.loads(manifest)
        altered["repository"] = "someone/else"
        with self.assertRaisesRegex(ValueError, "provenance"):
            verify_release(self.root, self.revision, canonical(altered), archive, Path(self.temporary.name) / "foreign")
        self.run_git("update-ref", "-d", "refs/remotes/origin/main")
        with self.assertRaisesRegex(ValueError, "not on main"):
            verify_release(self.root, self.revision, manifest, archive, Path(self.temporary.name) / "unmerged")

    def test_public_bytes_must_match_committed_git_tree(self) -> None:
        (self.root / "public" / "feed.xml").write_text("<rss>changed</rss>\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "differs from committed revision"):
            create_release(self.root, self.revision, self.bundle, validate=self.validator)

    def test_source_inputs_must_match_committed_git_tree(self) -> None:
        (self.root / "requirements.txt").write_text("feedgen==9.9.9\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Source input differs from committed revision: requirements.txt"):
            create_release(self.root, self.revision, self.bundle, validate=self.validator)

    def test_exact_payload_rejects_missing_episode_route(self) -> None:
        (self.root / "public" / "search-index.json").write_text(json.dumps({
            "schema_version": 1,
            "episodes": [{"id": "show:one", "page_url": "show/episodes/missing/",
                          "audio_url": "https://example.test/one.mp3"}],
        }), encoding="utf-8")
        self.run_git("add", ".")
        self.run_git("commit", "-m", "missing episode route")
        self.revision = self.run_git("rev-parse", "HEAD")
        self.run_git("update-ref", "refs/remotes/origin/main", self.revision)
        with patch("podcast_feeds.release_artifact.load_enabled_shows", return_value=[]):
            with self.assertRaisesRegex(ValueError, "episode route is missing"):
                create_release(self.root, self.revision, self.bundle)

    def test_exact_payload_rejects_wrong_account_environment(self) -> None:
        (self.root / "public" / "search-index.json").write_text(
            json.dumps({"schema_version": 1, "episodes": []}), encoding="utf-8",
        )
        (self.root / "config").mkdir()
        (self.root / "config" / "accounts.production.json").write_text(
            json.dumps({"environment": "production", "listenerAccounts": True}), encoding="utf-8",
        )
        (self.root / "public" / "accounts-config.json").write_text(
            json.dumps({"environment": "preview", "listenerAccounts": True}), encoding="utf-8",
        )
        self.run_git("add", ".")
        self.run_git("commit", "-m", "wrong account environment")
        self.revision = self.run_git("rev-parse", "HEAD")
        self.run_git("update-ref", "refs/remotes/origin/main", self.revision)
        with patch("podcast_feeds.release_artifact.load_enabled_shows", return_value=[]):
            with self.assertRaisesRegex(ValueError, "account configuration differs"):
                create_release(self.root, self.revision, self.bundle)

    def test_partial_target_retry_and_offline_recovery_use_retained_payload(self) -> None:
        manifest, archive = self.create()
        release_id = digest(manifest)
        client = FakeS3()
        store = ReleaseStore("fixture", client)
        store.put_release(release_id, manifest, archive)
        source_puts = len(client.puts)
        with patch("requests.get", side_effect=AssertionError("upstream fetch")), patch(
            "urllib.request.urlopen", side_effect=AssertionError("upstream network")
        ):
            primary = Path(self.temporary.name) / "primary"
            mirror = Path(self.temporary.name) / "mirror"
            fetch(self.root, self.revision, release_id, primary, Path(self.temporary.name) / "primary-bundle", store)
            # A failed target deploy does not alter the retained bytes or the
            # successful target; only that target is prepared again.
            with self.assertRaisesRegex(RuntimeError, "target unavailable"):
                raise RuntimeError("target unavailable")
            fetch(self.root, self.revision, release_id, mirror, Path(self.temporary.name) / "mirror-bundle", store)
            self.assertEqual((primary / "index.html").read_bytes(), (mirror / "index.html").read_bytes())
            self.assertEqual(len(client.puts), source_puts)

    def test_lost_revision_index_recovers_offline_but_corrupt_index_fails_closed(self) -> None:
        manifest, archive = self.create()
        release_id = digest(manifest)
        client = FakeS3()
        store = ReleaseStore("fixture", client)
        store.put_release(release_id, manifest, archive)
        index_key = store._revision_key(self.revision)
        client.objects.pop(index_key)
        with self.assertRaises(FileNotFoundError):
            fetch(self.root, self.revision, release_id, Path(self.temporary.name) / "missing-index",
                  Path(self.temporary.name) / "missing-index-bundle", store)
        with patch("requests.get", side_effect=AssertionError("upstream fetch")), patch(
            "urllib.request.urlopen", side_effect=AssertionError("upstream network")
        ):
            self.assertEqual(recover_index(self.root, self.revision, release_id,
                                           Path(self.temporary.name) / "recovery-bundle", store), release_id)
            self.assertEqual(store.release_id_for_revision(self.revision), release_id)
            fetch(self.root, self.revision, release_id, Path(self.temporary.name) / "recovered-target",
                  Path(self.temporary.name) / "recovered-bundle", store)
        self.assertEqual((Path(self.temporary.name) / "recovered-target" / "index.html").read_text(),
                         "<html>public route</html>\n")
        client.objects[index_key] = b"{corrupt"
        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            recover_index(self.root, self.revision, release_id,
                          Path(self.temporary.name) / "corrupt-recovery-bundle", store)
        self.assertEqual(client.objects[index_key], b"{corrupt")


if __name__ == "__main__":
    unittest.main()
