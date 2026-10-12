"""Retain validated release bundles in a private, S3-compatible R2 bucket.

Objects are addressed by SHA-256 and written only when absent. There is no
delete or expiry operation here: deployment receipts decide which historical
releases are useful, and a failed or partial upload must remain retryable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_PREFIX = "releases/v1"
_CHUNK = 1024 * 1024


def _sha256(source: bytes | Path) -> str:
    digest = hashlib.sha256()
    if isinstance(source, bytes):
        digest.update(source)
    else:
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(_CHUNK), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _manifest_identity(manifest_bytes: bytes) -> tuple[str, str]:
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("release manifest is not valid JSON") from exc
    digest = manifest.get("payload_digest") if isinstance(manifest, dict) else None
    revision = manifest.get("source_revision") if isinstance(manifest, dict) else None
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise ValueError("release manifest needs a lowercase SHA-256 payload_digest")
    if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
        raise ValueError("release manifest needs a full lowercase source_revision")
    return revision, digest


def _missing(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}


class ReleaseStore:
    """A retained, immutable mapping from manifest digest to manifest and ZIP.

    ``release_id`` is SHA-256 of the exact manifest bytes. The manifest names
    the SHA-256 of the exact ``payload.zip`` bytes. For large releases, pass a
    Path to both put_release and get_release so the archive stays off the heap.
    """

    def __init__(self, bucket: str, client: Any):
        if not bucket or not bucket.strip():
            raise ValueError("release bucket is required")
        self.bucket = bucket.strip()
        self.client = client

    @classmethod
    def from_environment(cls) -> "ReleaseStore":
        bucket = os.environ.get("R2_RELEASE_BUCKET", "").strip()
        if not bucket:
            raise RuntimeError("R2_RELEASE_BUCKET is required for durable releases")
        account_id = os.environ["R2_RELEASE_ACCOUNT_ID"]
        access_key = os.environ["R2_RELEASE_ACCESS_KEY"]
        secret_key = os.environ["R2_RELEASE_SECRET_KEY"]
        client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
            config=Config(connect_timeout=30, read_timeout=120, retries={"max_attempts": 2}),
        )
        return cls(bucket, client)

    @staticmethod
    def _manifest_key(release_id: str) -> str:
        return f"{_PREFIX}/manifests/{release_id}.json"

    @staticmethod
    def _payload_key(payload_digest: str) -> str:
        return f"{_PREFIX}/payloads/{payload_digest}.zip"

    @staticmethod
    def _revision_key(source_revision: str) -> str:
        return f"{_PREFIX}/by-revision/{source_revision}.json"

    def _exists_verified(self, key: str, expected_digest: str) -> bool:
        """Stream an existing object solely for its checksum."""
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if _missing(exc):
                return False
            raise
        digest = hashlib.sha256()
        for chunk in iter(lambda: response["Body"].read(_CHUNK), b""):
            digest.update(chunk)
        if digest.hexdigest() != expected_digest:
            raise RuntimeError(f"retained release object {key} failed SHA-256 verification")
        return True

    def _read(self, key: str, *, expected_digest: str, output: Path | None = None) -> bytes | Path | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if _missing(exc):
                return None
            raise

        stream = response["Body"]
        digest = hashlib.sha256()
        if output is None:
            chunks = []
            for chunk in iter(lambda: stream.read(_CHUNK), b""):
                digest.update(chunk)
                chunks.append(chunk)
            result: bytes | Path = b"".join(chunks)
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            # Never leave a corrupt or truncated archive at the requested path.
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".release-", delete=False) as temporary:
                    temporary_path = Path(temporary.name)
                    for chunk in iter(lambda: stream.read(_CHUNK), b""):
                        digest.update(chunk)
                        temporary.write(chunk)
            except BaseException:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
                raise
            assert temporary_path is not None
            result = temporary_path

        if digest.hexdigest() != expected_digest:
            if output is not None:
                result.unlink(missing_ok=True)
            raise RuntimeError(f"retained release object {key} failed SHA-256 verification")
        if output is not None:
            result.replace(output)
            return output
        return result

    def _put_immutable(self, key: str, source: bytes | Path, digest: str, content_type: str) -> None:
        if self._exists_verified(key, digest):
            return

        try:
            if isinstance(source, bytes):
                self.client.put_object(
                    Bucket=self.bucket, Key=key, Body=source,
                    ContentType=content_type, IfNoneMatch="*",
                )
            else:
                with source.open("rb") as stream:
                    self.client.put_object(
                        Bucket=self.bucket, Key=key, Body=stream,
                        ContentType=content_type, IfNoneMatch="*",
                    )
        except ClientError as exc:
            # A concurrent identical writer may win the conditional upload.
            # A lost response after a successful write is also retryable.
            if not self._exists_verified(key, digest):
                raise
        # Do not trust a successful PutObject response or an S3 ETag as a
        # checksum (multipart ETags are not SHA-256 digests).
        if not self._exists_verified(key, digest):
            raise RuntimeError(f"retained release object {key} disappeared after upload")

    def put_release(self, release_id: str, manifest_bytes: bytes, payload_bytes: bytes | Path) -> None:
        """Store the ZIP first and publish its manifest only after read-back.

        A retry after either upload boundary reuses matching objects. A
        missing manifest means the interrupted release is not discoverable as
        complete, while its payload remains available for the retry.
        """
        if not isinstance(manifest_bytes, bytes) or not isinstance(payload_bytes, (bytes, Path)):
            raise TypeError("manifest must be bytes and payload must be bytes or Path")
        if not _DIGEST.fullmatch(release_id) or _sha256(manifest_bytes) != release_id:
            raise ValueError("release_id must equal the manifest SHA-256")
        source_revision, payload_digest = _manifest_identity(manifest_bytes)
        if _sha256(payload_bytes) != payload_digest:
            raise ValueError("payload bytes differ from the release manifest")
        self._put_immutable(self._payload_key(payload_digest), payload_bytes, payload_digest, "application/zip")
        self._put_immutable(self._manifest_key(release_id), manifest_bytes, release_id, "application/json")
        # This is the only mutable-looking key, but conditional PutObject and
        # byte comparison make the first completed release for a revision
        # permanent. It is written last, so an interrupted upload can retry.
        index = (json.dumps({
            "schema_version": 1,
            "source_revision": source_revision,
            "release_id": release_id,
            "payload_digest": payload_digest,
        }, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        self._put_immutable(self._revision_key(source_revision), index, _sha256(index), "application/json")

    def get_release(self, release_id: str, output_path: Path | None = None,
                    *, require_index: bool = True) -> tuple[bytes, bytes | Path]:
        """Retrieve and check both objects; index bypass is for offline recovery only.

        A caller bypassing the index must independently verify the package
        against its trusted Git source before repairing the index.
        """
        if not _DIGEST.fullmatch(release_id):
            raise ValueError("release_id must be a lowercase SHA-256 digest")
        manifest = self._read(self._manifest_key(release_id), expected_digest=release_id)
        if manifest is None:
            raise FileNotFoundError(f"retained release manifest {release_id} is missing")
        assert isinstance(manifest, bytes)
        source_revision, payload_digest = _manifest_identity(manifest)
        if require_index and self.release_id_for_revision(source_revision) != release_id:
            raise RuntimeError("release manifest is not the indexed release for its source revision")
        payload = self._read(self._payload_key(payload_digest), expected_digest=payload_digest, output=output_path)
        if payload is None:
            raise FileNotFoundError(f"retained release payload {payload_digest} is missing")
        return manifest, payload

    def release_id_for_revision(self, source_revision: str) -> str:
        """Resolve a completed release; an interrupted upload has no index."""
        if not _REVISION.fullmatch(source_revision):
            raise ValueError("source_revision must be a full lowercase Git SHA")
        key = self._revision_key(source_revision)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if _missing(exc):
                raise FileNotFoundError(f"retained release for {source_revision} is missing") from exc
            raise
        index_bytes = response["Body"].read()
        try:
            index = json.loads(index_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"retained release index {key} is corrupt") from exc
        release_id = index.get("release_id") if isinstance(index, dict) else None
        if (
            not isinstance(release_id, str) or not _DIGEST.fullmatch(release_id)
            or index.get("schema_version") != 1
            or index.get("source_revision") != source_revision
            or not isinstance(index.get("payload_digest"), str)
            or not _DIGEST.fullmatch(index["payload_digest"])
        ):
            raise RuntimeError(f"retained release index {key} is invalid")
        canonical = (json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        if index_bytes != canonical:
            raise RuntimeError(f"retained release index {key} is not canonical")
        manifest = self._read(self._manifest_key(release_id), expected_digest=release_id)
        if manifest is None:
            raise RuntimeError(f"retained release index {key} points to a missing manifest")
        assert isinstance(manifest, bytes)
        if _manifest_identity(manifest) != (source_revision, index["payload_digest"]):
            raise RuntimeError(f"retained release index {key} disagrees with its manifest")
        return release_id
