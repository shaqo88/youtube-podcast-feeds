from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

HOSTED_FEED_PREFIX = "https://torah-pod.pages.dev/"
DIRECTORY_PLATFORMS = ("apple", "spotify")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def _load_optional(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _published_age_days(value: str, today: date) -> int | None:
    if not value:
        return None
    try:
        published = datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None
    return max(0, (today - published).days)


def build_operational_report(
    public_status: dict[str, Any],
    *,
    r2_report: dict[str, Any] | None,
    availability_report: dict[str, Any] | None,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    normalized_status = public_status if isinstance(public_status, dict) else {}
    normalized_availability = (
        availability_report if isinstance(availability_report, dict) else {}
    )
    normalized_r2 = r2_report if isinstance(r2_report, dict) else {}

    availability_by_slug = {
        str(item.get("slug") or ""): item
        for item in (normalized_availability or {}).get("shows", [])
        if isinstance(item, dict)
    }
    storage_by_slug: dict[str, dict[str, int]] = {}
    for item in (normalized_r2 or {}).get("prefixes", []):
        if not isinstance(item, dict):
            continue
        slug = str(item.get("show_slug") or "")
        if not slug or slug == "(unmapped)":
            continue
        current = storage_by_slug.setdefault(slug, {"bytes": 0, "objects": 0})
        current["bytes"] += int(item.get("bytes") or 0)
        current["objects"] += int(item.get("objects") or 0)

    shows = []
    for item in normalized_status.get("shows", []) or []:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "")
        feed_url = str(item.get("feed_url") or "")
        hosted = feed_url.startswith(HOSTED_FEED_PREFIX)
        latest = item.get("latest_episode") if isinstance(item.get("latest_episode"), dict) else {}
        platforms = item.get("platforms") if isinstance(item.get("platforms"), dict) else {}

        if hosted and availability_report is None:
            feed_health = {"status": "unavailable", "reason": "report_missing"}
        elif hosted:
            checked = availability_by_slug.get(slug)
            feed_health = (
                {
                    "status": str(checked.get("status") or "error"),
                    "feed_status": checked.get("feed_status"),
                    "enclosure_status": checked.get("enclosure_status"),
                    "range_supported": bool(checked.get("range_supported")),
                    "error": str(checked.get("error") or ""),
                }
                if checked
                else {"status": "unavailable", "reason": "show_not_checked"}
            )
        else:
            feed_health = {"status": "not_applicable", "reason": "externally_hosted"}

        if hosted and r2_report is None:
            storage = {"status": "unavailable", "bytes": None, "objects": None}
        elif hosted:
            totals = storage_by_slug.get(slug, {"bytes": 0, "objects": 0})
            storage = {"status": "available", **totals}
        else:
            storage = {"status": "not_applicable", "bytes": None, "objects": None}

        show_status = "ok"
        if feed_health["status"] == "error":
            show_status = "error"
        elif hosted and (
            feed_health["status"] == "unavailable"
            or storage["status"] == "unavailable"
        ):
            show_status = "unavailable"

        shows.append(
            {
                "slug": slug,
                "title": str(item.get("title") or ""),
                "status": show_status,
                "hosting": "torah_pod" if hosted else "external",
                "feed_url": feed_url,
                "episode_count": int(item.get("episode_count") or 0),
                "latest_episode": {
                    "title": str(latest.get("title") or ""),
                    "published": str(latest.get("published") or ""),
                    "age_days": _published_age_days(
                        str(latest.get("published") or ""),
                        today,
                    ),
                },
                "feed_health": feed_health,
                "storage": storage,
                "directories": {
                    platform: {
                        "status": "listed" if platforms.get(platform) else "not_recorded",
                        "url": str(platforms.get(platform) or ""),
                    }
                    for platform in DIRECTORY_PLATFORMS
                },
                "source_types": sorted(
                    {
                        str(source.get("type") or "")
                        for source in (item.get("sources") or [])
                        if isinstance(source, dict) and source.get("type")
                    }
                ),
            }
        )

    counts = {
        status: sum(show["status"] == status for show in shows)
        for status in ("ok", "error", "unavailable")
    }
    unmapped = (r2_report or {}).get("unmapped")
    return {
        "status": "error" if counts["error"] else "ok",
        "content_updated_at": str(public_status.get("generated_at") or ""),
        "show_count": len(shows),
        "hosted_show_count": sum(show["hosting"] == "torah_pod" for show in shows),
        "counts": counts,
        "providers": {
            "availability": "available" if availability_report is not None else "unavailable",
            "r2": "available" if r2_report is not None else "unavailable",
        },
        "unmapped_storage": unmapped or {"bytes": 0, "objects": 0, "prefixes": []},
        "shows": shows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["counts"]
    lines = [
        "## Per-show operational health",
        "",
        f"- Overall: `{report['status']}`",
        f"- Shows: {report['show_count']} ({report['hosted_show_count']} Torah Pod-hosted)",
        f"- Healthy: {counts['ok']}; failing: {counts['error']}; unavailable: {counts['unavailable']}",
        f"- Availability data: `{report['providers']['availability']}`",
        f"- R2 data: `{report['providers']['r2']}`",
        "",
        "| Show | Hosting | Health | Episodes | Latest age | Feed/range | Storage | Apple | Spotify |",
        "| --- | --- | --- | ---: | ---: | --- | ---: | --- | --- |",
    ]
    for show in report["shows"]:
        latest_age = show["latest_episode"]["age_days"]
        feed = show["feed_health"]
        storage = show["storage"]
        feed_text = feed["status"]
        if feed.get("range_supported"):
            feed_text += "/range"
        storage_text = "-" if storage["bytes"] is None else str(storage["bytes"])
        lines.append(
            f"| `{show['slug']}` | {show['hosting']} | {show['status']} | "
            f"{show['episode_count']} | {latest_age if latest_age is not None else '-'} | "
            f"{feed_text} | {storage_text} | "
            f"{show['directories']['apple']['status']} | {show['directories']['spotify']['status']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", type=Path, default=Path("public/status.json"))
    parser.add_argument("--r2", type=Path)
    parser.add_argument("--availability", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()

    public_status = json.loads(args.status.read_text(encoding="utf-8"))
    report = build_operational_report(
        public_status,
        r2_report=_load_optional(args.r2),
        availability_report=_load_optional(args.availability),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(render_markdown(report), encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
