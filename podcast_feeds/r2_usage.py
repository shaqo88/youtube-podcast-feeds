from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from collections.abc import Iterable, Mapping
from typing import Any

from .config import load_enabled_shows
from .storage import r2_client

BYTES_PER_GB = 1024**3


@dataclass(frozen=True)
class PrefixUsage:
    prefix: str
    show_slug: str
    bytes: int
    objects: int


def _format_bytes(value: int) -> str:
    if value >= BYTES_PER_GB:
        return f"{value / BYTES_PER_GB:.2f} GB"
    if value >= 1024**2:
        return f"{value / 1024**2:.2f} MB"
    if value >= 1024:
        return f"{value / 1024:.2f} KB"
    return f"{value} B"


def _status(total_bytes: int, warning_gb: float, critical_gb: float) -> str:
    total_gb = total_bytes / BYTES_PER_GB
    if total_gb >= critical_gb:
        return "critical"
    if total_gb >= warning_gb:
        return "warning"
    return "ok"


def summarize_usage(
    bucket: str,
    objects: Iterable[Mapping[str, Any]],
    prefixes: Mapping[str, str],
) -> dict[str, Any]:
    usage: dict[str, PrefixUsage] = {}
    total_bytes = 0
    total_objects = 0

    for item in objects:
        key = str(item.get("Key") or "")
        size = int(item.get("Size") or 0)
        prefix = key.split("/", 1)[0] if "/" in key else "(root)"
        show_slug = prefixes.get(prefix, "(unmapped)")
        current = usage.get(prefix) or PrefixUsage(
            prefix=prefix,
            show_slug=show_slug,
            bytes=0,
            objects=0,
        )
        usage[prefix] = PrefixUsage(
            prefix=prefix,
            show_slug=current.show_slug,
            bytes=current.bytes + size,
            objects=current.objects + 1,
        )
        total_bytes += size
        total_objects += 1

    prefix_rows = sorted(
        (
            {
                "prefix": item.prefix,
                "show_slug": item.show_slug,
                "bytes": item.bytes,
                "objects": item.objects,
            }
            for item in usage.values()
        ),
        key=lambda item: item["bytes"],
        reverse=True,
    )
    unmapped_rows = [item for item in prefix_rows if item["show_slug"] == "(unmapped)"]

    return {
        "bucket": bucket,
        "total_bytes": total_bytes,
        "total_objects": total_objects,
        "prefixes": prefix_rows,
        "unmapped": {
            "bytes": sum(int(item["bytes"]) for item in unmapped_rows),
            "objects": sum(int(item["objects"]) for item in unmapped_rows),
            "prefixes": [str(item["prefix"]) for item in unmapped_rows],
        },
    }


def collect_usage() -> dict[str, Any]:
    bucket = os.environ["R2_BUCKET"]
    client = r2_client()
    paginator = client.get_paginator("list_objects_v2")
    prefixes = {show.r2.prefix: show.slug for show in load_enabled_shows()}
    objects = (
        item
        for page in paginator.paginate(Bucket=bucket)
        for item in page.get("Contents", [])
    )
    return summarize_usage(bucket, objects, prefixes)


def render_markdown(report: dict[str, Any], warning_gb: float, critical_gb: float) -> str:
    total_bytes = int(report["total_bytes"])
    status = _status(total_bytes, warning_gb, critical_gb)
    lines = [
        "# R2 Usage",
        "",
        f"- Bucket: `{report['bucket']}`",
        f"- Status: `{status}`",
        f"- Total: {_format_bytes(total_bytes)}",
        f"- Objects: {report['total_objects']}",
        f"- Warning threshold: {warning_gb:g} GB",
        f"- Critical threshold: {critical_gb:g} GB",
    ]
    unmapped = report.get("unmapped") or {}
    if int(unmapped.get("objects") or 0):
        prefix_list = ", ".join(f"`{prefix}`" for prefix in unmapped.get("prefixes") or [])
        lines.extend(
            [
                f"- Warning: {unmapped['objects']} unmapped object(s) use {_format_bytes(int(unmapped['bytes']))} under {prefix_list}.",
            ]
        )
    lines.extend(
        [
            "",
            "| Prefix | Show | Size | Objects |",
            "| --- | --- | ---: | ---: |",
        ]
    )
    for item in report["prefixes"]:
        lines.append(
            f"| `{item['prefix']}` | `{item['show_slug']}` | {_format_bytes(int(item['bytes']))} | {item['objects']} |"
        )
    if not report["prefixes"]:
        lines.append("| - | - | 0 B | 0 |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of Markdown.")
    parser.add_argument("--warning-gb", type=float, default=7.0)
    parser.add_argument("--critical-gb", type=float, default=9.0)
    args = parser.parse_args()

    report = collect_usage()
    report["status"] = _status(int(report["total_bytes"]), args.warning_gb, args.critical_gb)
    report["warning_gb"] = args.warning_gb
    report["critical_gb"] = args.critical_gb
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report, args.warning_gb, args.critical_gb), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
