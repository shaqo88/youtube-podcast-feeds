from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import boto3
from botocore.exceptions import ClientError

from .config import ROOT, load_enabled_shows, load_show
from .episodes import load_episodes, save_episodes
from .episode_notifications import new_episode_notification

SCHEMA_VERSION = 1
STATE_BUCKET_ENV = "R2_STATE_BUCKET"
RETRY_HOURS = (1, 2, 4, 6)
PENDING_RECONCILE_INTERVAL = timedelta(hours=24)
PENDING_RECONCILE_KEY = "v1/index/pending-reconciled.json"
VALID_WORK_STATES = {
    "pending",
    "waiting_for_recording",
    "retry_wait",
    "processing",
    "ready_to_publish",
    "published",
    "unavailable",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat().replace("+00:00", "Z")


def stable_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def fingerprint(value: Any) -> str:
    return hashlib.sha256(stable_json(value)).hexdigest()


def source_fingerprint(show_slug: str) -> str:
    path = ROOT / "shows" / show_slug / "config.yml"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def retry_at(identity: str, attempt: int, now: datetime | None = None) -> str:
    base_hours = RETRY_HOURS[min(max(attempt, 1) - 1, len(RETRY_HOURS) - 1)]
    digest = int(hashlib.sha256(identity.encode()).hexdigest()[:8], 16)
    jitter = ((digest % 2001) - 1000) / 10000
    return timestamp((now or utc_now()) + timedelta(hours=base_hours * (1 + jitter)))


@dataclass
class StateStore:
    bucket: str
    client: Any
    operations: dict[str, int] = field(default_factory=dict)

    def _count(self, name: str) -> None:
        self.operations[name] = self.operations.get(name, 0) + 1

    @classmethod
    def from_environment(cls) -> "StateStore":
        bucket = os.environ.get(STATE_BUCKET_ENV, "").strip()
        if not bucket:
            raise RuntimeError(f"{STATE_BUCKET_ENV} is required; refusing to run without durable state")
        account_id = os.environ.get("R2_STATE_ACCOUNT_ID") or os.environ["R2_ACCOUNT_ID"]
        access_key = os.environ.get("R2_STATE_ACCESS_KEY") or os.environ["R2_ACCESS_KEY"]
        secret_key = os.environ.get("R2_STATE_SECRET_KEY") or os.environ["R2_SECRET_KEY"]
        client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
        )
        return cls(bucket, client)

    def get_json(self, key: str) -> dict[str, Any] | None:
        self._count("get")
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                return None
            raise
        try:
            value = json.loads(response["Body"].read())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"State object {key} is corrupt; refusing to overwrite it") from exc
        if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
            raise RuntimeError(f"State object {key} has an unsupported schema")
        return value

    def put_json(self, key: str, value: dict[str, Any]) -> None:
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("State documents require the current schema_version")
        self._count("put")
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=stable_json(value),
            ContentType="application/json",
        )

    def delete_json(self, key: str) -> None:
        self._count("delete")
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def list_json(self, prefix: str) -> Iterable[tuple[str, dict[str, Any]]]:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            self._count("list_page")
            for item in page.get("Contents", []):
                key = item["Key"]
                value = self.get_json(key)
                if value is not None:
                    yield key, value


def pending_key(candidate_id: str) -> str:
    return f"v1/pending/{candidate_id}.json"


def receipt_complete(value: dict[str, Any] | None) -> bool:
    if not value:
        return False
    deployments = value.get("deployments") or {}
    notification = (value.get("notification") or {}).get("state")
    release_revision = value.get("release_revision")
    release_id = value.get("release_id")
    payload_digest = value.get("payload_digest")
    if bool(release_id) != bool(payload_digest):
        return False
    return (
        all(
            deployments.get(target, {}).get("status") == "verified"
            and (not release_revision or deployments.get(target, {}).get("revision") == release_revision)
            and (not release_id or deployments.get(target, {}).get("release_id") == release_id)
            and (not release_id or deployments.get(target, {}).get("payload_digest") == payload_digest)
            for target in ("cloudflare-pages", "github-pages")
        )
        and (not release_id or (
            isinstance(release_id, str) and bool(re.fullmatch(r"[0-9a-f]{64}", release_id))
            and isinstance(payload_digest, str) and bool(re.fullmatch(r"[0-9a-f]{64}", payload_digest))
        ))
        and notification in {"sent", "not_required"}
    )


def mark_pending(store: StateStore, candidate_id: str) -> None:
    store.put_json(pending_key(candidate_id), {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
    })


def mark_work_published(store: StateStore, item: dict[str, Any]) -> None:
    work_key = f"v1/work/{item['lane']}/{item['show_slug']}/{item['episode_id']}.json"
    work = store.get_json(work_key)
    if work and work.get("candidate_id") in {None, item["candidate_id"]}:
        work.update({"state": "published", "updated_at": timestamp()})
        store.put_json(work_key, work)


def reconcile_pending(store: StateStore) -> dict[str, int]:
    """Repair the non-transactional candidate/marker/receipt boundary."""
    found = 0
    restored = 0
    removed = 0
    for _, candidate in store.list_json("v1/candidates/"):
        found += 1
        candidate_id = str(candidate["candidate_id"])
        marker = store.get_json(pending_key(candidate_id))
        candidate_receipt = store.get_json(f"v1/receipts/{candidate_id}.json")
        if receipt_complete(candidate_receipt):
            if marker:
                store.delete_json(pending_key(candidate_id))
                removed += 1
        elif not candidate_receipt and store.get_json(f"v1/quarantine/{candidate_id}.json"):
            if marker:
                store.delete_json(pending_key(candidate_id))
                removed += 1
        elif not marker:
            mark_pending(store, candidate_id)
            restored += 1
    store.put_json(PENDING_RECONCILE_KEY, {
        "schema_version": SCHEMA_VERSION,
        "reconciled_at": timestamp(),
    })
    result = {"candidates_scanned": found, "markers_restored": restored, "markers_removed": removed}
    print(f"Reconciled pending publication index: {result}.")
    return result


def snapshot(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for show in load_enabled_shows():
        target = destination / show.slug / "episodes.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        if show.episodes_path.exists():
            shutil.copyfile(show.episodes_path, target)
        else:
            target.write_text("{}\n", encoding="utf-8")


def _episode_lane(show: Any, episode: dict[str, Any]) -> str:
    source_type = str(episode.get("source_type") or "").lower()
    if source_type == "drive":
        return "drive"
    if source_type == "existing_feed":
        return "existing_feed"
    source_url = str(episode.get("source_url") or "").lower()
    if "drive.google.com" in source_url:
        return "drive"
    if "youtube.com" in source_url or "youtu.be" in source_url:
        return "youtube"
    source_types = {source.type for source in show.sources}
    if len(source_types) == 1 and "drive" in source_types:
        return "drive"
    if len(source_types) == 1 and "existing_feed" in source_types:
        return "existing_feed"
    return "youtube"


def bootstrap(store: StateStore | None, show_slug: str, output: Path, dry_run: bool = False) -> dict[str, Any]:
    """Initialize durable state from public metadata without changing publication."""
    show = load_show(show_slug)
    episodes = load_episodes(show.episodes_path)
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "show_slug": show.slug,
        "dry_run": dry_run,
        "episode_count": len(episodes),
        "planned": {"published": 0, "unavailable": 0, "pending": 0},
        "existing_state": 0,
        "operational_fields_to_remove": [],
        "public_changes": 0,
    }
    now = timestamp()
    operational_fields = ("last_failure_reason", "last_failure_at", "unavailable_pending_at")
    for episode_id, episode in sorted(episodes.items()):
        lane = _episode_lane(show, episode)
        key = f"v1/work/{lane}/{show.slug}/{episode_id}.json"
        previous = None if dry_run else store.get_json(key)  # type: ignore[union-attr]
        if previous:
            summary["existing_state"] += 1
            continue
        if episode.get("unavailable"):
            state = "unavailable"
        elif episode.get("url"):
            state = "published"
        else:
            state = "pending"
        summary["planned"][state] += 1
        present_fields = [field for field in operational_fields if field in episode]
        if present_fields:
            summary["operational_fields_to_remove"].append({"episode_id": episode_id, "fields": present_fields})
        if not dry_run:
            first_seen = episode.get("last_failure_at") or episode.get("unavailable_pending_at") or now
            store.put_json(  # type: ignore[union-attr]
                key,
                {
                    "schema_version": SCHEMA_VERSION,
                    "show_slug": show.slug,
                    "episode_id": episode_id,
                    "lane": lane,
                    "state": state,
                    "candidate_id": None,
                    "attempt_count": 0,
                    "first_discovered_at": first_seen,
                    "first_ready_at": first_seen if state == "published" else None,
                    "next_attempt_at": now if state == "pending" else None,
                    "error_category": "historical_failure" if present_fields and state == "pending" else None,
                    "updated_at": now,
                },
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def capture(store: StateStore, baseline: Path, lane: str, show_filter: str | None = None, discovery_succeeded: bool = False) -> int:
    captured = 0
    shows = [load_show(show_filter)] if show_filter else load_enabled_shows()
    included = {value.strip() for value in os.environ.get("SYNC_PIPELINE_SHOWS", "").split(",") if value.strip()}
    if os.environ.get("SYNC_REQUIRE_ALLOWLIST") == "1" and not included and not show_filter:
        shows = []
    elif included and not show_filter:
        shows = [show for show in shows if show.slug in included]
    allowed_types = {"youtube", "youtube_playlist"} if lane == "youtube" else {lane}
    for show in shows:
        if not any(source.type in allowed_types for source in show.sources):
            continue
        before = load_episodes(baseline / show.slug / "episodes.json")
        after = load_episodes(show.episodes_path)
        config_hash = source_fingerprint(show.slug)
        if discovery_succeeded:
            store.put_json(
                f"v1/sources/{lane}/{show.slug}.json",
                {
                    "schema_version": SCHEMA_VERSION,
                    "show_slug": show.slug,
                    "lane": lane,
                    "source_config_fingerprint": config_hash,
                    "last_successful_discovery_at": timestamp(),
                    "processing_heartbeat_at": timestamp(),
                    "discovery_cursor": None,
                },
            )
        for episode_id in sorted(set(before) | set(after)):
            old = before.get(episode_id)
            new = after.get(episode_id)
            if old == new:
                continue
            public_episode = dict(new) if new is not None else None
            if public_episode is not None:
                for field in ("last_failure_reason", "last_failure_at", "unavailable_pending_at"):
                    public_episode.pop(field, None)
            candidate_body = {
                "schema_version": SCHEMA_VERSION,
                "show_slug": show.slug,
                "episode_id": episode_id,
                "lane": lane,
                "source_config_fingerprint": config_hash,
                "previous_record_fingerprint": fingerprint(old),
                "episode": public_episode,
            }
            work_key = f"v1/work/{lane}/{show.slug}/{episode_id}.json"
            prior_work = store.get_json(work_key) or {}
            prior_candidate_id = prior_work.get("candidate_id")
            prior_candidate = store.get_json(f"v1/candidates/{prior_candidate_id}.json") if prior_candidate_id else None
            if prior_candidate and all(prior_candidate.get(key) == value for key, value in candidate_body.items()):
                # Repeated capture of the same transition retains its identity,
                # including candidates created before IDs stopped using time.
                candidate_id = str(prior_candidate_id)
            else:
                # The same A -> B correction can be real work again after a
                # later B -> A correction. Link identity to the previous work
                # candidate so a completed old receipt cannot swallow it.
                unlinked_id = fingerprint(candidate_body)
                unlinked_candidate = store.get_json(f"v1/candidates/{unlinked_id}.json")
                if not prior_candidate_id or (unlinked_candidate and not receipt_complete(store.get_json(f"v1/receipts/{unlinked_id}.json"))):
                    # Keep the pre-index candidate identity when its write
                    # completed but the corresponding work update did not.
                    candidate_id = unlinked_id
                else:
                    candidate_id = fingerprint({**candidate_body, "predecessor_candidate_id": prior_candidate_id})
            existing = store.get_json(f"v1/candidates/{candidate_id}.json")
            candidate_receipt = store.get_json(f"v1/receipts/{candidate_id}.json")
            if receipt_complete(candidate_receipt):
                continue
            if not candidate_receipt and store.get_json(f"v1/quarantine/{candidate_id}.json"):
                continue
            if not existing:
                store.put_json(f"v1/candidates/{candidate_id}.json", {
                    **candidate_body,
                    "candidate_id": candidate_id,
                    "predecessor_candidate_id": prior_candidate_id,
                    "created_at": timestamp(),
                })
            mark_pending(store, candidate_id)
            if existing and prior_work.get("candidate_id") == candidate_id:
                continue
            work = {
                "schema_version": SCHEMA_VERSION,
                "show_slug": show.slug,
                "episode_id": episode_id,
                "lane": lane,
                "state": "ready_to_publish",
                "candidate_id": candidate_id,
                "attempt_count": int(prior_work.get("attempt_count") or 0) + 1,
                "first_discovered_at": prior_work.get("first_discovered_at") or timestamp(),
                "first_ready_at": prior_work.get("first_ready_at") or timestamp(),
                "next_attempt_at": None,
                "error_category": None,
                "updated_at": timestamp(),
            }
            store.put_json(work_key, work)
            if receipt_complete(store.get_json(f"v1/receipts/{candidate_id}.json")):
                # A publisher may have completed this candidate while capture
                # was writing its advisory work record.
                mark_work_published(store, work)
                store.delete_json(pending_key(candidate_id))
            captured += 1
    print(f"Captured {captured} immutable publication candidate(s) for {lane}.")
    return captured


def record_skips(store: StateStore, report: Path, lane: str, cookie_fingerprint: str | None = None) -> int:
    if not report.exists():
        return 0
    items = json.loads(report.read_text(encoding="utf-8"))
    recorded = 0
    for item in items:
        show_slug = str(item["show_slug"])
        episode_id = str(item["video_id"])
        work_key = f"v1/work/{lane}/{show_slug}/{episode_id}.json"
        previous = store.get_json(work_key) or {}
        attempt = int(previous.get("attempt_count") or 0) + 1
        reason = str(item.get("reason") or "")
        if item.get("phase") == "readiness":
            state = "waiting_for_recording"
            category = "recording_not_ready"
            next_attempt = timestamp(utc_now() + timedelta(hours=1))
        elif "cookie refresh required" in reason:
            state = "retry_wait"
            category = "cookie_invalid"
            next_attempt = retry_at(f"{show_slug}:{episode_id}", attempt)
        elif "auth/bot-check" in reason or "403" in reason:
            state = "retry_wait"
            category = "access"
            next_attempt = retry_at(f"{show_slug}:{episode_id}", attempt)
        else:
            state = "retry_wait"
            category = "unknown"
            next_attempt = retry_at(f"{show_slug}:{episode_id}", attempt)
        store.put_json(
            work_key,
            {
                "schema_version": SCHEMA_VERSION,
                "show_slug": show_slug,
                "episode_id": episode_id,
                "lane": lane,
                "state": state,
                "candidate_id": previous.get("candidate_id"),
                "attempt_count": attempt,
                "first_discovered_at": previous.get("first_discovered_at") or timestamp(),
                "first_ready_at": previous.get("first_ready_at"),
                "next_attempt_at": next_attempt,
                "error_category": category,
                "last_error_stage": item.get("phase"),
                "updated_at": timestamp(),
            },
        )
        recorded += 1
    if cookie_fingerprint and any(
        "cookie refresh required" in str(item.get("reason") or "") for item in items
    ):
        store.put_json(
            "v1/auth/youtube-cookie.json",
            {
                "schema_version": SCHEMA_VERSION,
                "status": "rejected",
                "rejected_fingerprint": cookie_fingerprint,
                "rejected_at": timestamp(),
            },
        )
    access_ids = {
        str(item.get("video_id")) for item in items
        if "auth/bot-check" in str(item.get("reason")) or "403" in str(item.get("reason"))
    }
    if lane == "youtube" and len(access_ids) >= 3:
        runner = os.environ.get("RUNNER_NAME", "unknown")
        key = f"v1/runners/{runner}.json"
        previous = store.get_json(key) or {}
        streak = int(previous.get("access_failure_streak") or 0) + 1
        pause_hours = RETRY_HOURS[min(streak - 1, len(RETRY_HOURS) - 1)]
        store.put_json(
            key,
            {
                "schema_version": SCHEMA_VERSION,
                "runner": runner,
                "status": "paused",
                "access_failure_streak": streak,
                "paused_until": timestamp(utc_now() + timedelta(hours=pause_hours)),
                "updated_at": timestamp(),
            },
        )
    print(f"Recorded {recorded} retry state update(s).")
    return recorded


def cookie_allowed(store: StateStore, fingerprint: str) -> bool:
    state = store.get_json("v1/auth/youtube-cookie.json") or {}
    return not (
        state.get("status") == "rejected"
        and state.get("rejected_fingerprint") == fingerprint
    )


def runner_gate(store: StateStore, runner: str) -> bool:
    value = store.get_json(f"v1/runners/{runner}.json")
    if not value or value.get("status") != "paused" or not value.get("paused_until"):
        return True
    paused_until = datetime.fromisoformat(value["paused_until"].replace("Z", "+00:00"))
    if utc_now() >= paused_until:
        return True
    print(f"Runner {runner} is paused until {value['paused_until']} after repeated access failures.")
    return False


def runner_success(store: StateStore, runner: str) -> None:
    store.put_json(
        f"v1/runners/{runner}.json",
        {"schema_version": SCHEMA_VERSION, "runner": runner, "status": "healthy", "access_failure_streak": 0, "paused_until": None, "updated_at": timestamp()},
    )


def mark_processing(store: StateStore, show_slug: str, episode_id: str, lane: str = "youtube") -> None:
    key = f"v1/work/{lane}/{show_slug}/{episode_id}.json"
    previous = store.get_json(key) or {}
    store.put_json(
        key,
        {
            "schema_version": SCHEMA_VERSION,
            "show_slug": show_slug,
            "episode_id": episode_id,
            "lane": lane,
            "state": "processing",
            "candidate_id": previous.get("candidate_id"),
            "attempt_count": int(previous.get("attempt_count") or 0) + 1,
            "first_discovered_at": previous.get("first_discovered_at") or timestamp(),
            "first_ready_at": previous.get("first_ready_at"),
            "next_attempt_at": None,
            "error_category": None,
            "updated_at": timestamp(),
        },
    )


def due_retries(
    store: StateStore,
    lane: str,
    show_slug: str,
    limit: int,
    now: datetime | None = None,
) -> list[str]:
    """Return retryable queue items whose durable retry time has arrived."""
    current = now or utc_now()
    due: list[dict[str, Any]] = []
    prefix = f"v1/work/{lane}/{show_slug}/"
    for _, item in store.list_json(prefix):
        if item.get("lane") != lane or item.get("show_slug") != show_slug:
            continue
        if item.get("state") not in {"waiting_for_recording", "retry_wait"}:
            continue
        if item.get("candidate_id"):
            continue
        next_attempt_at = item.get("next_attempt_at")
        if next_attempt_at:
            next_attempt = datetime.fromisoformat(str(next_attempt_at).replace("Z", "+00:00"))
            if next_attempt > current:
                continue
        due.append(item)

    due.sort(
        key=lambda item: (
            str(item.get("next_attempt_at") or item.get("first_discovered_at") or ""),
            str(item.get("first_discovered_at") or ""),
            str(item.get("episode_id") or ""),
        )
    )
    return [str(item["episode_id"]) for item in due[: max(0, limit)] if item.get("episode_id")]


def mark_retry_resolved(store: StateStore, show_slug: str, episode_id: str, lane: str = "youtube") -> None:
    """Close a retry after successful source validation of an existing public episode."""
    key = f"v1/work/{lane}/{show_slug}/{episode_id}.json"
    work = store.get_json(key)
    if not work or work.get("state") not in {"waiting_for_recording", "retry_wait"} or work.get("candidate_id"):
        return
    work.update({
        "state": "published",
        "next_attempt_at": None,
        "error_category": None,
        "last_error_stage": None,
        "updated_at": timestamp(),
    })
    store.put_json(key, work)


def discard_channel_id_retry(store: StateStore, show_slug: str, channel_id: str) -> bool:
    """Remove a channel mistakenly queued as a video, preserving any linked candidate."""
    key = f"v1/work/youtube/{show_slug}/{channel_id}.json"
    work = store.get_json(key)
    if not work or work.get("episode_id") != channel_id:
        return False
    if work.get("state") not in {"waiting_for_recording", "retry_wait"} or work.get("candidate_id"):
        return False
    store.delete_json(key)
    return True


def apply_candidates(store: StateStore, manifest: Path) -> int:
    started = time.monotonic()
    initial_operations = dict(getattr(store, "operations", {}))
    reconciliation = store.get_json(PENDING_RECONCILE_KEY) or {}
    last_reconciled = reconciliation.get("reconciled_at")
    if not last_reconciled or utc_now() - datetime.fromisoformat(last_reconciled.replace("Z", "+00:00")) >= PENDING_RECONCILE_INTERVAL:
        reconcile_pending(store)
    applied: list[dict[str, str]] = []
    marker_count = 0
    oldest_pending_at: str | None = None
    for _, marker in store.list_json("v1/pending/"):
        marker_count += 1
        candidate_id = str(marker["candidate_id"])
        candidate = store.get_json(f"v1/candidates/{candidate_id}.json")
        if not candidate:
            raise RuntimeError(f"Pending marker {candidate_id} has no immutable candidate")
        existing_receipt = store.get_json(f"v1/receipts/{candidate_id}.json")
        if existing_receipt:
            if receipt_complete(existing_receipt):
                store.delete_json(pending_key(candidate_id))
                continue
            created_at = candidate.get("created_at")
            if created_at and (oldest_pending_at is None or created_at < oldest_pending_at):
                oldest_pending_at = created_at
            applied.append({
                "candidate_id": candidate_id,
                "show_slug": str(candidate["show_slug"]),
                "episode_id": str(candidate["episode_id"]),
                "lane": str(candidate["lane"]),
            })
            continue
        if store.get_json(f"v1/quarantine/{candidate_id}.json"):
            store.delete_json(pending_key(candidate_id))
            continue
        work_key = f"v1/work/{candidate['lane']}/{candidate['show_slug']}/{candidate['episode_id']}.json"
        current_work = store.get_json(work_key) or {}
        newer_id = current_work.get("candidate_id")
        if newer_id and newer_id != candidate_id:
            newer = store.get_json(f"v1/candidates/{newer_id}.json")
            same_episode = newer and all(newer.get(key) == candidate.get(key) for key in ("lane", "show_slug", "episode_id"))
            newer_capture = same_episode and (
                newer.get("predecessor_candidate_id") == candidate_id
                or (candidate.get("created_at") and newer.get("created_at") and newer["created_at"] > candidate["created_at"])
            )
            if newer_capture:
                store.put_json(f"v1/quarantine/{candidate_id}.json", {
                    **candidate, "schema_version": SCHEMA_VERSION,
                    "quarantined_at": timestamp(),
                    "reason": "superseded by newer candidate",
                    "superseded_by": newer_id,
                })
                store.delete_json(pending_key(candidate_id))
                continue
        created_at = candidate.get("created_at")
        if created_at and (oldest_pending_at is None or created_at < oldest_pending_at):
            oldest_pending_at = created_at
        show = load_show(str(candidate["show_slug"]))
        if not show.enabled or source_fingerprint(show.slug) != candidate["source_config_fingerprint"]:
            store.put_json(
                f"v1/quarantine/{candidate_id}.json",
                {**candidate, "schema_version": SCHEMA_VERSION, "quarantined_at": timestamp(), "reason": "show disabled or configuration changed"},
            )
            store.delete_json(pending_key(candidate_id))
            continue
        episodes = load_episodes(show.episodes_path)
        episode_id = str(candidate["episode_id"])
        current = episodes.get(episode_id)
        proposed = candidate.get("episode")
        if current == proposed:
            applied.append({"candidate_id": candidate_id, "show_slug": show.slug, "episode_id": episode_id, "lane": str(candidate["lane"])})
            continue
        predecessor_id = candidate.get("predecessor_candidate_id")
        predecessor = store.get_json(f"v1/candidates/{predecessor_id}.json") if predecessor_id else None
        predecessor_applied = bool(
            current_work.get("candidate_id") == candidate_id
            and predecessor
            and all(predecessor.get(key) == candidate.get(key) for key in ("lane", "show_slug", "episode_id"))
            and predecessor.get("previous_record_fingerprint") == candidate["previous_record_fingerprint"]
            and predecessor.get("episode") == current
        )
        if fingerprint(current) != candidate["previous_record_fingerprint"] and not predecessor_applied:
            store.put_json(
                f"v1/quarantine/{candidate_id}.json",
                {**candidate, "schema_version": SCHEMA_VERSION, "quarantined_at": timestamp(), "reason": "published record changed"},
            )
            store.delete_json(pending_key(candidate_id))
            continue
        if proposed is None:
            episodes.pop(episode_id, None)
        else:
            episodes[episode_id] = proposed
        save_episodes(show.episodes_path, episodes)
        applied.append({"candidate_id": candidate_id, "show_slug": show.slug, "episode_id": episode_id, "lane": str(candidate["lane"])})
    manifest.write_text(json.dumps(applied, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    operations = getattr(store, "operations", {})
    object_calls = {key: count - initial_operations.get(key, 0) for key, count in operations.items()}
    age_hours = None if not oldest_pending_at else round((utc_now() - datetime.fromisoformat(oldest_pending_at.replace("Z", "+00:00"))).total_seconds() / 3600, 1)
    print(f"Applied {len(applied)} publication candidate(s) from {marker_count} marker(s) in {time.monotonic() - started:.2f}s; oldest pending age: {age_hours}h; state calls: {object_calls}.")
    return len(applied)


def receipt(store: StateStore, manifest: Path, revision: str) -> None:
    applied = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    for item in applied:
        candidate_id = item["candidate_id"]
        receipt_key = f"v1/receipts/{candidate_id}.json"
        existing = store.get_json(receipt_key)
        if not existing:
            store.put_json(
                receipt_key,
                {"schema_version": SCHEMA_VERSION, **item, "revision": revision, "release_revision": revision, "published_at": timestamp(), "deployments": {}, "notification": {"state": "pending"}},
            )
        elif existing.get("release_revision", existing.get("revision")) != revision:
            # A retry may rebuild on a newer main revision. Keep the original
            # content commit for provenance, while making both target results
            # describe this exact validated deployment attempt.
            existing.setdefault("deployment_history", []).append({
                "revision": existing.get("release_revision", existing.get("revision")),
                "deployments": existing.get("deployments") or {},
                "release_id": existing.get("release_id"),
                "payload_digest": existing.get("payload_digest"),
            })
            existing["release_revision"] = revision
            existing["deployments"] = {}
            existing.pop("release_id", None)
            existing.pop("payload_digest", None)
            store.put_json(receipt_key, existing)
        mark_work_published(store, item)


def update_receipts(
    store: StateStore, manifest: Path, *, deployment: str | None = None,
    status: str | None = None, notification: str | None = None,
    release_id: str | None = None, payload_digest: str | None = None,
) -> None:
    if (release_id is None) != (payload_digest is None) or any(
        value is not None and not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in (release_id, payload_digest)
    ):
        raise ValueError("release_id and payload_digest must be paired SHA-256 digests")
    applied = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    for item in applied:
        key = f"v1/receipts/{item['candidate_id']}.json"
        value = store.get_json(key)
        if not value:
            raise RuntimeError(f"Missing publication receipt for {item['candidate_id']}")
        if release_id:
            if value.get("release_id") not in {None, release_id}:
                raise RuntimeError("Publication receipt already belongs to another release artifact")
            if value.get("payload_digest") not in {None, payload_digest}:
                raise RuntimeError("Publication receipt already belongs to another payload digest")
            value["release_id"] = release_id
            value["payload_digest"] = payload_digest
        if deployment:
            value.setdefault("deployments", {})[deployment] = {
                "status": status,
                "revision": value.get("release_revision", value.get("revision")),
                "updated_at": timestamp(),
                **({"release_id": release_id, "payload_digest": payload_digest} if release_id else {}),
            }
        if notification:
            if not (notification == "not_required" and (value.get("notification") or {}).get("state") == "sent"):
                value["notification"] = {"state": notification, "updated_at": timestamp()}
        store.put_json(key, value)
        if receipt_complete(value):
            mark_work_published(store, item)
            store.delete_json(pending_key(item["candidate_id"]))


def notification_report(store: StateStore, manifest: Path, output: Path) -> int:
    applied = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    notifications: list[dict[str, Any]] = []
    for item in applied:
        candidate = store.get_json(f"v1/candidates/{item['candidate_id']}.json")
        receipt_value = store.get_json(f"v1/receipts/{item['candidate_id']}.json")
        if not candidate or not receipt_value:
            continue
        if (receipt_value.get("notification") or {}).get("state") not in {"pending", "failed"}:
            continue
        episode = candidate.get("episode")
        if candidate.get("previous_record_fingerprint") == fingerprint(None) and episode:
            notifications.append(new_episode_notification(load_show(item["show_slug"]), episode))
    output.write_text(json.dumps(notifications, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(notifications)} pending notification(s).")
    return len(notifications)


def health(store: StateStore, output: Path | None = None, persist: bool = False) -> dict[str, Any]:
    now = utc_now()
    work = [value for _, value in store.list_json("v1/work/")]
    unpublished = [item for item in work if item.get("state") not in {"published", "unavailable"}]
    ready = [item for item in unpublished if item.get("state") == "ready_to_publish"]
    oldest = min((item.get("first_discovered_at") for item in unpublished if item.get("first_discovered_at")), default=None)
    oldest_ready = min((item.get("first_ready_at") for item in ready if item.get("first_ready_at")), default=None)
    waiting_overdue = [
        item for item in unpublished
        if item.get("state") == "waiting_for_recording"
        and item.get("first_discovered_at")
        and now - datetime.fromisoformat(item["first_discovered_at"].replace("Z", "+00:00")) >= timedelta(hours=24)
    ]
    access_failures = [
        {"show_slug": item.get("show_slug"), "episode_id": item.get("episode_id"),
         "category": item.get("error_category"), "first_discovered_at": item.get("first_discovered_at")}
        for item in unpublished
        if item.get("error_category") in {"access", "cookie_invalid"}
    ]
    access_overdue = any(
        item["first_discovered_at"] and
        now - datetime.fromisoformat(item["first_discovered_at"].replace("Z", "+00:00")) >= timedelta(hours=6)
        for item in access_failures
    )
    stale_sources: list[dict[str, Any]] = []
    for _, source in store.list_json("v1/sources/"):
        last = source.get("last_successful_discovery_at")
        if not last:
            continue
        age = now - datetime.fromisoformat(last.replace("Z", "+00:00"))
        if age >= timedelta(hours=3):
            stale_sources.append({"show_slug": source.get("show_slug"), "lane": source.get("lane"), "age_hours": round(age.total_seconds() / 3600, 1)})
    receipts = [value for _, value in store.list_json("v1/receipts/")]
    publication = {
        "content_committed": len(receipts),
        "production_verified": 0,
        "complete": 0,
        "awaiting_completion": 0,
        "oldest_incomplete_at": None,
        "incomplete_over_6h": 0,
        "incomplete_without_timestamp": 0,
        "primary": {"verified": 0, "pending": 0, "failed": 0},
        "mirror": {"verified": 0, "pending": 0, "failed": 0},
        "notification": {"sent": 0, "not_required": 0, "pending": 0, "failed": 0},
    }
    for item in receipts:
        deployments = item.get("deployments") or {}
        release_revision = item.get("release_revision")
        target_states = []
        for label, target in (("primary", "cloudflare-pages"), ("mirror", "github-pages")):
            target_receipt = deployments.get(target) or {}
            state = target_receipt.get("status")
            verified_for_release = state == "verified" and (not release_revision or target_receipt.get("revision") == release_revision)
            category = "verified" if verified_for_release else "failed" if state == "failed" else "pending"
            publication[label][category] += 1
            target_states.append(category)
        notification_state = (item.get("notification") or {}).get("state")
        notification_category = notification_state if notification_state in {"sent", "not_required", "failed"} else "pending"
        publication["notification"][notification_category] += 1
        verified = all(state == "verified" for state in target_states)
        publication["production_verified"] += int(verified)
        if verified and notification_category in {"sent", "not_required"}:
            publication["complete"] += 1
            continue
        publication["awaiting_completion"] += 1
        committed_at = item.get("published_at")
        if committed_at:
            if publication["oldest_incomplete_at"] is None or committed_at < publication["oldest_incomplete_at"]:
                publication["oldest_incomplete_at"] = committed_at
            if now - datetime.fromisoformat(committed_at.replace("Z", "+00:00")) >= timedelta(hours=6):
                publication["incomplete_over_6h"] += 1
        else:
            publication["incomplete_without_timestamp"] += 1
    quarantine = {"count": 0, "oldest_at": None, "over_6h": 0, "without_timestamp": 0}
    for _, item in store.list_json("v1/quarantine/"):
        quarantine["count"] += 1
        quarantined_at = item.get("quarantined_at")
        if not quarantined_at:
            quarantine["without_timestamp"] += 1
            continue
        if quarantine["oldest_at"] is None or quarantined_at < quarantine["oldest_at"]:
            quarantine["oldest_at"] = quarantined_at
        if now - datetime.fromisoformat(quarantined_at.replace("Z", "+00:00")) >= timedelta(hours=6):
            quarantine["over_6h"] += 1
    ready_overdue = bool(oldest_ready and now - datetime.fromisoformat(oldest_ready.replace("Z", "+00:00")) >= timedelta(hours=6))
    stale_alert = any(item["age_hours"] >= 6 for item in stale_sources)
    alert = bool(ready_overdue or waiting_overdue or access_overdue or stale_alert or publication["incomplete_over_6h"] or publication["incomplete_without_timestamp"] or quarantine["over_6h"] or quarantine["without_timestamp"])
    status = "warning" if alert or access_failures or stale_sources or publication["awaiting_completion"] or quarantine["count"] else "ok"
    report = {
        "schema_version": SCHEMA_VERSION,
        "checked_at": timestamp(now),
        "queue_size": len(unpublished),
        "ready_count": len(ready),
        "oldest_unpublished_at": oldest,
        "oldest_ready_at": oldest_ready,
        "status": status,
        "alert": alert,
        "stale_sources": stale_sources,
        "source_access_failures": access_failures,
        "recordings_waiting_over_24h": len(waiting_overdue),
        "publication": publication,
        "quarantine": quarantine,
    }
    if persist:
        incident_key = "v1/health/sync-incident.json"
        previous = store.get_json(incident_key) or {}
        # A three-hour discovery gap is an operator-visible warning, but the
        # notification policy opens an incident only at the six-hour alert
        # threshold or for an overdue item. Treat legacy persisted
        # warning values as non-incidents so rollout does not emit a spurious
        # recovery message.
        incident_status = "alert" if alert else "ok"
        # Treat legacy error incidents as open so this rollout does not send
        # a false recovery message.
        previous_status = "alert" if previous.get("status") in {"alert", "error"} else "ok"
        last_notified = previous.get("last_notified_at")
        reminder_due = bool(
            incident_status == "alert" and last_notified
            and now - datetime.fromisoformat(last_notified.replace("Z", "+00:00")) >= timedelta(hours=24)
        )
        transition = (
            "opened" if incident_status == "alert" and previous_status == "ok"
            else "recovered" if incident_status == "ok" and previous_status == "alert"
            else "reminder" if reminder_due
            else None
        )
        report["notification_transition"] = transition
        store.put_json(
            incident_key,
            {
                "schema_version": SCHEMA_VERSION,
                "status": incident_status,
                "observed_status": status,
                "updated_at": timestamp(now),
                "opened_at": previous.get("opened_at") if previous_status == "alert" else (timestamp(now) if incident_status == "alert" else None),
                "last_notified_at": timestamp(now) if transition else last_notified,
            },
        )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("--output", type=Path, required=True)
    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.add_argument("--show", required=True)
    bootstrap_parser.add_argument("--output", type=Path, required=True)
    bootstrap_parser.add_argument("--dry-run", action="store_true")
    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--baseline", type=Path, required=True)
    capture_parser.add_argument("--lane", choices=("youtube", "drive", "existing_feed"), required=True)
    capture_parser.add_argument("--show")
    capture_parser.add_argument("--discovery-succeeded", action="store_true")
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--manifest", type=Path, required=True)
    subparsers.add_parser("reconcile-pending")
    receipt_parser = subparsers.add_parser("receipt")
    receipt_parser.add_argument("--manifest", type=Path, required=True)
    receipt_parser.add_argument("--revision", required=True)
    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--output", type=Path)
    health_parser.add_argument("--persist", action="store_true")
    update_parser = subparsers.add_parser("update-receipts")
    update_parser.add_argument("--manifest", type=Path, required=True)
    update_parser.add_argument("--deployment", choices=("cloudflare-pages", "github-pages"))
    update_parser.add_argument("--status", choices=("dispatched", "verified", "failed"))
    update_parser.add_argument("--notification", choices=("pending", "sent", "failed", "not_required"))
    update_parser.add_argument("--release-id")
    update_parser.add_argument("--payload-digest")
    skips_parser = subparsers.add_parser("record-skips")
    skips_parser.add_argument("--report", type=Path, required=True)
    skips_parser.add_argument("--lane", default="youtube")
    skips_parser.add_argument("--cookie-fingerprint")
    cookie_parser = subparsers.add_parser("cookie-allowed")
    cookie_parser.add_argument("--fingerprint", required=True)
    notifications_parser = subparsers.add_parser("notifications")
    notifications_parser.add_argument("--manifest", type=Path, required=True)
    notifications_parser.add_argument("--output", type=Path, required=True)
    runner_gate_parser = subparsers.add_parser("runner-gate")
    runner_gate_parser.add_argument("--runner", required=True)
    runner_success_parser = subparsers.add_parser("runner-success")
    runner_success_parser.add_argument("--runner", required=True)
    args = parser.parse_args()
    if args.command == "snapshot":
        snapshot(args.output)
        return 0
    if args.command == "bootstrap" and args.dry_run:
        bootstrap(None, args.show, args.output, dry_run=True)
        return 0
    store = StateStore.from_environment()
    if args.command == "bootstrap":
        bootstrap(store, args.show, args.output)
    elif args.command == "capture":
        capture(store, args.baseline, args.lane, args.show, args.discovery_succeeded)
    elif args.command == "apply":
        apply_candidates(store, args.manifest)
    elif args.command == "reconcile-pending":
        reconcile_pending(store)
    elif args.command == "receipt":
        receipt(store, args.manifest, args.revision)
    elif args.command == "health":
        health(store, args.output, args.persist)
    elif args.command == "update-receipts":
        update_receipts(
            store, args.manifest, deployment=args.deployment,
            status=args.status, notification=args.notification,
            release_id=args.release_id, payload_digest=args.payload_digest,
        )
    elif args.command == "record-skips":
        record_skips(store, args.report, args.lane, args.cookie_fingerprint)
    elif args.command == "cookie-allowed":
        return 0 if cookie_allowed(store, args.fingerprint) else 1
    elif args.command == "notifications":
        notification_report(store, args.manifest, args.output)
    elif args.command == "runner-gate":
        return 0 if runner_gate(store, args.runner) else 1
    elif args.command == "runner-success":
        runner_success(store, args.runner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
