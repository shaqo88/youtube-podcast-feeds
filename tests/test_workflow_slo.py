import unittest
from datetime import datetime, timedelta, timezone

from podcast_feeds.workflow_slo import build_availability_slo, render_markdown


NOW = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)


def run(days_ago, conclusion="success", event="schedule", status="completed"):
    created = NOW - timedelta(days=days_ago)
    return {
        "createdAt": created.isoformat().replace("+00:00", "Z"),
        "conclusion": conclusion,
        "event": event,
        "status": status,
    }


class WorkflowSloTests(unittest.TestCase):
    def test_collects_history_without_claiming_success(self):
        report = build_availability_slo([run(2), run(1)], now=NOW)

        self.assertEqual(report["status"], "collecting")
        self.assertIsNone(report["target_met"])
        self.assertEqual(report["success_percent"], 100.0)
        self.assertIn("will not claim", render_markdown(report))

    def test_calculates_completed_scheduled_run_objective(self):
        runs = [run(30), run(20), run(10), run(1, "failure")]
        runs += [run(5, event="workflow_dispatch"), run(2, status="in_progress")]
        report = build_availability_slo(runs, now=NOW, target_percent=70)

        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["target_met"])
        self.assertEqual(report["completed_runs"], 4)
        self.assertEqual(report["successful_runs"], 3)
        self.assertEqual(report["success_percent"], 75.0)

    def test_reports_missed_objective_after_full_window(self):
        report = build_availability_slo(
            [run(30), run(15), run(1, "cancelled")], now=NOW
        )

        self.assertEqual(report["status"], "error")
        self.assertFalse(report["target_met"])
        self.assertEqual(report["unsuccessful_runs"], 1)

    def test_rejects_invalid_objective_configuration(self):
        with self.assertRaises(ValueError):
            build_availability_slo([], now=NOW, window_days=0)
        with self.assertRaises(ValueError):
            build_availability_slo([], now=NOW, target_percent=0)


if __name__ == "__main__":
    unittest.main()
