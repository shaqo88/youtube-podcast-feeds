"""Retry a delayed mirror from the primary's independently retained release."""

from __future__ import annotations

import argparse
import json
import re
import subprocess

from . import deployment_handoff as handoff


def recover(repository: str, *, release_lookup=None) -> int:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository must be owner/name")
    handoff.git("fetch", "origin", "main")
    main = handoff.git("rev-parse", "origin/main").stdout.strip()
    primary = handoff.live_artifact(handoff.TARGETS["cloudflare-pages"][1], "cloudflare-pages")
    if not primary:
        raise ValueError("Primary has no valid retained-release receipt; refusing mirror recovery")
    revision, release_id, _ = primary
    handoff.validate_revision(revision)
    if (handoff.git("merge-base", "--is-ancestor", revision, main, check=False).returncode
            or not handoff.public_content_equal(revision, main)):
        raise ValueError("Primary is behind main public content; primary publication needs attention")
    if release_lookup is None:
        from .release_store import ReleaseStore

        release_lookup = ReleaseStore.from_environment().release_identity_for_revision
    if release_lookup(revision) != primary:
        raise ValueError("Primary receipt does not match the private retained-release index")
    mirror = handoff.live_artifact(handoff.TARGETS["github-pages"][1], "github-pages")
    if mirror == primary:
        print(f"Primary and mirror both serve retained release {release_id}; no recovery needed")
        return 0
    runs = subprocess.run(
        ["gh", "run", "list", "--repo", repository, "--workflow", "pages.yml",
         "--branch", "main", "--limit", "100", "--json", "status"],
        check=True, capture_output=True, text=True,
    )
    if any(run["status"] != "completed" for run in json.loads(runs.stdout)):
        print("Mirror deployment already pending or running; leaving it to finish")
        return 0
    subprocess.run(
        ["gh", "workflow", "run", "pages.yml", "--repo", repository, "--ref", "main",
         "-f", f"revision={revision}", "-f", f"release_id={release_id}"],
        check=True, capture_output=True, text=True,
    )
    print(f"::warning::Primary publication verified; mirror delayed. Dispatched retained release {release_id} to mirror only")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    try:
        return recover(args.repo)
    except (ValueError, OSError, RuntimeError, KeyError, subprocess.SubprocessError) as exc:
        print(f"::error::Mirror recovery could not safely dispatch: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
