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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REVISION = re.compile(r"^[0-9a-f]{40}$")
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
        request = Request(url, headers={"Cache-Control": "no-cache"})
        with urlopen(request, timeout=12) as response:
            data = json.load(response)
        if not isinstance(data, dict) or data.get("target") != target:
            return None
        revision = data.get("revision")
        return revision if isinstance(revision, str) and REVISION.fullmatch(revision) else None
    except (HTTPError, URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError):
        return None


def emit_output(deploy: bool, reason: str) -> None:
    print(reason)
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"deploy={'true' if deploy else 'false'}\n")


def preflight(revision: str, target: str, *, force: bool = False) -> int:
    validate_revision(revision)
    actual = git("rev-parse", "HEAD").stdout.strip()
    if actual != revision:
        raise ValueError(f"checkout {actual} differs from requested revision {revision}")
    main = git("rev-parse", "origin/main").stdout.strip()
    if git("merge-base", "--is-ancestor", revision, main, check=False).returncode:
        raise ValueError(f"requested revision {revision} is not on main")
    if not public_content_equal(revision, main):
        emit_output(False, f"Skipping obsolete {revision}: main has newer public content")
        return 0
    deployed = live_revision(TARGETS[target][1], target)
    if deployed and deployed != revision and git("cat-file", "-e", f"{deployed}^{{commit}}", check=False).returncode == 0:
        if git("merge-base", "--is-ancestor", revision, deployed, check=False).returncode == 0:
            emit_output(False, f"Skipping {revision}: {target} already serves newer revision {deployed}")
            return 0
    if deployed == revision and not force:
        emit_output(False, f"Skipping duplicate {target} deployment for {revision}")
        return 0
    emit_output(True, f"Deploying validated {revision} to {target}; live revision is {deployed or 'unknown'}")
    return 0


def dispatch(revision: str, repository: str) -> int:
    validate_revision(revision)
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
        if public_content_equal(deployed or "", revision):
            print(f"{target}: already serves the same public content at {deployed}")
            continue
        result = subprocess.run(
            ["gh", "workflow", "run", workflow, "--repo", repository, "--ref", "main", "-f", f"revision={revision}"],
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
    preflight_parser = sub.add_parser("preflight")
    preflight_parser.add_argument("--revision", required=True)
    preflight_parser.add_argument("--target", choices=TARGETS, required=True)
    preflight_parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "dispatch":
            return dispatch(args.revision, args.repo)
        return preflight(args.revision, args.target, force=args.force)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
