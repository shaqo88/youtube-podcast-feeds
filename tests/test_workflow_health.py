import unittest
from datetime import datetime, timedelta, timezone

from podcast_feeds.workflow_health import (
    WorkflowSpec,
    build_workflow_health,
    evaluate_workflow,
    render_markdown,
)


NOW = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)


def run(hours_ago, *, status="completed", conclusion="success"):
    created = NOW - timedelta(hours=hours_ago)
    return {
        "status": status,
        "conclusion": conclusion,
        "createdAt": created.isoformat().replace("+00:00", "Z"),
        "url": "https://github.example/run",
    }


class WorkflowHealthTests(unittest.TestCase):
    def test_reports_current_success_and_freshness(self):
        result = evaluate_workflow(
            WorkflowSpec("sync", "Sync", max_age_hours=3), [run(1)], now=NOW
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["last_completed_age_hours"], 1.0)

    def test_reports_failed_and_stale_critical_workflows(self):
        failed = evaluate_workflow(
            WorkflowSpec("deploy", "Deploy"),
            [run(1, conclusion="failure")],
            now=NOW,
        )
        stale = evaluate_workflow(
            WorkflowSpec("sync", "Sync", max_age_hours=3), [run(4)], now=NOW
        )

        self.assertEqual((failed["status"], failed["issue"]), ("error", "latest_completed_failed"))
        self.assertEqual((stale["status"], stale["issue"]), ("error", "latest_completed_stale"))

    def test_distinguishes_active_from_stuck(self):
        spec = WorkflowSpec("sync", "Sync", stuck_after_hours=2)

        self.assertEqual(evaluate_workflow(spec, [run(1, status="queued", conclusion="")], now=NOW)["status"], "running")
        stuck = evaluate_workflow(spec, [run(3, status="in_progress", conclusion="")], now=NOW)
        self.assertEqual((stuck["status"], stuck["issue"]), ("error", "active_run_stuck"))

    def test_noncritical_failure_is_warning_and_report_is_rendered(self):
        specs = (
            WorkflowSpec("critical", "Critical"),
            WorkflowSpec("optional", "Optional", critical=False),
        )
        report = build_workflow_health(
            {
                "critical": [run(1)],
                "optional": [run(1, conclusion="failure")],
            },
            specs=specs,
            now=NOW,
        )

        self.assertEqual(report["status"], "warning")
        self.assertIn("Critical workflow inventory", render_markdown(report))
        self.assertIn("latest_completed_failed", render_markdown(report))

    def test_missing_critical_workflow_is_error(self):
        report = build_workflow_health(
            {}, specs=(WorkflowSpec("missing", "Missing"),), now=NOW
        )

        self.assertEqual(report["status"], "error")
        self.assertEqual(report["workflows"][0]["issue"], "never_completed")


if __name__ == "__main__":
    unittest.main()
