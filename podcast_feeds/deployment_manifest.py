from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def build_manifest(
    *,
    target: str,
    revision: str,
    run_id: str,
    deployed_at: str | None = None,
    run_url: str = "",
    release_id: str | None = None,
    payload_digest: str | None = None,
) -> dict[str, object]:
    target = target.strip()
    revision = revision.strip().lower()
    run_id = str(run_id).strip()
    if not target:
        raise ValueError("target is required")
    if not REVISION_PATTERN.fullmatch(revision):
        raise ValueError("revision must be a full lowercase Git commit SHA")
    if not run_id.isdigit() or int(run_id) <= 0:
        raise ValueError("run_id must be a positive integer")
    if deployed_at:
        parsed = datetime.fromisoformat(deployed_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("deployed_at must include a timezone")
        timestamp = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    else:
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    result = {
        "schema_version": SCHEMA_VERSION,
        "target": target,
        "revision": revision,
        "deployed_at": timestamp,
        "run_id": int(run_id),
        "run_url": run_url.strip(),
    }
    if release_id is not None or payload_digest is not None:
        if not release_id or not re.fullmatch(r"[0-9a-f]{64}", release_id):
            raise ValueError("release_id must be a full lowercase SHA-256 digest")
        if not payload_digest or not re.fullmatch(r"[0-9a-f]{64}", payload_digest):
            raise ValueError("payload_digest must be a full lowercase SHA-256 digest")
        result["release_id"] = release_id
        result["payload_digest"] = payload_digest
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-url", default="")
    parser.add_argument("--deployed-at")
    parser.add_argument("--release-id")
    parser.add_argument("--payload-digest")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(
        target=args.target,
        revision=args.revision,
        run_id=args.run_id,
        run_url=args.run_url,
        deployed_at=args.deployed_at,
        release_id=args.release_id,
        payload_digest=args.payload_digest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
