from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DEPLOYMENT_GRACE_HOURS = 1.0


@dataclass(frozen=True)
class DeploymentSpec:
    target: str
    label: str
    manifest_file: str
    source_paths: tuple[str, ...]


DEPLOYMENTS = (
    DeploymentSpec(
        "cloudflare-pages",
        "Cloudflare Pages",
        "cloudflare-pages.json",
        ("public", ".github/workflows/cloudflare_pages.yml"),
    ),
    DeploymentSpec(
        "github-pages",
        "GitHub Pages",
        "github-pages.json",
        ("public", ".github/workflows/pages.yml"),
    ),
    DeploymentSpec(
        "onboarding-worker",
        "Onboarding Worker",
        "onboarding-worker.json",
        ("workers/onboarding", ".github/workflows/deploy_onboarding_worker.yml"),
    ),
)


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp_missing_timezone")
    return parsed.astimezone(timezone.utc)


def _git_output(repo_root: Path, arguments: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def expected_revision(repo_root: Path, source_paths: tuple[str, ...]) -> str:
    return _git_output(
        repo_root,
        ["log", "-1", "--format=%H", "--", *source_paths],
    )


def revision_contains(repo_root: Path, expected: str, deployed: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", expected, deployed],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise ValueError("revision_not_available")
    return result.returncode == 0


def revision_age_hours(repo_root: Path, revision: str, now: datetime) -> float:
    committed_at = _timestamp(_git_output(repo_root, ["show", "-s", "--format=%cI", revision]))
    return round((now - committed_at).total_seconds() / 3600, 2)


def evaluate_deployment(
    spec: DeploymentSpec,
    manifest: dict[str, Any],
    *,
    now: datetime | None = None,
    expected_revision_reader: Callable[[tuple[str, ...]], str],
    revision_contains_reader: Callable[[str, str], bool],
    expected_revision_age_reader: Callable[[str], float],
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if isinstance(manifest.get("deployment"), dict):
        manifest = manifest["deployment"]
    issue = ""
    revision = str(manifest.get("revision") or "").lower()
    deployed_at_text = str(manifest.get("deployed_at") or "")
    expected = expected_revision_reader(spec.source_paths)
    expected_age_hours = None
    if REVISION_PATTERN.fullmatch(expected):
        try:
            expected_age_hours = expected_revision_age_reader(expected)
        except (subprocess.SubprocessError, ValueError):
            expected_age_hours = None
    within_grace = (
        expected_age_hours is not None
        and -0.1 <= expected_age_hours <= DEPLOYMENT_GRACE_HOURS
    )
    try:
        deployed_at = _timestamp(deployed_at_text)
        age_hours = round((now - deployed_at).total_seconds() / 3600, 2)
    except (TypeError, ValueError):
        deployed_at = None
        age_hours = None
        issue = "invalid_deployed_at"
    if manifest.get("schema_version") != 1:
        issue = issue or "unsupported_schema"
    elif manifest.get("target") != spec.target:
        issue = issue or "wrong_target"
    elif not REVISION_PATTERN.fullmatch(revision):
        issue = issue or "invalid_revision"
    elif (
        not str(manifest.get("run_id") or "").isdigit()
        or int(manifest.get("run_id") or 0) <= 0
    ):
        issue = issue or "invalid_run_id"
    elif age_hours is not None and age_hours < -0.1:
        issue = issue or "deployment_time_in_future"
    elif not REVISION_PATTERN.fullmatch(expected):
        issue = issue or "expected_revision_unavailable"
    else:
        try:
            if not revision_contains_reader(expected, revision):
                issue = (
                    "deployment_pending"
                    if within_grace
                    else "expected_revision_not_deployed"
                )
        except (subprocess.SubprocessError, ValueError):
            issue = "revision_comparison_failed"
    if within_grace and issue in {
        "invalid_deployed_at",
        "unsupported_schema",
        "invalid_revision",
        "invalid_run_id",
    }:
        issue = "deployment_pending"
    status = "pending" if issue == "deployment_pending" else "error" if issue else "ok"
    return {
        "target": spec.target,
        "label": spec.label,
        "status": status,
        "issue": issue,
        "revision": revision,
        "expected_revision": expected,
        "expected_revision_age_hours": expected_age_hours,
        "deployed_at": deployed_at_text,
        "age_hours": age_hours,
        "run_id": manifest.get("run_id"),
        "run_url": str(manifest.get("run_url") or ""),
    }


def build_deployment_health(
    manifests: dict[str, dict[str, Any]],
    *,
    repo_root: Path,
    specs: tuple[DeploymentSpec, ...] = DEPLOYMENTS,
    now: datetime | None = None,
) -> dict[str, Any]:
    deployments = []
    for spec in specs:
        manifest = manifests.get(spec.target)
        if not isinstance(manifest, dict):
            try:
                expected = expected_revision(repo_root, spec.source_paths)
                expected_age = revision_age_hours(
                    repo_root,
                    expected,
                    (now or datetime.now(timezone.utc)).astimezone(timezone.utc),
                )
            except (subprocess.SubprocessError, ValueError):
                expected = ""
                expected_age = None
            pending = (
                expected_age is not None
                and -0.1 <= expected_age <= DEPLOYMENT_GRACE_HOURS
            )
            deployments.append(
                {
                    "target": spec.target,
                    "label": spec.label,
                    "status": "pending" if pending else "error",
                    "issue": "deployment_pending" if pending else "manifest_missing",
                    "revision": "",
                    "expected_revision": expected,
                    "expected_revision_age_hours": expected_age,
                    "deployed_at": "",
                    "age_hours": None,
                    "run_id": None,
                    "run_url": "",
                }
            )
            continue
        deployments.append(
            evaluate_deployment(
                spec,
                manifest,
                now=now,
                expected_revision_reader=lambda paths: expected_revision(repo_root, paths),
                revision_contains_reader=lambda expected, deployed: revision_contains(
                    repo_root, expected, deployed
                ),
                expected_revision_age_reader=lambda revision: revision_age_hours(
                    repo_root, revision, (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
                ),
            )
        )
    has_errors = any(item["status"] == "error" for item in deployments)
    has_pending = any(item["status"] == "pending" for item in deployments)
    return {
        "status": "error" if has_errors else "pending" if has_pending else "ok",
        "deployments": deployments,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "## Deployment provenance",
        "",
        f"- Overall: `{report['status']}`",
        "",
        "| Target | State | Age (hours) | Live revision | Expected revision | Issue |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for item in report["deployments"]:
        live = item["revision"][:12] if item["revision"] else "-"
        expected = item["expected_revision"][:12] if item["expected_revision"] else "-"
        age = item["age_hours"] if item["age_hours"] is not None else "-"
        lines.append(
            f"| {item['label']} | {item['status']} | {age} | {live} | "
            f"{expected} | {item['issue'] or '-'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifests-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    manifests = {}
    for spec in DEPLOYMENTS:
        path = args.manifests_dir / spec.manifest_file
        if path.exists():
            manifests[spec.target] = json.loads(path.read_text(encoding="utf-8"))
    report = build_deployment_health(manifests, repo_root=args.repo_root.resolve())
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(render_markdown(report), encoding="utf-8")
    print(rendered, end="")
    return 1 if report["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
