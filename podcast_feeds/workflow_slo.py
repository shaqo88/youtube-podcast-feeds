from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def build_availability_slo(
    runs: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    window_days: int = 30,
    target_percent: float = 99.5,
) -> dict[str, Any]:
    if window_days < 1:
        raise ValueError("window_days must be positive")
    if not 0 < target_percent <= 100:
        raise ValueError("target_percent must be in (0, 100]")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    window_start = now - timedelta(days=window_days)
    completed: list[tuple[datetime, str]] = []
    for run in runs:
        if run.get("event") != "schedule" or run.get("status") != "completed":
            continue
        try:
            created = _timestamp(str(run.get("createdAt") or ""))
        except ValueError:
            continue
        if window_start <= created <= now:
            completed.append((created, str(run.get("conclusion") or "unknown")))
    completed.sort(key=lambda item: item[0])
    successes = sum(conclusion == "success" for _, conclusion in completed)
    total = len(completed)
    rate = round(successes * 100 / total, 3) if total else None
    sample_start = completed[0][0] if completed else None
    coverage_days = round((now - sample_start).total_seconds() / 86400, 2) if sample_start else 0.0
    history_complete = coverage_days >= window_days - 1
    if not history_complete:
        status = "collecting"
        target_met = None
    else:
        target_met = bool(rate is not None and rate >= target_percent)
        status = "ok" if target_met else "error"
    return {
        "status": status,
        "window_days": window_days,
        "target_percent": target_percent,
        "window_start": window_start.isoformat().replace("+00:00", "Z"),
        "sample_start": sample_start.isoformat().replace("+00:00", "Z") if sample_start else None,
        "coverage_days": coverage_days,
        "history_complete": history_complete,
        "completed_runs": total,
        "successful_runs": successes,
        "unsuccessful_runs": total - successes,
        "success_percent": rate,
        "target_met": target_met,
    }


def render_markdown(report: dict[str, Any]) -> str:
    rate = report["success_percent"]
    rate_text = "unavailable" if rate is None else f"{rate:.3f}%"
    target = report["target_percent"]
    lines = [
        "## Scheduled availability objective",
        "",
        f"- Status: `{report['status']}`",
        f"- Objective: at least {target}% successful scheduled checks over {report['window_days']} days",
        f"- Observed: {rate_text} ({report['successful_runs']}/{report['completed_runs']} completed scheduled runs)",
        f"- Unsuccessful checks: {report['unsuccessful_runs']}",
        f"- History coverage: {report['coverage_days']} days",
    ]
    if not report["history_complete"]:
        lines.append("- Evaluation is collecting history; it will not claim the objective passed or failed yet.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--window-days", type=int, default=30)
    parser.add_argument("--target-percent", type=float, default=99.5)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    runs = json.loads(args.runs.read_text(encoding="utf-8"))
    if not isinstance(runs, list):
        raise ValueError("runs input must be a JSON list")
    report = build_availability_slo(
        runs,
        window_days=args.window_days,
        target_percent=args.target_percent,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(render_markdown(report), encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
