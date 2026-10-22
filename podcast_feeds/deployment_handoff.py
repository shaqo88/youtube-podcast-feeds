"""Hand validated Git content to the two existing deployment workflows.

This keeps writer retries useful after a push succeeded but its dispatch did not.
Each target is checked independently, so a healthy mirror does not hide a
missing primary deployment (or vice versa).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REVISION = re.compile(r"^[0-9a-f]{40}$")
ARTIFACT_ID = re.compile(r"^[0-9a-f]{64}$")
PUBLICATION_USER_AGENT = "torah-pod-publication/1.0"
TARGETS = {
    "github-pages": (
        "pages.yml",
        "https://shaqo88.github.io/youtube-podcast-feeds/deployment.json",
    ),
    "cloudflare-pages": (
        "cloudflare_pages.yml",
        "https://torah-pod.pages.dev/deployment.json",
    ),
}


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], check=check, capture_output=True, text=True
    )


def validate_revision(revision: str) -> str:
    if not REVISION.fullmatch(revision):
        raise ValueError("expected a full lowercase Git commit SHA")
    return revision


def public_content_equal(left: str, right: str) -> bool:
    """Compare checked-in public bytes, treating unknown revisions as unequal."""
    if not REVISION.fullmatch(left) or not REVISION.fullmatch(right):
        return False
    for revision in (left, right):
        if git("cat-file", "-e", f"{revision}^{{commit}}", check=False).returncode:
            return False
    return git("diff", "--quiet", left, right, "--", "public", check=False).returncode == 0


def live_revision(url: str, target: str) -> str | None:
    try:
        request = Request(url, headers={"Cache-Control": "no-cache", "User-Agent": PUBLICATION_USER_AGENT})
        with urlopen(request, timeout=12) as response:
            data = json.load(response)
        if not isinstance(data, dict) or data.get("target") != target:
            return None
        revision = data.get("revision")
        return revision if isinstance(revision, str) and REVISION.fullmatch(revision) else None
    except (HTTPError, URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError):
        return None


def live_artifact(url: str, target: str) -> tuple[str, str, str] | None:
    """Read target-specific receipt identity for an artifact deployment."""
    try:
        request = Request(url, headers={"Cache-Control": "no-cache", "User-Agent": PUBLICATION_USER_AGENT})
        with urlopen(request, timeout=12) as response:
            data = json.load(response)
        if not isinstance(data, dict) or data.get("target") != target:
            return None
        values = (data.get("revision"), data.get("release_id"), data.get("payload_digest"))
        if isinstance(values[0], str) and REVISION.fullmatch(values[0]) and all(isinstance(value, str) and ARTIFACT_ID.fullmatch(value) for value in values[1:]):
            return values
    except (HTTPError, URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError):
        pass
    return None


def emit_output(deploy: bool, reason: str) -> None:
    print(reason)
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"deploy={'true' if deploy else 'false'}\n")


def preflight(
    revision: str, target: str, *, force: bool = False, release_id: str | None = None,
    artifact_mode: bool = False, rollback: bool = False,
) -> int:
    validate_revision(revision)
    if release_id is not None and not ARTIFACT_ID.fullmatch(release_id):
        raise ValueError("release_id must be a full lowercase SHA-256 digest")
    if rollback and (not artifact_mode or release_id is None):
        raise ValueError("rollback requires artifact mode and an explicit retained release ID")
    actual = git("rev-parse", "HEAD").stdout.strip()
    if actual != revision:
        raise ValueError(f"checkout {actual} differs from requested revision {revision}")
    if artifact_mode and release_id is None and not force:
        emit_output(False, f"Skipping unretained {target} deployment for {revision} while artifact mode is enabled")
        return 0
    main = git("rev-parse", "origin/main").stdout.strip()
    if git("merge-base", "--is-ancestor", revision, main, check=False).returncode:
        raise ValueError(f"requested revision {revision} is not on main")
    if not rollback and not public_content_equal(revision, main):
        emit_output(False, f"Skipping obsolete {revision}: main has newer public content")
        return 0
    deployed = live_revision(TARGETS[target][1], target)
    if not rollback and deployed and deployed != revision and git("cat-file", "-e", f"{deployed}^{{commit}}", check=False).returncode == 0:
        if (
            git("merge-base", "--is-ancestor", revision, deployed, check=False).returncode == 0
            and public_content_equal(deployed, main)
        ):
            emit_output(False, f"Skipping {revision}: {target} already serves newer revision {deployed}")
            return 0
    if deployed == revision:
        if release_id is not None:
            live = live_artifact(TARGETS[target][1], target)
            if live and live[1] != release_id:
                raise ValueError(f"{target} already serves a different retained release for {revision}")
            if live and live[1] == release_id and not force:
                emit_output(False, f"Skipping duplicate {target} release {release_id}")
                return 0
        elif not force:
            emit_output(False, f"Skipping duplicate {target} deployment for {revision}")
            return 0
    emit_output(True, f"Deploying validated {revision} to {target}; live revision is {deployed or 'unknown'}")
    return 0


def verify(revision: str, target: str, *, attempts: int = 18, delay_seconds: int = 10,
           release_id: str | None = None, payload_digest: str | None = None) -> int:
    """Require the target's public receipt to serve this exact Git revision."""
    validate_revision(revision)
    if (release_id is None) != (payload_digest is None) or (release_id is not None and (not ARTIFACT_ID.fullmatch(release_id) or not ARTIFACT_ID.fullmatch(payload_digest or ""))):
        raise ValueError("release_id and payload_digest must be paired SHA-256 digests")
    if attempts < 1:
        raise ValueError("verification needs at least one attempt")
    url = TARGETS[target][1]
    for attempt in range(1, attempts + 1):
        # Distinct URLs avoid an old CDN response masking an updated receipt.
        probe_url = f"{url}?verify={revision}&attempt={attempt}"
        observed_artifact = live_artifact(probe_url, target) if release_id else None
        observed = observed_artifact[0] if release_id and observed_artifact else live_revision(probe_url, target) if not release_id else None
        if observed == revision and (release_id is None or observed_artifact == (revision, release_id, payload_digest)):
            print(f"{target}: verified live revision {revision} on attempt {attempt}")
            return 0
        print(f"{target}: waiting for {revision}; observed {observed or 'no valid receipt'} ({attempt}/{attempts})")
        if attempt < attempts:
            time.sleep(delay_seconds)
    print(f"::error::{target} did not serve exact revision {revision}", file=sys.stderr)
    return 1


def reconcile(
    revision: str, target: str, repository: str, *, artifact_mode: bool = False,
    release_lookup: Callable[[str], str] | None = None,
) -> int:
    """Recover newer content committed while this target was deploying."""
    validate_revision(revision)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository must be owner/name")
    actual = git("rev-parse", "HEAD").stdout.strip()
    if actual != revision:
        raise ValueError(f"checkout {actual} differs from deployed revision {revision}")
    main = git("rev-parse", "origin/main").stdout.strip()
    if git("merge-base", "--is-ancestor", revision, main, check=False).returncode:
        raise ValueError(f"deployed revision {revision} is not on main")
    if public_content_equal(revision, main):
        print(f"{target}: main has no newer public content after {revision}")
        return 0

    release_id = None
    if artifact_mode:
        if release_lookup is None:
            from .release_store import ReleaseStore

            release_lookup = ReleaseStore.from_environment().release_id_for_revision
        try:
            release_id = release_lookup(main)
        except (FileNotFoundError, ValueError, RuntimeError, KeyError) as exc:
            print(f"::error::{target} cannot hand off newer main without a retained release: {exc}", file=sys.stderr)
            return 1
        if not isinstance(release_id, str) or not ARTIFACT_ID.fullmatch(release_id):
            print(f"::error::{target} retained release index returned an invalid ID for {main}", file=sys.stderr)
            return 1

    workflow, url = TARGETS[target]
    deployed = live_revision(f"{url}?reconcile={main}", target)
    live = live_artifact(f"{url}?reconcile={main}", target) if artifact_mode else None
    if public_content_equal(deployed or "", main) and (not artifact_mode or (live and live[1] == release_id)):
        print(f"{target}: newer main public content is already live at {deployed}")
        return 0
    command = ["gh", "workflow", "run", workflow, "--repo", repository, "--ref", "main", "-f", f"revision={main}"]
    if release_id:
        command.extend(["-f", f"release_id={release_id}"])
    result = subprocess.run(
        command,
        capture_output=True, text=True,
    )
    if result.returncode:
        print(f"::error::{target} newer-main dispatch failed: {result.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"{target}: handed newer main revision {main} to deployment")
    return 0


def dispatch(revision: str, repository: str, release_id: str | None = None) -> int:
    validate_revision(revision)
    if release_id is not None and not ARTIFACT_ID.fullmatch(release_id):
        raise ValueError("release_id must be a full lowercase SHA-256 digest")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository must be owner/name")
    main = git("rev-parse", "origin/main").stdout.strip()
    if git("merge-base", "--is-ancestor", revision, main, check=False).returncode:
        raise ValueError(f"validated revision {revision} is not on main")
    if not public_content_equal(revision, main):
        raise ValueError("main contains newer public content; refusing an obsolete handoff")
    failures = []
    for target, (workflow, url) in TARGETS.items():
        deployed = live_revision(url, target)
        live = live_artifact(url, target) if release_id else None
        if public_content_equal(deployed or "", revision) and (release_id is None or (live and live[1] == release_id)):
            print(f"{target}: already serves the same public content at {deployed}")
            continue
        command = ["gh", "workflow", "run", workflow, "--repo", repository, "--ref", "main", "-f", f"revision={revision}"]
        if release_id:
            command.extend(["-f", f"release_id={release_id}"])
        result = subprocess.run(
            command,
            capture_output=True, text=True,
        )
        if result.returncode:
            failures.append(target)
            print(f"{target}: dispatch failed: {result.stderr.strip()}", file=sys.stderr)
        else:
            print(f"{target}: dispatched {revision}")
    if failures:
        print(f"Dispatch failed for: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    dispatch_parser = sub.add_parser("dispatch")
    dispatch_parser.add_argument("--revision", required=True)
    dispatch_parser.add_argument("--repo", required=True)
    dispatch_parser.add_argument("--release-id")
    preflight_parser = sub.add_parser("preflight")
    preflight_parser.add_argument("--revision", required=True)
    preflight_parser.add_argument("--target", choices=TARGETS, required=True)
    preflight_parser.add_argument("--force", action="store_true")
    preflight_parser.add_argument("--release-id")
    preflight_parser.add_argument("--artifact-mode", action="store_true")
    preflight_parser.add_argument("--rollback", action="store_true")
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--revision", required=True)
    verify_parser.add_argument("--target", choices=TARGETS, required=True)
    verify_parser.add_argument("--release-id")
    verify_parser.add_argument("--payload-digest")
    verify_parser.add_argument("--attempts", type=int, default=18)
    reconcile_parser = sub.add_parser("reconcile")
    reconcile_parser.add_argument("--revision", required=True)
    reconcile_parser.add_argument("--target", choices=TARGETS, required=True)
    reconcile_parser.add_argument("--repo", required=True)
    reconcile_parser.add_argument("--artifact-mode", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "dispatch":
            return dispatch(args.revision, args.repo, args.release_id)
        if args.command == "verify":
            return verify(args.revision, args.target, attempts=args.attempts,
                          release_id=args.release_id, payload_digest=args.payload_digest)
        if args.command == "reconcile":
            return reconcile(args.revision, args.target, args.repo, artifact_mode=args.artifact_mode)
        return preflight(args.revision, args.target, force=args.force, release_id=args.release_id,
                         artifact_mode=args.artifact_mode, rollback=args.rollback)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
