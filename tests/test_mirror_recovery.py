import json
import subprocess
import unittest
from unittest.mock import patch

from podcast_feeds import mirror_recovery as recovery
from podcast_feeds.publication_status import mirror_only_failure, mirror_only_health


REVISION = "a" * 40
IDENTITY = (REVISION, "b" * 64, "c" * 64)


class MirrorRecoveryTests(unittest.TestCase):
    def perform(self, *, primary=IDENTITY, mirror=None, indexed=IDENTITY,
                current=True, ancestor=True, active=False):
        def git(*args, **kwargs):
            return subprocess.CompletedProcess(args, 0 if ancestor else 1,
                                               REVISION if args[0] == "rev-parse" else "", "")

        def run(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, json.dumps([
                {"status": "in_progress" if active else "completed"}
            ]), "")

        with patch.object(recovery.handoff, "git", side_effect=git), patch.object(
            recovery.handoff, "public_content_equal", return_value=current
        ), patch.object(recovery.handoff, "live_artifact", side_effect=[primary, mirror]), patch.object(
            recovery.subprocess, "run", side_effect=run
        ) as execute:
            result = recovery.recover("owner/repo", release_lookup=lambda _: indexed)
        return result, [call.args[0] for call in execute.call_args_list]

    def test_recovers_only_mirror_using_exact_retained_primary_identity(self):
        result, calls = self.perform()
        self.assertEqual(result, 0)
        self.assertEqual(len(calls), 2)
        self.assertIn("pages.yml", calls[-1])
        self.assertIn(f"revision={REVISION}", calls[-1])
        self.assertIn(f"release_id={IDENTITY[1]}", calls[-1])
        self.assertNotIn("force=true", calls[-1])
        self.assertFalse(any("sync.yml" in call for call in calls))

    def test_healthy_mirror_is_noop_and_active_deployment_is_not_duplicated(self):
        self.assertEqual(self.perform(mirror=IDENTITY), (0, []))
        self.assertEqual(len(self.perform(active=True)[1]), 1)

    def test_refuses_unknown_stale_or_unretained_primary(self):
        for args in ({"primary": None}, {"current": False}, {"ancestor": False},
                     {"indexed": (REVISION, "d" * 64, IDENTITY[2])},
                     {"indexed": (REVISION, IDENTITY[1], "d" * 64)}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.perform(**args)

    def test_dispatch_failure_is_not_reported_as_recovery(self):
        with patch.object(recovery.handoff, "git", return_value=subprocess.CompletedProcess([], 0, REVISION)), patch.object(
            recovery.handoff, "public_content_equal", return_value=True
        ), patch.object(recovery.handoff, "live_artifact", side_effect=[IDENTITY, None]), patch.object(
            recovery.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "gh")
        ), self.assertRaises(subprocess.CalledProcessError):
            recovery.recover("owner/repo", release_lookup=lambda _: IDENTITY)

    def test_mirror_warning_requires_positive_primary_and_sync_evidence(self):
        self.assertTrue(mirror_only_failure("success", "success", "failure"))
        for states in (("failure", "success", "failure"), ("success", "failure", "failure"),
                       ("success", "skipped", "failure"), ("success", "success", "skipped")):
            self.assertFalse(mirror_only_failure(*states))
        report = {"deployments": [
            {"target": "cloudflare-pages", "status": "ok"},
            {"target": "onboarding-worker", "status": "ok"},
            {"target": "github-pages", "status": "error"},
        ]}
        self.assertTrue(mirror_only_health(report))
        report["deployments"][0]["status"] = "error"
        self.assertFalse(mirror_only_health(report))
        self.assertFalse(mirror_only_health({}))

    def test_recovery_schedule_cannot_recurse_and_keeps_read_only_release_credentials(self):
        from pathlib import Path
        import yaml
        workflow = yaml.safe_load(Path(".github/workflows/mirror_recovery.yml").read_text())
        triggers = workflow.get("on", workflow.get(True))
        self.assertEqual(set(triggers), {"schedule", "workflow_dispatch"})
        self.assertEqual(workflow["permissions"]["contents"], "read")
        step = workflow["jobs"]["recover"]["steps"][-1]
        self.assertEqual(step["shell"], "bash")
        self.assertIn("READ_ACCESS_KEY", step["env"]["R2_RELEASE_ACCESS_KEY"])


if __name__ == "__main__":
    unittest.main()
