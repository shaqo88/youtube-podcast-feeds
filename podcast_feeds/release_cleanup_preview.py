"""Read-only inventory and conservative preview for retained release objects.

The preview is advisory. An S3 listing is not an atomic snapshot, and this
module deliberately has no delete operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .release_store import ReleaseStore


PREFIX = "releases/v1/"
KEY = re.compile(r"^releases/v1/(manifests/([0-9a-f]{64})\.json|payloads/([0-9a-f]{64})\.zip|by-revision/([0-9a-f]{40})\.json)$")


def instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def collect(store: ReleaseStore) -> dict[str, Any]:
    """List every bucket object and read only release JSON, never ZIP bytes."""
    observed_at = datetime.now(timezone.utc).isoformat()
    objects = []
    paginator = store.client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=store.bucket):
        for item in page.get("Contents", []):
            key = item["Key"]
            row: dict[str, Any] = {
                "key": key, "size": item["Size"],
                "last_modified": item["LastModified"].astimezone(timezone.utc).isoformat(),
            }
            match = KEY.fullmatch(key)
            if match and (match.group(2) or match.group(4)):
                response = store.client.get_object(Bucket=store.bucket, Key=key)
                body = response["Body"].read()
                row["body_hex"] = body.hex()
            objects.append(row)
    return {"observed_at": observed_at, "objects": objects,
            "warning": "Listing is non-atomic; revalidate all protections before deletion."}


def preview(snapshot: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    now = instant(snapshot["observed_at"])
    cutoff = now - timedelta(days=7)
    objects = snapshot["objects"]
    by_key = {row["key"]: row for row in objects}
    if len(by_key) != len(objects) or any(not isinstance(row["size"], int) or row["size"] < 0 for row in objects):
        raise ValueError("duplicate keys or invalid object size")
    reasons: dict[str, set[str]] = defaultdict(set)
    releases: dict[str, dict[str, Any]] = {}
    indexes: dict[str, dict[str, Any]] = {}
    errors = []

    def parse(row: dict[str, Any]) -> dict[str, Any]:
        raw = bytes.fromhex(row["body_hex"])
        if len(raw) != row["size"]:
            raise ValueError("JSON object length differs from listing")
        match = KEY.fullmatch(row["key"])
        if match and match.group(2) and hashlib.sha256(raw).hexdigest() != match.group(2):
            raise ValueError("manifest SHA-256 differs from release ID")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("JSON object is not an object")
        if match and match.group(4) and raw != (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode():
            raise ValueError("index is not canonical")
        return value

    for row in objects:
        key = row["key"]
        match = KEY.fullmatch(key)
        if not match:
            reasons[key].add("unknown object or prefix")
            if key.startswith(PREFIX):
                errors.append(f"unknown release-prefix object: {key}")
            continue
        try:
            instant(row["last_modified"])
            if match.group(2):
                manifest = parse(row)
                release_id = match.group(2)
                revision = manifest.get("source_revision")
                digest = manifest.get("payload_digest")
                if (not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision)
                        or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
                    raise ValueError("invalid manifest references")
                releases[release_id] = {"revision": revision, "payload_digest": digest, "manifest_key": key}
            elif match.group(4):
                index = parse(row)
                revision = match.group(4)
                if (index.get("schema_version") != 1 or index.get("source_revision") != revision
                        or not isinstance(index.get("release_id"), str)
                        or not re.fullmatch(r"[0-9a-f]{64}", index["release_id"])
                        or not isinstance(index.get("payload_digest"), str)
                        or not re.fullmatch(r"[0-9a-f]{64}", index["payload_digest"])):
                    raise ValueError("invalid index references")
                indexes[revision] = index
        except (ValueError, KeyError, TypeError) as exc:
            reasons[key].add(f"invalid or unreadable release metadata: {exc}")
            errors.append(key)

    protected_ids: dict[str, set[str]] = defaultdict(set)
    required = ("current", "last_known_good", "in_flight")
    complete = evidence.get("complete") is True and all(k in evidence for k in required)
    try:
        evidence_at = instant(evidence["observed_at"])
        if abs((now - evidence_at).total_seconds()) > 600:
            complete = False
            errors.append("receipt and attempt evidence is more than ten minutes from inventory")
    except (KeyError, TypeError, ValueError):
        complete = False
        errors.append("receipt and attempt evidence needs a timezone-aware observed_at")
    current = evidence.get("current", {})
    if not isinstance(current, dict) or set(current) != {"github_pages", "cloudflare_pages"}:
        complete = False
        errors.append("both target receipts are required")
        current = {}
    for target, identity in current.items():
        if isinstance(identity, dict) and isinstance(identity.get("release_id"), str):
            protected_ids[identity["release_id"]].add(f"current on {target}")
        else:
            complete = False
    for name, value in (("preceding verified last-known-good", evidence.get("last_known_good")),):
        if isinstance(value, dict) and isinstance(value.get("release_id"), str):
            protected_ids[value["release_id"]].add(name)
        else:
            complete = False
    if not isinstance(evidence.get("in_flight"), list):
        complete = False
    else:
        for attempt in evidence["in_flight"]:
            if not isinstance(attempt, dict) or not isinstance(attempt.get("release_id"), str):
                complete = False
                continue
            protected_ids[attempt["release_id"]].add("active, queued or recoverable attempt")
    if errors:
        complete = False

    release_rows = []
    for release_id, release in sorted(releases.items()):
        revision = release["revision"]
        digest = release["payload_digest"]
        keys = [release["manifest_key"], f"{PREFIX}payloads/{digest}.zip", f"{PREFIX}by-revision/{revision}.json"]
        index = indexes.get(revision)
        valid = all(key in by_key for key in keys) and index is not None and index.get("release_id") == release_id and index.get("payload_digest") == digest
        if not valid:
            complete = False
            errors.append(f"incomplete release {release_id}")
        # The index is written after payload and manifest; its LastModified is
        # the observable completion timestamp, not an episode date.
        retained_at = instant(by_key[keys[2]]["last_modified"]) if keys[2] in by_key else None
        if retained_at and any(instant(by_key[key]["last_modified"]) > retained_at for key in keys if key in by_key):
            valid = False
            complete = False
            errors.append(f"index predates release object {release_id}")
        why = set(protected_ids.get(release_id, set()))
        if retained_at and retained_at >= cutoff:
            why.add("within seven-day window")
        if not valid:
            why.add("missing or inconsistent release reference")
        for key in keys:
            if key in by_key:
                reasons[key].update(why)
        release_rows.append({"release_id": release_id, "revision": revision, "payload_digest": digest,
                             "retained_at": retained_at.isoformat() if retained_at else None,
                             "age_days": round((now - retained_at).total_seconds() / 86400, 3) if retained_at else None,
                             "complete": valid, "protection": sorted(why)})

    for release_id in protected_ids:
        if release_id not in releases:
            complete = False
            errors.append(f"protected release absent: {release_id}")
    for label, identity in list(current.items()) + [("last_known_good", evidence.get("last_known_good"))]:
        if not isinstance(identity, dict):
            continue
        release = releases.get(identity.get("release_id"))
        if release and (identity.get("revision") != release["revision"]
                        or identity.get("payload_digest") != release["payload_digest"]):
            complete = False
            errors.append(f"{label} receipt disagrees with retained manifest")
    for revision, index in indexes.items():
        release = releases.get(index["release_id"])
        if release is None or release["revision"] != revision:
            complete = False
            errors.append(f"index without matching manifest: {revision}")
    if not complete:
        for row in objects:
            reasons[row["key"]].add("blocked: incomplete or ambiguous evidence")

    # An unreferenced payload may be an interrupted upload, never a candidate.
    for row in objects:
        key = row["key"]
        match = KEY.fullmatch(key)
        if match and match.group(3) and key not in reasons:
            reasons[key].add("unreferenced payload or interrupted upload")
        if match and match.group(4) and key not in reasons:
            reasons[key].add("unreferenced index")
    eligible_keys = set()
    if complete:
        for release in release_rows:
            if release["complete"] and not release["protection"]:
                rid = release["release_id"]
                detail = releases[rid]
                eligible_keys.update((detail["manifest_key"], f"{PREFIX}by-revision/{detail['revision']}.json",
                                      f"{PREFIX}payloads/{detail['payload_digest']}.zip"))
        # Shared payloads remain if any non-eligible release references them.
        for release in release_rows:
            if release["release_id"] not in {r["release_id"] for r in release_rows if r["complete"] and not r["protection"]}:
                eligible_keys.discard(f"{PREFIX}payloads/{releases[release['release_id']]['payload_digest']}.zip")
        for key in list(eligible_keys):
            if reasons[key]:
                eligible_keys.discard(key)
    result_objects = [{"key": row["key"], "size": row["size"], "last_modified": row["last_modified"],
                       "status": "potentially_eligible" if row["key"] in eligible_keys else "protected_or_blocked",
                       "reasons": ["complete release older than seven days; review only"] if row["key"] in eligible_keys else sorted(reasons[row["key"]])}
                      for row in sorted(objects, key=lambda x: x["key"])]
    return {"observed_at": now.isoformat(), "retention_cutoff": cutoff.isoformat(),
            "current": current, "last_known_good": evidence.get("last_known_good"),
            "in_flight": evidence.get("in_flight"),
            "total_objects": len(objects), "total_bytes": sum(r["size"] for r in objects),
            "reclaimable_objects": len(eligible_keys), "reclaimable_bytes": sum(by_key[k]["size"] for k in eligible_keys),
            "evidence_complete": complete, "errors": sorted(set(errors)), "releases": release_rows,
            "objects": result_objects,
            "warning": "Non-atomic listing: revalidate live receipts, attempts, references and object versions before any later owner-approved deletion."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, help="Previously captured JSON inventory; omit to collect live read-only R2 inventory")
    parser.add_argument("--snapshot-output", type=Path, help="Write captured live inventory locally for private audit")
    parser.add_argument("--evidence", type=Path, required=True, help="Private reviewed target and attempt evidence JSON")
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else collect(ReleaseStore.from_environment())
    if args.snapshot_output:
        args.snapshot_output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    print(json.dumps(preview(snapshot, evidence), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
