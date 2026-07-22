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
    return {
        "schema_version": SCHEMA_VERSION,
        "target": target,
        "revision": revision,
        "deployed_at": timestamp,
        "run_id": int(run_id),
        "run_url": run_url.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-url", default="")
    parser.add_argument("--deployed-at")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(
        target=args.target,
        revision=args.revision,
        run_id=args.run_id,
        run_url=args.run_url,
        deployed_at=args.deployed_at,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
