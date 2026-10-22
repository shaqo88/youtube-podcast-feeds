"""Verify one deployed publication target against an exact content revision."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen


TARGET_URLS = {
    "cloudflare-pages": "https://torah-pod.pages.dev/deployment.json",
    "github-pages": "https://shaqo88.github.io/youtube-podcast-feeds/deployment.json",
}
PUBLICATION_USER_AGENT = "torah-pod-publication/1.0"


def read_deployment(target: str, attempt: int) -> dict:
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    request = Request(
        f"{TARGET_URLS[target]}?sync={run_id}&attempt={attempt}",
        headers={"Cache-Control": "no-cache", "User-Agent": PUBLICATION_USER_AGENT},
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def validate_feed(show: str) -> bool:
    return subprocess.run(
        [sys.executable, "-m", "podcast_feeds.validate", "--show", show, "--network"],
        check=False,
    ).returncode == 0


def verify_target(
    target: str,
    revision: str,
    shows: list[str],
    *,
    read: Callable[[str, int], dict] = read_deployment,
    validate: Callable[[str], bool] = validate_feed,
    attempts: int | None = None,
    delay: float = 10,
    pause: Callable[[float], None] = time.sleep,
    release_id: str | None = None,
    payload_digest: str | None = None,
) -> bool:
    if target not in TARGET_URLS or len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
        raise ValueError("Expected a known target and full lowercase Git revision")
    if (release_id is None) != (payload_digest is None) or any(
        value is not None and (len(value) != 64 or any(char not in "0123456789abcdef" for char in value))
        for value in (release_id, payload_digest)
    ):
        raise ValueError("Artifact identity requires paired lowercase SHA-256 digests")
    # Deployment dispatch returns before the target job completes. GitHub Pages
    # can take up to 15 minutes, plus queue and CDN propagation time.
    if attempts is None:
        attempts = 24 if target == "cloudflare-pages" else 120
    if attempts < 1:
        raise ValueError("Verification requires at least one attempt")
    for attempt in range(attempts):
        try:
            deployment = read(target, attempt + 1)
        except (OSError, ValueError, KeyError) as error:
            status = getattr(error, "code", None)
            detail = f" HTTP {status}" if isinstance(status, int) else ""
            print(f"{target} receipt unavailable on attempt {attempt + 1}/{attempts}: {type(error).__name__}{detail}")
            deployment = {}
        if isinstance(deployment, dict) and (
            deployment.get("target"), deployment.get("revision")
        ) == (target, revision) and (release_id is None or (
            deployment.get("release_id"), deployment.get("payload_digest")
        ) == (release_id, payload_digest)):
            if target != "cloudflare-pages" or all(validate(show) for show in shows):
                return True
            print(f"{target} exact receipt visible on attempt {attempt + 1}/{attempts}; feed validation pending")
        elif isinstance(deployment, dict) and deployment:
            print(
                f"{target} receipt mismatch on attempt {attempt + 1}/{attempts}: "
                f"target={deployment.get('target', 'missing')} revision={deployment.get('revision', 'missing')} "
                f"release_id={deployment.get('release_id', 'missing')} "
                f"payload_digest={deployment.get('payload_digest', 'missing')}"
            )
        if attempt + 1 < attempts:
            pause(delay)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=tuple(TARGET_URLS), required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--release-id")
    parser.add_argument("--payload-digest")
    args = parser.parse_args()
    candidates = json.loads(args.manifest.read_text(encoding="utf-8"))
    shows = sorted({item["show_slug"] for item in candidates})
    verified = verify_target(args.target, args.revision, shows, release_id=args.release_id, payload_digest=args.payload_digest)
    print(f"{args.target}: {'verified' if verified else 'not verified'} for {args.revision}")
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
