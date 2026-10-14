"""Synthetic reference and safety cases for the advisory cleanup preview."""

import hashlib
import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from podcast_feeds.release_cleanup_preview import collect, collect_cloudflare_rest, preview


NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)
IDENTITIES = {}


def stamp(days):
    return (NOW - timedelta(days=days)).isoformat()


def obj(key, data, days):
    row = {"key": key, "size": len(data), "last_modified": stamp(days)}
    if key.endswith(".json"):
        row["body_hex"] = data.hex()
    return row


def release(revision, payload_digest, days, payload_size=1):
    manifest = json.dumps({"schema_version": 1, "repository": "shaqo88/youtube-podcast-feeds",
                           "source_revision": revision, "payload_digest": payload_digest,
                           "payload_size": payload_size}, sort_keys=True).encode()
    rid = hashlib.sha256(manifest).hexdigest()
    IDENTITIES[rid] = {"release_id": rid, "revision": revision, "payload_digest": payload_digest}
    index = (json.dumps({"schema_version": 1, "source_revision": revision,
                         "release_id": rid, "payload_digest": payload_digest},
                        sort_keys=True, separators=(",", ":")) + "\n").encode()
    rows = [obj(f"releases/v1/manifests/{rid}.json", manifest, days + 0.1),
            obj(f"releases/v1/by-revision/{revision}.json", index, days)]
    return rid, rows


def evidence(current, previous, pending=None):
    return {"complete": True, "observed_at": stamp(0),
            "current": {"github_pages": IDENTITIES[current], "cloudflare_pages": IDENTITIES[current]},
            "last_known_good": IDENTITIES[previous], "in_flight": pending or []}


def test_shared_payload_and_old_complete_release():
    digest = "a" * 64
    current, a = release("1" * 40, digest, 1, 7)
    old, b = release("2" * 40, digest, 10, 7)
    rows = a + b + [obj(f"releases/v1/payloads/{digest}.zip", b"payload", 10.2)]
    result = preview({"observed_at": stamp(0), "objects": rows}, evidence(current, current))
    eligible = {row["key"] for row in result["objects"] if row["status"] == "potentially_eligible"}
    assert result["evidence_complete"]
    assert len(eligible) == 2
    assert f"releases/v1/payloads/{digest}.zip" not in eligible
    assert result["reclaimable_bytes"] == sum(row["size"] for row in b)


def test_old_complete_unshared_release_counts_whole_identity_once():
    current_digest, old_digest = "a" * 64, "b" * 64
    current, a = release("1" * 40, current_digest, 1, 3)
    old, b = release("2" * 40, old_digest, 10, 3)
    rows = a + b + [obj(f"releases/v1/payloads/{current_digest}.zip", b"new", 1.2),
                    obj(f"releases/v1/payloads/{old_digest}.zip", b"old", 10.2)]
    result = preview({"observed_at": stamp(0), "objects": rows}, evidence(current, current))
    assert result["reclaimable_objects"] == 3
    assert result["reclaimable_bytes"] == sum(row["size"] for row in b) + 3
    assert next(row for row in result["releases"] if row["release_id"] == old)["age_days"] == 10


def test_mismatched_targets_and_pending_release_are_protected():
    ids, rows = [], []
    for n in range(3):
        digest = f"{n + 1:064x}"
        rid, triple = release(f"{n + 1:040x}", digest, 10)
        ids.append(rid)
        rows += triple + [obj(f"releases/v1/payloads/{digest}.zip", b"z", 10.2)]
    ev = evidence(ids[0], ids[0], [{"release_id": ids[2]}])
    ev["current"]["cloudflare_pages"] = IDENTITIES[ids[1]]
    result = preview({"observed_at": stamp(0), "objects": rows}, ev)
    assert result["reclaimable_bytes"] == 0
    assert all(row["protection"] for row in result["releases"])


def test_missing_index_blocks_every_candidate():
    digest = "a" * 64
    rid, rows = release("1" * 40, digest, 10)
    rows = rows[:1] + [obj(f"releases/v1/payloads/{digest}.zip", b"x", 10.2)]
    result = preview({"observed_at": stamp(0), "objects": rows}, evidence(rid, rid))
    assert not result["evidence_complete"]
    assert result["reclaimable_bytes"] == 0


def test_truncated_payload_size_blocks_release():
    current, a = release("1" * 40, "a" * 64, 1)
    old, b = release("2" * 40, "b" * 64, 10, 4)
    rows = a + b + [obj(f"releases/v1/payloads/{'a' * 64}.zip", b"x", 1.2),
                    obj(f"releases/v1/payloads/{'b' * 64}.zip", b"old", 10.2)]
    result = preview({"observed_at": stamp(0), "objects": rows}, evidence(current, current))
    assert not result["evidence_complete"]
    assert not next(r for r in result["releases"] if r["release_id"] == old)["complete"]
    assert result["reclaimable_bytes"] == 0


def test_interrupted_upload_and_unknown_object_are_blocked():
    digest = "a" * 64
    rid, rows = release("1" * 40, digest, 1)
    rows += [obj(f"releases/v1/payloads/{digest}.zip", b"x", 1.2),
             obj(f"releases/v1/payloads/{'b' * 64}.zip", b"orphan", 15),
             obj("permission-probe", b"probe", 20)]
    result = preview({"observed_at": stamp(0), "objects": rows}, evidence(rid, rid))
    assert result["reclaimable_bytes"] == 0
    assert any("unreferenced payload" in reason for row in result["objects"] for reason in row["reasons"])
    assert any("unknown object" in reason for row in result["objects"] for reason in row["reasons"])


def test_changing_reference_or_missing_evidence_blocks_all():
    digest = "a" * 64
    rid, rows = release("1" * 40, digest, 10)
    rows += [obj(f"releases/v1/payloads/{digest}.zip", b"x", 10.2)]
    ev = evidence(rid, rid)
    ev["current"]["cloudflare_pages"] = {"release_id": "f" * 64}
    result = preview({"observed_at": stamp(0), "objects": rows}, ev)
    assert not result["evidence_complete"]
    assert result["reclaimable_bytes"] == 0
    ev = evidence(rid, rid)
    ev["complete"] = False
    assert preview({"observed_at": stamp(0), "objects": rows}, ev)["reclaimable_bytes"] == 0


def test_queued_attempt_without_release_dependency_blocks_candidates():
    current, a = release("1" * 40, "a" * 64, 1)
    _, b = release("2" * 40, "b" * 64, 10)
    rows = a + b + [obj(f"releases/v1/payloads/{'a' * 64}.zip", b"x", 1.2),
                    obj(f"releases/v1/payloads/{'b' * 64}.zip", b"y", 10.2)]
    ev = evidence(current, current, [{"workflow_run_id": 1, "release_id": None}])
    result = preview({"observed_at": stamp(0), "objects": rows}, ev)
    assert not result["evidence_complete"] and result["reclaimable_bytes"] == 0
    assert all(row["status"] == "protected_or_blocked" for row in result["objects"])


def test_receipt_mismatch_or_unknown_release_key_blocks_old_candidate():
    current_digest, old_digest = "a" * 64, "b" * 64
    current, a = release("1" * 40, current_digest, 1, 3)
    _, b = release("2" * 40, old_digest, 10, 3)
    rows = a + b + [obj(f"releases/v1/payloads/{current_digest}.zip", b"new", 1.2),
                    obj(f"releases/v1/payloads/{old_digest}.zip", b"old", 10.2)]
    ev = evidence(current, current)
    ev["current"]["github_pages"] = {**ev["current"]["github_pages"], "payload_digest": "c" * 64}
    result = preview({"observed_at": stamp(0), "objects": rows}, ev)
    assert not result["evidence_complete"] and result["reclaimable_bytes"] == 0
    ev = evidence(current, current)
    rows.append(obj("releases/v1/new-format/marker", b"?", 1))
    result = preview({"observed_at": stamp(0), "objects": rows}, ev)
    assert not result["evidence_complete"] and result["reclaimable_bytes"] == 0


def test_missing_payload_timestamp_blocks_with_per_object_reason():
    rid, rows = release("1" * 40, "a" * 64, 10)
    payload = obj(f"releases/v1/payloads/{'a' * 64}.zip", b"x", 10.2)
    del payload["last_modified"]
    result = preview({"observed_at": stamp(0), "objects": rows + [payload]}, evidence(rid, rid))
    assert not result["evidence_complete"] and result["reclaimable_bytes"] == 0
    assert any("missing or invalid LastModified" in reason
               for row in result["objects"] for reason in row["reasons"])


def test_collector_lists_bucket_and_reads_only_release_json():
    rid, rows = release("1" * 40, "a" * 64, 1, 3)
    rows += [obj(f"releases/v1/payloads/{'a' * 64}.zip", b"zip", 1.2),
             obj("permission-probe", b"probe", 3)]
    calls = []

    class Client:
        def get_paginator(self, operation):
            assert operation == "list_objects_v2"
            calls.append(operation)
            return self

        def paginate(self, **kwargs):
            assert kwargs == {"Bucket": "test"}
            return [{"Contents": [{"Key": r["key"], "Size": r["size"],
                                   "LastModified": instant_for_test(r["last_modified"])} for r in page]}
                    for page in (rows[:1], rows[1:])]

        def get_object(self, **kwargs):
            calls.append(kwargs["Key"])
            row = next(r for r in rows if r["key"] == kwargs["Key"])
            return {"Body": io.BytesIO(bytes.fromhex(row["body_hex"]))}

    result = collect(SimpleNamespace(bucket="test", client=Client()))
    assert result["objects"] and len(result["objects"]) == 4
    assert sum(row["size"] for row in result["objects"]) == sum(row["size"] for row in rows)
    assert len(calls) == 3
    assert all(key.endswith(".json") for key in calls[1:])


def test_cloudflare_rest_collector_paginates_and_gets_only_json():
    rid, rows = release("1" * 40, "a" * 64, 1, 3)
    rows += [obj(f"releases/v1/payloads/{'a' * 64}.zip", b"zip", 1.2)]
    calls = []

    def open_url(request, timeout):
        calls.append((request.method, request.full_url))
        assert request.method == "GET" and request.get_header("Authorization") == "Bearer fixture-token"
        if request.full_url.endswith("/objects"):
            body = {"success": True, "result": [{"key": rows[0]["key"], "size": rows[0]["size"],
                                                   "last_modified": rows[0]["last_modified"]}],
                    "result_info": {"is_truncated": True, "cursor": "next"}}
            return io.BytesIO(json.dumps(body).encode())
        if request.full_url.endswith("?cursor=next"):
            body = {"success": True, "result": [{"key": r["key"], "size": r["size"],
                                                   "last_modified": r["last_modified"]} for r in rows[1:]],
                    "result_info": {"is_truncated": False}}
            return io.BytesIO(json.dumps(body).encode())
        row = next(r for r in rows if request.full_url.endswith(r["key"]))
        return io.BytesIO(bytes.fromhex(row["body_hex"]))

    result = collect_cloudflare_rest("test", "1" * 32, "fixture-token", open_url=open_url)
    assert len(result["objects"]) == 3
    assert sum(row["size"] for row in result["objects"]) == sum(row["size"] for row in rows)
    assert len(calls) == 4  # Two list pages and two JSON GETs; no ZIP fetch.


def load_tests(loader, tests, pattern):
    tests.addTests(unittest.FunctionTestCase(fn, description=name)
                   for name, fn in sorted(globals().items())
                   if name.startswith("test_") and callable(fn))
    return tests


def instant_for_test(value):
    return datetime.fromisoformat(value)
