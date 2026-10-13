"""Prepare, retain, fetch, and inspect exact release payloads.

All commands operate on Git content or the private release store; none contact
YouTube, Drive, or linked RSS. Deployment remains a separate, target job.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import ROOT
from .release_artifact import create_release, digest, verify_release
from .release_store import ReleaseStore


def _output(release_id: str, manifest: dict) -> None:
    print(f"Retained release {release_id} from {manifest['source_revision']} with payload {manifest['payload_digest']}")
    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(f"release_id={release_id}\npayload_digest={manifest['payload_digest']}\n")


def prepare(root: Path, revision: str, output: Path, store: ReleaseStore) -> str:
    """Reuse an existing retained release or package the committed bytes once."""
    output.mkdir(parents=True, exist_ok=True)
    try:
        release_id = store.release_id_for_revision(revision)
    except FileNotFoundError:
        release_id = None
    if release_id:
        manifest_bytes, payload = store.get_release(release_id, output / "payload.zip")
        assert isinstance(payload, Path)
        (output / "manifest.json").write_bytes(manifest_bytes)
        with tempfile.TemporaryDirectory(prefix="release-reuse-") as directory:
            verify_release(root, revision, manifest_bytes, payload, Path(directory))
        manifest = json.loads(manifest_bytes)
        print(f"Reused exact retained payload {manifest['payload_digest']}; no rebuild")
    else:
        release_id, manifest = create_release(root, revision, output)
        store.put_release(release_id, (output / "manifest.json").read_bytes(), output / "payload.zip")
        print(f"Packaged and retained exact payload {manifest['payload_digest']}")
    _output(release_id, manifest)
    return release_id


def fetch(root: Path, revision: str, release_id: str, destination: Path,
          bundle_dir: Path, store: ReleaseStore) -> str:
    """Verify a retained package against Git before exposing deployment files."""
    bundle_dir.mkdir(parents=True, exist_ok=True)
    manifest_bytes, payload = store.get_release(release_id, bundle_dir / "payload.zip")
    assert isinstance(payload, Path)
    manifest = json.loads(manifest_bytes)
    if manifest.get("source_revision") != revision:
        raise ValueError("Retained release belongs to a different source revision")
    verified_id = verify_release(root, revision, manifest_bytes, payload, destination)
    if verified_id != release_id:
        raise ValueError("Retained release ID mismatch")
    (bundle_dir / "manifest.json").write_bytes(manifest_bytes)
    _output(release_id, manifest)
    return release_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--revision", required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    fetch_parser = sub.add_parser("fetch")
    fetch_parser.add_argument("--revision", required=True)
    fetch_parser.add_argument("--release-id", required=True)
    fetch_parser.add_argument("--destination", type=Path, required=True)
    fetch_parser.add_argument("--bundle-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        store = ReleaseStore.from_environment()
        if args.command == "prepare":
            prepare(ROOT, args.revision, args.output, store)
        else:
            fetch(ROOT, args.revision, args.release_id, args.destination, args.bundle_dir, store)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Release preparation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
