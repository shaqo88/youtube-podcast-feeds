from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
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
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=stable_json(value),
            ContentType="application/json",
        )

    def list_json(self, prefix: str) -> Iterable[tuple[str, dict[str, Any]]]:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item["Key"]
                value = self.get_json(key)
                if value is not None:
                    yield key, value


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
                "created_at": timestamp(),
            }
            candidate_id = fingerprint(candidate_body)
            candidate_body["candidate_id"] = candidate_id
            store.put_json(f"v1/candidates/{candidate_id}.json", candidate_body)
            work_key = f"v1/work/{lane}/{show.slug}/{episode_id}.json"
            prior_work = store.get_json(work_key) or {}
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
            captured += 1
    print(f"Captured {captured} immutable publication candidate(s) for {lane}.")
    return captured


def record_skips(store: StateStore, report: Path, lane: str) -> int:
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


def apply_candidates(store: StateStore, manifest: Path) -> int:
    applied: list[dict[str, str]] = []
    for _, candidate in store.list_json("v1/candidates/"):
        candidate_id = str(candidate["candidate_id"])
        existing_receipt = store.get_json(f"v1/receipts/{candidate_id}.json")
        if existing_receipt:
            deployments = existing_receipt.get("deployments") or {}
            notification = (existing_receipt.get("notification") or {}).get("state")
            complete = (
                deployments.get("cloudflare-pages", {}).get("status") == "verified"
                and deployments.get("github-pages", {}).get("status") == "verified"
                and notification in {"sent", "not_required"}
            )
            if complete:
                continue
            applied.append({
                "candidate_id": candidate_id,
                "show_slug": str(candidate["show_slug"]),
                "episode_id": str(candidate["episode_id"]),
                "lane": str(candidate["lane"]),
            })
            continue
        show = load_show(str(candidate["show_slug"]))
        if not show.enabled or source_fingerprint(show.slug) != candidate["source_config_fingerprint"]:
            store.put_json(
                f"v1/quarantine/{candidate_id}.json",
                {**candidate, "schema_version": SCHEMA_VERSION, "quarantined_at": timestamp(), "reason": "show disabled or configuration changed"},
            )
            continue
        episodes = load_episodes(show.episodes_path)
        episode_id = str(candidate["episode_id"])
        current = episodes.get(episode_id)
        proposed = candidate.get("episode")
        if current == proposed:
            applied.append({"candidate_id": candidate_id, "show_slug": show.slug, "episode_id": episode_id, "lane": str(candidate["lane"])})
            continue
        if fingerprint(current) != candidate["previous_record_fingerprint"]:
            store.put_json(
                f"v1/quarantine/{candidate_id}.json",
                {**candidate, "schema_version": SCHEMA_VERSION, "quarantined_at": timestamp(), "reason": "published record changed"},
            )
            continue
        if proposed is None:
            episodes.pop(episode_id, None)
        else:
            episodes[episode_id] = proposed
        save_episodes(show.episodes_path, episodes)
        applied.append({"candidate_id": candidate_id, "show_slug": show.slug, "episode_id": episode_id, "lane": str(candidate["lane"])})
    manifest.write_text(json.dumps(applied, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Applied {len(applied)} publication candidate(s).")
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
                {"schema_version": SCHEMA_VERSION, **item, "revision": revision, "published_at": timestamp(), "deployments": {}, "notification": {"state": "pending"}},
            )
        work_key = f"v1/work/{item['lane']}/{item['show_slug']}/{item['episode_id']}.json"
        work = store.get_json(work_key)
        if work:
            work.update({"state": "published", "updated_at": timestamp()})
            store.put_json(work_key, work)


def update_receipts(
    store: StateStore, manifest: Path, *, deployment: str | None = None,
    status: str | None = None, notification: str | None = None
) -> None:
    applied = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    for item in applied:
        key = f"v1/receipts/{item['candidate_id']}.json"
        value = store.get_json(key)
        if not value:
            raise RuntimeError(f"Missing publication receipt for {item['candidate_id']}")
        if deployment:
            value.setdefault("deployments", {})[deployment] = {
                "status": status,
                "updated_at": timestamp(),
            }
        if notification:
            value["notification"] = {"state": notification, "updated_at": timestamp()}
        store.put_json(key, value)


def notification_report(store: StateStore, manifest: Path, output: Path) -> int:
    applied = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    notifications: list[dict[str, Any]] = []
    for item in applied:
        candidate = store.get_json(f"v1/candidates/{item['candidate_id']}.json")
        receipt_value = store.get_json(f"v1/receipts/{item['candidate_id']}.json")
        if not candidate or not receipt_value:
            continue
        if (receipt_value.get("notification") or {}).get("state") != "pending":
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
    stale_sources: list[dict[str, Any]] = []
    for _, source in store.list_json("v1/sources/"):
        last = source.get("last_successful_discovery_at")
        if not last:
            continue
        age = now - datetime.fromisoformat(last.replace("Z", "+00:00"))
        if age >= timedelta(hours=3):
            stale_sources.append({"show_slug": source.get("show_slug"), "lane": source.get("lane"), "age_hours": round(age.total_seconds() / 3600, 1)})
    ready_overdue = bool(oldest_ready and now - datetime.fromisoformat(oldest_ready.replace("Z", "+00:00")) >= timedelta(hours=6))
    stale_error = any(item["age_hours"] >= 6 for item in stale_sources)
    status = "error" if ready_overdue or waiting_overdue or stale_error else ("warning" if stale_sources else "ok")
    report = {
        "schema_version": SCHEMA_VERSION,
        "checked_at": timestamp(now),
        "queue_size": len(unpublished),
        "ready_count": len(ready),
        "oldest_unpublished_at": oldest,
        "oldest_ready_at": oldest_ready,
        "status": status,
        "stale_sources": stale_sources,
        "recordings_waiting_over_24h": len(waiting_overdue),
    }
    if persist:
        incident_key = "v1/health/sync-incident.json"
        previous = store.get_json(incident_key) or {}
        previous_status = previous.get("status", "ok")
        last_notified = previous.get("last_notified_at")
        reminder_due = bool(
            status != "ok" and last_notified
            and now - datetime.fromisoformat(last_notified.replace("Z", "+00:00")) >= timedelta(hours=24)
        )
        transition = "opened" if status != "ok" and previous_status == "ok" else "recovered" if status == "ok" and previous_status != "ok" else "reminder" if reminder_due else None
        report["notification_transition"] = transition
        store.put_json(
            incident_key,
            {
                "schema_version": SCHEMA_VERSION,
                "status": status,
                "updated_at": timestamp(now),
                "opened_at": previous.get("opened_at") if previous_status != "ok" else (timestamp(now) if status != "ok" else None),
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
    skips_parser = subparsers.add_parser("record-skips")
    skips_parser.add_argument("--report", type=Path, required=True)
    skips_parser.add_argument("--lane", default="youtube")
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
    elif args.command == "receipt":
        receipt(store, args.manifest, args.revision)
    elif args.command == "health":
        health(store, args.output, args.persist)
    elif args.command == "update-receipts":
        update_receipts(
            store, args.manifest, deployment=args.deployment,
            status=args.status, notification=args.notification
        )
    elif args.command == "record-skips":
        record_skips(store, args.report, args.lane)
    elif args.command == "notifications":
        notification_report(store, args.manifest, args.output)
    elif args.command == "runner-gate":
        return 0 if runner_gate(store, args.runner) else 1
    elif args.command == "runner-success":
        runner_success(store, args.runner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
