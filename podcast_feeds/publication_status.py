"""Classify publication impact without hiding failed verification."""

import argparse
import json
from pathlib import Path


def mirror_only_failure(sync: str, primary: str, mirror: str) -> bool:
    return sync == "success" and primary == "success" and mirror == "failure"


def mirror_only_health(report: dict) -> bool:
    deployments = report.get("deployments", [])
    states = {item.get("target"): item.get("status") for item in deployments}
    return (states.get("cloudflare-pages") == "ok"
            and states.get("onboarding-worker") == "ok"
            and states.get("github-pages") == "error"
            and all(item.get("status") == "ok" for item in deployments
                    if item.get("target") != "github-pages"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--health", type=Path)
    parser.add_argument("--sync", default="")
    parser.add_argument("--primary", default="")
    parser.add_argument("--mirror", default="")
    args = parser.parse_args()
    if args.health:
        try:
            delayed = mirror_only_health(json.loads(args.health.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, AttributeError):
            delayed = False
    else:
        delayed = mirror_only_failure(args.sync, args.primary, args.mirror)
    print("true" if delayed else "false")


if __name__ == "__main__":
    main()
