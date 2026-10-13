from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from botocore.exceptions import ClientError

from podcast_feeds.release_store import ReleaseStore


REVISION = "a" * 40


def missing() -> ClientError:
    return ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")


def conflict() -> ClientError:
    return ClientError({"Error": {"Code": "PreconditionFailed", "Message": "exists"}}, "PutObject")


class FakeS3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.puts: list[str] = []
        self.fail_before: str | None = None
        self.fail_after: str | None = None

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise missing()
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, *, Bucket, Key, Body, ContentType, IfNoneMatch):
        assert IfNoneMatch == "*"
        if self.fail_before == Key:
            self.fail_before = None
            raise ClientError({"Error": {"Code": "ServiceUnavailable"}}, "PutObject")
        if Key in self.objects:
            raise conflict()
        self.objects[Key] = Body if isinstance(Body, bytes) else Body.read()
        self.puts.append(Key)
        if self.fail_after == Key:
            self.fail_after = None
            raise ClientError({"Error": {"Code": "ServiceUnavailable"}}, "PutObject")


def bundle(payload: bytes, revision: str = REVISION) -> tuple[str, bytes, bytes]:
    manifest = (json.dumps({
        "schema_version": 1,
        "source_revision": revision,
        "payload_digest": hashlib.sha256(payload).hexdigest(),
    }, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return hashlib.sha256(manifest).hexdigest(), manifest, payload


class ReleaseStoreTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeS3()
        self.store = ReleaseStore("release-fixture", self.client)

    def test_retains_exact_bytes_and_previous_release_without_expiry(self):
        first_id, first_manifest, first_payload = bundle(b"first ZIP")
        second_id, second_manifest, second_payload = bundle(b"second ZIP", "b" * 40)
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            payload_path = Path(directory, "payload.zip")
            payload_path.write_bytes(first_payload)
            self.store.put_release(first_id, first_manifest, payload_path)
            first_puts = list(self.client.puts)
            self.store.put_release(first_id, first_manifest, payload_path)
            self.assertEqual(self.client.puts, first_puts)
            self.store.put_release(second_id, second_manifest, second_payload)
            output = Path(directory, "download.zip")
            self.assertEqual(self.store.get_release(first_id, output), (first_manifest, output))
            self.assertEqual(output.read_bytes(), first_payload)
        self.assertEqual(self.store.get_release(second_id), (second_manifest, second_payload))
        self.assertEqual(self.store.release_id_for_revision(REVISION), first_id)
        self.assertEqual(self.store.release_id_for_revision("b" * 40), second_id)
        self.assertEqual(len(self.client.objects), 6)

    def test_rejects_missing_and_corrupted_objects(self):
        release_id, manifest, payload = bundle(b"valid ZIP")
        with self.assertRaises(FileNotFoundError):
            self.store.get_release(release_id)
        self.store.put_release(release_id, manifest, payload)
        manifest_key = self.store._manifest_key(release_id)
        payload_key = self.store._payload_key(hashlib.sha256(payload).hexdigest())
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            output = Path(directory, "download.zip")
            output.write_bytes(b"previous good local copy")
            self.client.objects[payload_key] = b"tampered"
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                self.store.get_release(release_id, output)
            self.assertEqual(output.read_bytes(), b"previous good local copy")
        self.client.objects[payload_key] = payload
        self.client.objects.pop(payload_key)
        with self.assertRaises(FileNotFoundError):
            self.store.get_release(release_id)
        self.client.objects[payload_key] = payload
        self.client.objects[manifest_key] = b"tampered manifest"
        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            self.store.get_release(release_id)
        self.client.objects.pop(manifest_key)
        with self.assertRaises(FileNotFoundError):
            self.store.get_release(release_id)

    def test_rejects_mismatched_input_and_existing_object(self):
        release_id, manifest, payload = bundle(b"valid ZIP")
        with self.assertRaisesRegex(ValueError, "payload bytes differ"):
            self.store.put_release(release_id, manifest, b"wrong ZIP")
        with self.assertRaisesRegex(ValueError, "release_id"):
            self.store.put_release("0" * 64, manifest, payload)
        self.client.objects[self.store._payload_key(hashlib.sha256(payload).hexdigest())] = b"corrupt existing"
        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            self.store.put_release(release_id, manifest, payload)

    def test_interrupted_manifest_or_index_write_recovers_on_retry(self):
        release_id, manifest, payload = bundle(b"valid ZIP")
        manifest_key = self.store._manifest_key(release_id)
        index_key = self.store._revision_key(REVISION)
        self.client.fail_before = manifest_key
        with self.assertRaises(ClientError):
            self.store.put_release(release_id, manifest, payload)
        with self.assertRaises(FileNotFoundError):
            self.store.release_id_for_revision(REVISION)
        self.assertEqual(len(self.client.objects), 1)  # payload uploaded once
        self.client.fail_before = index_key
        with self.assertRaises(ClientError):
            self.store.put_release(release_id, manifest, payload)
        self.assertEqual(len(self.client.objects), 2)
        with self.assertRaises(FileNotFoundError):
            self.store.get_release(release_id)  # no complete by-revision index yet
        self.store.put_release(release_id, manifest, payload)
        self.assertEqual(self.store.release_id_for_revision(REVISION), release_id)
        self.assertEqual(len(self.client.puts), 3)

    def test_lost_upload_response_is_reconciled_by_readback(self):
        release_id, manifest, payload = bundle(b"valid ZIP")
        self.client.fail_after = self.store._payload_key(hashlib.sha256(payload).hexdigest())
        self.store.put_release(release_id, manifest, payload)
        self.assertEqual(self.store.get_release(release_id), (manifest, payload))

    def test_revision_index_cannot_be_reassigned_by_equivalent_rebuild(self):
        first_id, first_manifest, first_payload = bundle(b"first ZIP")
        second_id, second_manifest, second_payload = bundle(b"rebuilt ZIP")
        self.store.put_release(first_id, first_manifest, first_payload)
        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            self.store.put_release(second_id, second_manifest, second_payload)
        self.assertEqual(self.store.release_id_for_revision(REVISION), first_id)
        self.assertEqual(self.store.get_release(first_id), (first_manifest, first_payload))

    def test_corrupt_or_missing_revision_index_fails_closed(self):
        release_id, manifest, payload = bundle(b"valid ZIP")
        self.store.put_release(release_id, manifest, payload)
        key = self.store._revision_key(REVISION)
        self.client.objects[key] = b'{"release_id":"bad"}\n'
        with self.assertRaisesRegex(RuntimeError, "invalid"):
            self.store.release_id_for_revision(REVISION)
        self.client.objects.pop(key)
        with self.assertRaises(FileNotFoundError):
            self.store.get_release(release_id)

    def test_lost_index_can_be_read_only_with_explicit_recovery_bypass(self):
        release_id, manifest, payload = bundle(b"valid ZIP")
        self.store.put_release(release_id, manifest, payload)
        self.client.objects.pop(self.store._revision_key(REVISION))
        with self.assertRaises(FileNotFoundError):
            self.store.get_release(release_id)
        self.assertEqual(
            self.store.get_release(release_id, require_index=False),
            (manifest, payload),
        )
        self.store.put_release(release_id, manifest, payload)
        self.assertEqual(self.store.get_release(release_id), (manifest, payload))


if __name__ == "__main__":
    unittest.main()
