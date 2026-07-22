import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from podcast_feeds.deployment_health import (
    DeploymentSpec,
    build_deployment_health,
    evaluate_deployment,
)
from podcast_feeds.deployment_manifest import build_manifest


NOW = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
LIVE_REVISION = "b" * 40
EXPECTED_REVISION = "a" * 40
SPEC = DeploymentSpec("pages", "Pages", "pages.json", ("public",))


class DeploymentHealthTests(unittest.TestCase):
    def manifest(self, **overrides):
        manifest = build_manifest(
            target="pages",
            revision=LIVE_REVISION,
            run_id="123",
            deployed_at="2026-07-22T10:00:00Z",
            run_url="https://github.example/run/123",
        )
        manifest.update(overrides)
        return manifest

    def evaluate(self, manifest, *, contains=True, expected_age_hours=2.0):
        return evaluate_deployment(
            SPEC,
            manifest,
            now=NOW,
            expected_revision_reader=lambda paths: EXPECTED_REVISION,
            revision_contains_reader=lambda expected, deployed: contains,
            expected_revision_age_reader=lambda revision: expected_age_hours,
        )

    def test_reports_fresh_revision_and_deployment_age(self):
        result = self.evaluate(self.manifest())

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["age_hours"], 2.0)
        self.assertEqual(result["expected_revision"], EXPECTED_REVISION)

    def test_rejects_live_revision_missing_latest_source_change(self):
        result = self.evaluate(self.manifest(), contains=False)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["issue"], "expected_revision_not_deployed")

    def test_allows_expected_deployment_to_propagate_for_one_hour(self):
        result = self.evaluate(
            self.manifest(), contains=False, expected_age_hours=0.5
        )

        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["issue"], "deployment_pending")

    def test_rejects_wrong_target_invalid_revision_and_future_timestamp(self):
        self.assertEqual(self.evaluate(self.manifest(target="worker"))["issue"], "wrong_target")
        self.assertEqual(self.evaluate(self.manifest(revision="short"))["issue"], "invalid_revision")
        self.assertEqual(self.evaluate(self.manifest(run_id=0))["issue"], "invalid_run_id")
        future = self.manifest(deployed_at="2026-07-22T13:00:00Z")
        self.assertEqual(self.evaluate(future)["issue"], "deployment_time_in_future")

    def test_accepts_worker_health_envelope(self):
        result = self.evaluate({"ok": True, "deployment": self.manifest()})

        self.assertEqual(result["status"], "ok")

    def test_manifest_requires_immutable_revision_and_positive_run(self):
        with self.assertRaisesRegex(ValueError, "full lowercase"):
            build_manifest(target="pages", revision="abc", run_id="1")
        with self.assertRaisesRegex(ValueError, "positive integer"):
            build_manifest(target="pages", revision=LIVE_REVISION, run_id="0")

    @patch("podcast_feeds.deployment_health.revision_age_hours", return_value=0.5)
    @patch("podcast_feeds.deployment_health.revision_contains", return_value=False)
    @patch("podcast_feeds.deployment_health.expected_revision", return_value=EXPECTED_REVISION)
    def test_report_preserves_pending_as_non_error(
        self, _expected, _contains, _age
    ):
        report = build_deployment_health(
            {"pages": self.manifest()},
            repo_root=Path("."),
            specs=(SPEC,),
            now=NOW,
        )

        self.assertEqual(report["status"], "pending")
        self.assertEqual(report["deployments"][0]["status"], "pending")

    @patch("podcast_feeds.deployment_health.revision_age_hours", return_value=2.0)
    @patch("podcast_feeds.deployment_health.expected_revision", return_value=EXPECTED_REVISION)
    def test_report_fails_closed_when_manifest_is_missing(self, _expected, _age):
        report = build_deployment_health(
            {}, repo_root=Path("."), specs=(SPEC,), now=NOW
        )

        self.assertEqual(report["status"], "error")
        self.assertEqual(report["deployments"][0]["issue"], "manifest_missing")

    @patch("podcast_feeds.deployment_health.revision_age_hours", return_value=0.25)
    @patch("podcast_feeds.deployment_health.expected_revision", return_value=EXPECTED_REVISION)
    def test_missing_manifest_uses_initial_rollout_grace(self, _expected, _age):
        report = build_deployment_health(
            {}, repo_root=Path("."), specs=(SPEC,), now=NOW
        )

        self.assertEqual(report["status"], "pending")
        self.assertEqual(report["deployments"][0]["issue"], "deployment_pending")


if __name__ == "__main__":
    unittest.main()
