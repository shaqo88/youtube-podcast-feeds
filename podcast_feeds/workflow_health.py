from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkflowSpec:
    workflow_id: str
    label: str
    critical: bool = True
    max_age_hours: float | None = None
    stuck_after_hours: float = 2.0


WORKFLOWS = (
    WorkflowSpec("sync", "Hourly podcast sync", max_age_hours=3),
    WorkflowSpec("credential_health", "Credential health", max_age_hours=8 * 24),
    WorkflowSpec("cloudflare_pages", "Cloudflare Pages deploy"),
    WorkflowSpec("pages", "GitHub Pages deploy"),
    WorkflowSpec("deploy_onboarding_worker", "Onboarding Worker deploy"),
    WorkflowSpec("notify_new_episodes", "New-episode notification"),
    WorkflowSpec("notify_added_podcast", "Added-podcast notification"),
    WorkflowSpec("approve_onboarding", "Onboarding approval"),
    WorkflowSpec(
        "discover_platform_links",
        "Platform-link discovery",
        critical=False,
        max_age_hours=8 * 24,
    ),
)


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def evaluate_workflow(
    spec: WorkflowSpec,
    runs: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    parsed = []
    for run in runs:
        try:
            created = _timestamp(str(run.get("createdAt") or ""))
        except ValueError:
            continue
        parsed.append((created, run))
    parsed.sort(key=lambda item: item[0], reverse=True)
    latest = parsed[0] if parsed else None
    completed = next(
        ((created, run) for created, run in parsed if run.get("status") == "completed"),
        None,
    )

    status = "ok"
    issue = ""
    latest_age = round((now - latest[0]).total_seconds() / 3600, 2) if latest else None
    completed_age = (
        round((now - completed[0]).total_seconds() / 3600, 2) if completed else None
    )
    if latest and latest[1].get("status") in {"queued", "in_progress", "waiting"}:
        if latest_age is not None and latest_age > spec.stuck_after_hours:
            status = "error" if spec.critical else "warning"
            issue = "active_run_stuck"
        else:
            status = "running"
            issue = "active_run"
    elif completed is None:
        status = "error" if spec.critical else "warning"
        issue = "never_completed"
    elif completed[1].get("conclusion") not in {"success", "skipped"}:
        status = "error" if spec.critical else "warning"
        issue = "latest_completed_failed"
    elif (
        spec.max_age_hours is not None
        and completed_age is not None
        and completed_age > spec.max_age_hours
    ):
        status = "error" if spec.critical else "warning"
        issue = "latest_completed_stale"

    latest_run = latest[1] if latest else {}
    completed_run = completed[1] if completed else {}
    return {
        "id": spec.workflow_id,
        "label": spec.label,
        "critical": spec.critical,
        "status": status,
        "issue": issue,
        "latest_status": str(latest_run.get("status") or "never"),
        "latest_created_at": str(latest_run.get("createdAt") or ""),
        "latest_age_hours": latest_age,
        "last_completed_conclusion": str(completed_run.get("conclusion") or "never"),
        "last_completed_at": str(completed_run.get("createdAt") or ""),
        "last_completed_age_hours": completed_age,
        "url": str((latest_run or completed_run).get("url") or ""),
        "max_age_hours": spec.max_age_hours,
    }


def build_workflow_health(
    runs_by_workflow: dict[str, list[dict[str, Any]]],
    *,
    specs: tuple[WorkflowSpec, ...] = WORKFLOWS,
    now: datetime | None = None,
) -> dict[str, Any]:
    workflows = [
        evaluate_workflow(spec, runs_by_workflow.get(spec.workflow_id, []), now=now)
        for spec in specs
    ]
    counts = {
        state: sum(item["status"] == state for item in workflows)
        for state in ("ok", "running", "warning", "error")
    }
    return {
        "status": "error" if counts["error"] else "warning" if counts["warning"] else "ok",
        "counts": counts,
        "workflows": workflows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["counts"]
    lines = [
        "## Critical workflow inventory",
        "",
        f"- Overall: `{report['status']}`",
        f"- Healthy: {counts['ok']}; running: {counts['running']}; warnings: {counts['warning']}; errors: {counts['error']}",
        "",
        "| Workflow | Critical | State | Last completed | Age (hours) | Issue |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for item in report["workflows"]:
        age = item["last_completed_age_hours"]
        lines.append(
            f"| {item['label']} | {'yes' if item['critical'] else 'no'} | "
            f"{item['status']} | {item['last_completed_conclusion']} | "
            f"{age if age is not None else '-'} | {item['issue'] or '-'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    runs_by_workflow = {}
    for spec in WORKFLOWS:
        path = args.runs_dir / f"{spec.workflow_id}.json"
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(value, list):
            raise ValueError(f"{path}: expected a JSON list")
        runs_by_workflow[spec.workflow_id] = value
    report = build_workflow_health(runs_by_workflow)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(render_markdown(report), encoding="utf-8")
    print(rendered, end="")
    return 1 if report["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
